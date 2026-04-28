"""代理 IP 服务：从第三方 API 获取动态住宅/隧道 IP，供 MCP 进程使用。"""
import httpx
import config as cfg
from utils.logger import get_logger

logger = get_logger("proxy_service")


def fetch_fresh_proxy() -> str | None:
    """
    读取 proxy_api_url 配置，调用一次拿一个 IP，返回 http://ip:port 格式。
    失败返回 None（调用方决定是否继续）。
    """
    url = cfg.get("proxy_api_url", "").strip()
    if not url:
        return None
    try:
        with httpx.Client(trust_env=False, timeout=10) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
        proxy = _parse_response(data)
        if proxy:
            logger.info(f"[proxy] 获取新 IP：{proxy}")
        else:
            logger.warning(f"[proxy] 无法解析代理响应：{str(data)[:300]}")
        return proxy
    except Exception as e:
        logger.warning(f"[proxy] 获取代理 IP 失败：{e}")
        return None


def test_proxy_speed(proxy: str, timeout: int = 8) -> bool:
    """
    通过代理向小红书发一次 HEAD 请求，超时或失败则视为劣质 IP。
    timeout 秒内有响应即认为合格。
    """
    import time as _time
    try:
        t0 = _time.time()
        with httpx.Client(
            proxies={"http://": proxy, "https://": proxy},
            trust_env=False,
            timeout=timeout,
        ) as client:
            client.head("https://www.xiaohongshu.com")
        elapsed = _time.time() - t0
        logger.info(f"[proxy] 测速 OK，耗时 {elapsed:.1f}s：{proxy}")
        return True
    except Exception as e:
        logger.warning(f"[proxy] 测速失败，丢弃 IP：{proxy}：{e}")
        return False


def _parse_response(data: object) -> str | None:
    """兼容常见代理服务商 JSON 响应，返回 http://ip:port。"""
    if not isinstance(data, dict):
        return None

    lst = None

    # 格式①：{"data": {"list": [{"ip":..., "port":...}]}}  ← 聚量/快代理
    d = data.get("data")
    if isinstance(d, dict):
        lst = d.get("list") or d.get("proxy_list")

    # 格式②：{"result": "ip:port"}  或  {"result": [{...}]}
    if lst is None:
        r = data.get("result")
        if isinstance(r, str) and ":" in r:
            ip, _, port = r.partition(":")
            return f"http://{ip}:{port}"
        if isinstance(r, list):
            lst = r

    # 格式③：顶层列表字段
    if lst is None:
        for key in ("proxy_list", "proxies", "ips", "list"):
            if isinstance(data.get(key), list):
                lst = data[key]
                break

    if lst and len(lst) > 0:
        item = lst[0]
        if isinstance(item, str) and ":" in item:
            ip, _, port = item.partition(":")
            return f"http://{ip}:{port}"
        if isinstance(item, dict):
            ip   = str(item.get("ip") or item.get("host") or "")
            port = str(item.get("port") or "")
            user = str(item.get("user") or item.get("username") or "")
            pwd  = str(item.get("pass") or item.get("password") or "")
            if ip and port:
                if user and pwd:
                    return f"http://{user}:{pwd}@{ip}:{port}"
                return f"http://{ip}:{port}"

    return None
