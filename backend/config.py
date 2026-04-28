"""
全局配置读写。
所有配置存于 settings 表，敏感字段（AI Key、飞书 Secret）加密存储。
"""
import logging
from database import conn
from utils.crypto import encrypt, decrypt

_log = logging.getLogger("config")

# 敏感字段列表，写入时自动加密，读取时自动解密
_ENCRYPTED_KEYS = {
    "ai_api_key",
    "feishu_app_secret",
}


def get(key: str, default: str = "") -> str:
    c = conn()
    row = c.execute(
        "SELECT value, is_encrypted FROM settings WHERE key=?", (key,)
    ).fetchone()
    c.close()
    if row is None:
        return default
    value = row["value"]
    if row["is_encrypted"] and value:
        try:
            value = decrypt(value)
        except Exception:
            _log.warning(
                "配置项 '%s' 解密失败（可能是机器迁移导致密钥不匹配），"
                "请在「设置」页面重新保存该字段", key
            )
            # 清空损坏的加密数据，避免前端误以为已配置
            c2 = conn()
            c2.execute(
                "UPDATE settings SET value='', updated_at=datetime('now') WHERE key=?",
                (key,),
            )
            c2.commit()
            c2.close()
            return default
    return value


def set(key: str, value: str) -> None:
    is_enc = 1 if key in _ENCRYPTED_KEYS else 0
    stored = encrypt(value) if is_enc and value else value
    c = conn()
    c.execute(
        """INSERT INTO settings (key, value, is_encrypted, updated_at)
           VALUES (?, ?, ?, datetime('now'))
           ON CONFLICT(key) DO UPDATE SET
               value=excluded.value,
               is_encrypted=excluded.is_encrypted,
               updated_at=excluded.updated_at""",
        (key, stored, is_enc),
    )
    c.commit()
    c.close()


_SENTINEL = "__SET__"   # 前端用这个值表示"已设置但不回传明文"


def get_all_public() -> dict:
    """
    返回所有配置供 Web UI 展示。
    加密字段若已设置则返回哨兵值 "__SET__"，前端显示星号占位；
    未设置的加密字段返回 ""。
    """
    c = conn()
    rows = c.execute("SELECT key, value, is_encrypted FROM settings").fetchall()
    c.close()
    result = {}
    for r in rows:
        if r["is_encrypted"]:
            if not r["value"]:
                result[r["key"]] = ""
            else:
                # 验证能否解密；不能则视为未设置
                try:
                    decrypt(r["value"])
                    result[r["key"]] = _SENTINEL
                except Exception:
                    result[r["key"]] = ""
        else:
            result[r["key"]] = r["value"]
    return result
