"""
飞书多维表格 + 消息推送。
直接复用 dengta/xhs-publisher 的结构，字段名适配 RedBeacon schema。
"""
import base64
import time
from pathlib import Path
import requests
from utils.logger import get_logger

logger = get_logger("feishu")
TIMEOUT = 30
_MAX_RETRY = 3
_RETRY_DELAY = 5

FEISHU_BASE = "https://open.feishu.cn/open-apis"

# ── 飞书多维表格字段名 ─────────────────────────────────────────────────────────
# 只改这里，与模板表格字段一一对应
FIELD_TITLE        = "标题"
FIELD_BODY         = "文案"
FIELD_IMAGES       = "图片"
FIELD_TAGS         = "标签"
FIELD_STATUS       = "状态"
FIELD_SCHEDULE_AT  = "发布时间"   # 用户填写的定时发布时间（毫秒时间戳）

STATUS_PENDING   = "未审核"
STATUS_APPROVED  = "通过"
STATUS_REJECTED  = "驳回"
STATUS_PUBLISHED = "已发布"
STATUS_FAILED    = "发布失败"


def _retry(fn, desc: str):
    last_err = None
    for attempt in range(1, _MAX_RETRY + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if attempt < _MAX_RETRY:
                logger.warning(f"[feishu] {desc} 第{attempt}次失败，{_RETRY_DELAY}s 后重试: {e}")
                time.sleep(_RETRY_DELAY)
            else:
                logger.error(f"[feishu] {desc} 已失败 {_MAX_RETRY} 次，放弃: {e}")
    raise last_err


class FeishuAPI:

    def __init__(self, app_id: str, app_secret: str, app_token: str, table_id: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token    # 多维表格 app token
        self.table_id = table_id      # 数据表 ID
        self._tenant_token: str = ""

    # ── Token ─────────────────────────────────────────────────────────────────

    def _get_tenant_token(self) -> str:
        resp = requests.post(
            f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["tenant_access_token"]

    def _auth(self) -> dict:
        if not self._tenant_token:
            self._tenant_token = self._get_tenant_token()
        return {"Authorization": f"Bearer {self._tenant_token}"}

    def _refresh_token(self) -> None:
        self._tenant_token = self._get_tenant_token()

    # ── 多维表格操作 ───────────────────────────────────────────────────────────

    def add_record(self, fields: dict) -> str:
        """新增一行，返回 record_id。"""
        def _do():
            resp = requests.post(
                f"{FEISHU_BASE}/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records",
                headers=self._auth(),
                json={"fields": fields},
                timeout=TIMEOUT,
            )
            if resp.status_code == 401:
                self._refresh_token()
                raise Exception("token 过期，已刷新")
            resp.raise_for_status()
            body = resp.json()
            if body.get("code", 0) != 0:
                raise Exception(f"飞书错误 {body.get('code')}: {body.get('msg')} — {body}")
            return body["data"]["record"]["record_id"]
        return _retry(_do, "add_record")

    def update_record(self, record_id: str, fields: dict) -> None:
        def _do():
            resp = requests.put(
                f"{FEISHU_BASE}/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/{record_id}",
                headers=self._auth(),
                json={"fields": fields},
                timeout=TIMEOUT,
            )
            if resp.status_code == 401:
                self._refresh_token()
                raise Exception("token 过期，已刷新")
            resp.raise_for_status()
        _retry(_do, f"update_record({record_id})")

    def get_approved_records(self) -> list[dict]:
        """拉取状态为「通过」的待发布内容（自动翻页）。"""
        def _do():
            url = f"{FEISHU_BASE}/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"
            items = []
            page_token = None
            while True:
                params = {
                    "filter": f'CurrentValue.[{FIELD_STATUS}]="{STATUS_APPROVED}"',
                    "page_size": 100,
                }
                if page_token:
                    params["page_token"] = page_token
                resp = requests.get(url, headers=self._auth(), params=params, timeout=TIMEOUT)
                if resp.status_code == 401:
                    self._refresh_token()
                    raise Exception("token 过期，已刷新")
                resp.raise_for_status()
                body = resp.json()
                if body.get("code", 0) != 0:
                    raise Exception(f"飞书错误 {body.get('code')}: {body.get('msg')}")
                data = body.get("data", {})
                items.extend(data.get("items") or [])
                if not data.get("has_more"):
                    break
                page_token = data.get("page_token")
            return items
        return _retry(_do, "get_approved_records")

    def upload_image(self, image_path: str) -> str:
        """上传图片到飞书，返回 file_token。"""
        def _do():
            with open(image_path, "rb") as f:
                data = f.read()
            resp = requests.post(
                f"{FEISHU_BASE}/drive/v1/medias/upload_all",
                headers=self._auth(),
                data={
                    "file_name": Path(image_path).name,
                    "parent_type": "bitable_image",
                    "parent_node": self.app_token,
                    "size": str(len(data)),
                },
                files={"file": (Path(image_path).name, data)},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["data"]["file_token"]
        return _retry(_do, f"upload_image({image_path})")

    def download_image(self, file_token: str, save_path: str) -> None:
        """从飞书下载附件到本地文件。"""
        import json as _json
        def _do():
            resp = requests.get(
                f"{FEISHU_BASE}/drive/v1/medias/{file_token}/download",
                headers=self._auth(),
                timeout=60,
                stream=True,
            )
            resp.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
        _retry(_do, f"download_image({file_token})")

    # ── 消息推送 ───────────────────────────────────────────────────────────────

    def send_text_message(self, user_id: str, text: str) -> None:
        """发文本消息给指定用户（user_id 类型）。"""
        import json as _json
        def _do():
            resp = requests.post(
                f"{FEISHU_BASE}/im/v1/messages?receive_id_type=user_id",
                headers=self._auth(),
                json={
                    "receive_id": user_id,
                    "msg_type": "text",
                    "content": _json.dumps({"text": text}),
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
        _retry(_do, "send_text_message")
