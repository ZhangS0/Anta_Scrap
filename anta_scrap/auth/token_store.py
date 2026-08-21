"""凭证持久化：读写 ~/.anta_scrap/credentials.json。"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from anta_scrap.config import ACCOUNTS_FILE, CREDENTIALS_FILE


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
    username: str = ""

    def is_expired(self, skew_seconds: int = 60) -> bool:
        if not self.expires_at:
            return False  # 未知过期时间，乐观假设，401 时再续期
        return time.time() + skew_seconds >= self.expires_at


def _read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return default


def _write_json(path: Path, data, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        path.chmod(mode)
    except OSError:
        pass


def _username_key(username: Optional[str], creds: "Credentials") -> str:
    """凭证 map 的键：优先显式 username，其次 Credentials.username，再解码 user_id。"""
    if username:
        return username
    if creds.username:
        return creds.username
    try:
        return base64.b64decode(creds.user_id).decode("utf-8")
    except Exception:
        return "default"


def _load_cred_map(path: Path = CREDENTIALS_FILE) -> dict:
    """读凭证文件，统一为 {username: 凭证dict}；兼容旧单对象格式。"""
    data = _read_json(path)
    if not isinstance(data, dict):
        return {}
    # 旧格式：顶层直接是单个 Credentials 对象（含 jwt/access_token 字段）
    if "jwt" in data or "access_token" in data:
        creds = Credentials(**data)
        return {_username_key(None, creds): data}
    return data


def save_credentials(creds: Credentials, username: Optional[str] = None, path: Path = CREDENTIALS_FILE) -> None:
    """按用户保存凭证：credentials.json 存 {username: {字段...}}。"""
    store = _load_cred_map(path)
    store[_username_key(username, creds)] = asdict(creds)
    _write_json(path, store)


def load_credentials(username: Optional[str] = None, path: Path = CREDENTIALS_FILE) -> Optional[Credentials]:
    """按用户读取凭证；username=None 且仅一个用户时返回它，多用户返回 None。"""
    store = _load_cred_map(path)
    if username:
        data = store.get(username)
        return Credentials(**data) if data else None
    if len(store) == 1:
        return Credentials(**next(iter(store.values())))
    return None


def save_account(username: str, password: str, dom_id: str = "guanbi", path: Path = ACCOUNTS_FILE) -> None:
    """把账号密码存到 accounts.json（明文 0600），供日后免密重登。"""
    store = _read_json(path, {}) or {}
    store[username] = {"password": password, "dom_id": dom_id or "guanbi"}
    _write_json(path, store)


def load_account(username: str, path: Path = ACCOUNTS_FILE) -> Optional[dict]:
    """取某账号已存密码/域：{"password", "dom_id"} 或 None。"""
    store = _read_json(path, {}) or {}
    return store.get(username)


def clear_credentials(path: Path = CREDENTIALS_FILE) -> None:
    if path.exists():
        path.unlink()
