"""
Fernet 对称加密工具。
AI API Key 等敏感配置加密存入 settings 表，任务执行时解密使用。
密钥派生自用户机器唯一 ID，不存入数据库。
"""
import hashlib
import platform
import base64
from cryptography.fernet import Fernet


def _derive_key() -> bytes:
    """根据机器特征派生 Fernet 密钥（32 字节，base64url 编码）。"""
    # 取机器名 + 平台信息作为熵源，足够防止数据库文件被直接搬走后读取
    seed = f"{platform.node()}:{platform.machine()}:{platform.system()}"
    digest = hashlib.sha256(seed.encode()).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_derive_key())


def encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()
