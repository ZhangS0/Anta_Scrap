"""会话管理：加载凭证 → JWT 过期自动续期 → 包装 AntaClient。"""

from __future__ import annotations

import time
from typing import Optional  # noqa: F401  (保留给类型注解使用)

from anta_scrap.auth.token_store import Credentials, load_account, load_credentials, save_account, save_credentials
from anta_scrap.client import AntaClient
from anta_scrap.config import env


class SessionExpired(RuntimeError):
    """凭证完全失效（refresh_token 也用不了），需要重新登录。"""


class PasswordRequired(RuntimeError):
    """该账号首次登录或本地无可用密码，需要调用方传入密码。"""


def _verify_or_false(creds: Credentials) -> bool:
    """服务端校验凭证；网络异常等意外情况按"校验失败"处理，交给续期分支兜底。"""
    from anta_scrap.auth.login import verify_token

    try:
        return verify_token(creds)
    except Exception:
        return False


def resolve_credentials(
    username: str,
    password: Optional[str] = None,
    dom_id: Optional[str] = None,
) -> Credentials:
    """多用户会话解析：优先用该账号缓存的 JWT；失效则用「本次传入或已存」的密码重登。

    - 传了 password → 记住它（save_account，供日后免密重登）。
    - 没传 → 从 accounts.json 取已存 password/dom_id。
    - 缓存 JWT 有效（未过期 + validate-token 通过）→ 直接返回，不重登（日常快路径）。
    - 缓存失效且无密码 → PasswordRequired（首次登录需传密码）。
    - 缓存失效且有密码 → login() 重登并 save_account 兜底。
    """
    from anta_scrap.auth.login import login

    provided_pwd = password or None
    provided_dom = dom_id or None

    effective_pwd = provided_pwd
    effective_dom = provided_dom
    if not effective_pwd:
        acct = load_account(username)
        if acct:
            effective_pwd = acct.get("password")
            effective_dom = effective_dom or acct.get("dom_id")
    effective_dom = effective_dom or "guanbi"

    creds = load_credentials(username)
    if creds and not creds.is_expired() and _verify_or_false(creds):
        if provided_pwd:
            save_account(username, provided_pwd, effective_dom)
        return creds

    if not effective_pwd:
        raise PasswordRequired(
            f"账号 {username} 首次登录或凭证失效且无本地密码，请传入 password"
        )

    result = login(username=username, password=effective_pwd, dom_id=effective_dom)
    creds = result.credentials
    save_account(username, effective_pwd, effective_dom)
    return creds


def _renew_credentials(creds: Optional[Credentials]) -> Credentials:
    """自动恢复失效凭证：先 refresh 续期，失败再用 .env 账号密码重登。"""
    from anta_scrap.auth.login import LoginError, login, refresh_credentials

    refresh_err = None
    if creds is not None:
        try:
            return refresh_credentials(creds)
        except LoginError as e:
            refresh_err = e

    username = env("ANTA_USERNAME")
    password = env("ANTA_PASSWORD")
    if not username or not password:
        raise SessionExpired(
            "凭证已失效"
            + (f"且 refresh_token 续期失败（{refresh_err}）" if refresh_err else "")
            + "；.env 未配置 ANTA_USERNAME/ANTA_PASSWORD，无法自动重登。"
            "请配置后重试，或手动运行: python scripts/anta_login.py"
        ) from refresh_err
    try:
        result = login(
            username=username,
            password=password,
            dom_id=env("ANTA_DOM_ID", "guanbi") or "guanbi",
        )
    except LoginError as e:
        raise SessionExpired(
            f"自动重登失败（账号密码可能已改或触发验证码: {e}）。"
            "请检查 .env 或手动运行: python scripts/anta_login.py"
        ) from e
    return result.credentials


class AntaSession:
    """高层会话句柄。

    用法：
        sess = AntaSession.ensure()        # 自动加载本地凭证
        client = sess.client                # 拿底层 AntaClient
        data = client.get_json("/api/...")

    ensure() 时若 JWT 已过期，自动用 refresh_token 续期一次并覆写凭证文件；
    续期也失败则抛 SessionExpired。会话中途的 401 不做被动续期
    （JWT 有效期 14 天，长会话场景罕见；遇到 401 重跑 ensure 即可）。
    """

    def __init__(self, creds: Credentials, client: Optional[AntaClient] = None):
        self.credentials = creds
        self.client = client or AntaClient(creds)

    @classmethod
    def ensure(cls, *, dom_id: Optional[str] = None) -> "AntaSession":
        """加载本地凭证并自动校验；失效时自动恢复，全程无需人工重登。

        校验两个维度：本地 JWT 过期时间 + 服务端 validate-token（会话可能被
        顶号/登出提前作废）。任一失效按顺序自动恢复：
          1. refresh_token 续期（轻量，优先）
          2. 用 .env 的账号密码走完整 CAS 登录（覆写凭证文件）

        两步都失败（如密码已改、触发验证码）才抛 SessionExpired。

        dom_id 参数已废弃（保留兼容）：凭证文件里存的已经是 Base64 编码后的
        x-dom-id 值（如 Z3VhbmJp），直接使用即可，无需覆盖。
        """
        creds = load_credentials(env("ANTA_USERNAME"))
        # 没有本地凭证 / 本地过期 / 服务端失效，都走自动恢复（refresh → 重登）
        if creds is None or creds.is_expired() or not _verify_or_false(creds):
            creds = _renew_credentials(creds)
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
