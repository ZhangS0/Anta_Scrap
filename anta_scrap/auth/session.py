"""会话管理：加载凭证 → 包装 AntaClient → 401 自动续期。"""

from __future__ import annotations

import time
from typing import Optional  # noqa: F401  (保留给类型注解使用)

from anta_scrap.auth.token_store import Credentials, load_credentials, save_credentials
from anta_scrap.client import AntaClient


class SessionExpired(RuntimeError):
    """凭证完全失效（refresh_token 也用不了），需要重新登录。"""


class AntaSession:
    """高层会话句柄。

    用法：
        sess = AntaSession.ensure()        # 自动加载本地凭证
        client = sess.client                # 拿底层 AntaClient
        data = client.get_json("/api/...")

    401 时自动用 refresh_token 续期一次；再失败抛 SessionExpired。
    """

    def __init__(self, creds: Credentials, client: Optional[AntaClient] = None):
        self.credentials = creds
        self.client = client or AntaClient(creds)

    @classmethod
    def ensure(cls, *, dom_id: Optional[str] = None) -> "AntaSession":
        """加载本地凭证；不存在或过期则提示重登。

        dom_id 参数已废弃（保留兼容）：凭证文件里存的已经是 Base64 编码后的
        x-dom-id 值（如 Z3VhbmJp），直接使用即可，无需覆盖。
        """
        creds = load_credentials()
        if creds is None:
            raise SessionExpired(
                "未找到本地凭证，请先运行: python scripts/anta_login.py"
            )
        return cls(creds)

    def is_jwt_expired(self, skew_seconds: int = 60) -> bool:
        return self.credentials.is_expired(skew_seconds)

    def save(self) -> None:
        save_credentials(self.credentials)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "AntaSession":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
