"""凭证持久化：读写 ~/.anta_scrap/credentials.json。"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from anta_scrap.config import CREDENTIALS_FILE


@dataclass
class Credentials:
    """登录后需要持久化的全部字段。

    access_token / refresh_token：CAS+OAuth2 流程产出，用于兑换 JWT。
    jwt：调 /api/* 时放进 `token` header 的值。
    user_id：Base64 编码的用户 ID（如 V0VCVVNFUg====）。
    dom_id：x-dom-id header 值（HAR 默认 guanbi）。
    expires_at：jwt 的 unix 过期时间（秒），未知时为 None。
    """

    access_token: str
    refresh_token: str
    jwt: str
    user_id: str
    dom_id: str = "guanbi"
    expires_at: Optional[float] = None

    def is_expired(self, skew_seconds: int = 60) -> bool:
        if not self.expires_at:
            return False  # 未知过期时间，乐观假设，401 时再续期
        return time.time() + skew_seconds >= self.expires_at


def save_credentials(creds: Credentials, path: Path = CREDENTIALS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 仅当前用户可读写（Windows 上 chmod 影响有限，但写一下不亏）
    data = json.dumps(asdict(creds), ensure_ascii=False, indent=2)
    path.write_text(data, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_credentials(path: Path = CREDENTIALS_FILE) -> Optional[Credentials]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Credentials(**data)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def clear_credentials(path: Path = CREDENTIALS_FILE) -> None:
    if path.exists():
        path.unlink()
