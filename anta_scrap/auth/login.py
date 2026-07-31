"""CAS + OAuth2 登录链路。

流程（HAR 验证）：
  1. GET  登录页（带 service 参数）→ 从 HTML 抓 execution / loginTraceId 兜底
  2. POST 登录表单 → 302 带 ticket → /oauth2.0/callbackAuthorize
  3. GET  callbackAuthorize → 302 → datav.anta.com/?access_token=AT-xxx&refresh_token=RT-xxx
  4. GET  datav.anta.com/  → 触发后端用 access_token 兑换 JWT
  5. GET  /api/validate-token（带 JWT） → 200 表示登录态 OK，顺便确认 user-id / dom-id

登录页 service 参数固定（datav 的 OAuth client_id=100068），无需用户传。
"""

from __future__ import annotations

import base64
import re
import secrets
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlparse

import httpx

from anta_scrap.auth.token_store import Credentials, save_credentials
from anta_scrap.config import CREDENTIALS_FILE

# datav 在 CAS 的 OAuth client 配置（HAR 固定值）
CLIENT_ID = "100068"
REDIRECT_URI = "https://datav.anta.com/standard-oauth2/authenticate"
STATE_DEFAULT = "1-b84e57bdfa4ef36fc34c207aef983d51baf49832-Y3NyZi1zdGF0ZQ=="


class LoginError(RuntimeError):
    pass


@dataclass
class LoginResult:
    credentials: Credentials
    message: str


def login(
    username: str,
    password: str,
    dom_id: str = "guanbi",
    *,
    show_sensitive: bool = False,
) -> LoginResult:
    """跑完整登录链路并把凭证写入 ~/.anta_scrap/credentials.json。

    show_sensitive=True 时在异常里回显响应片段，便于排查。
    """
    with httpx.Client(
        follow_redirects=False,  # 手动跟，便于在每步抓 token
        timeout=30.0,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/150.0.0.0 Safari/537.36"
            ),
        },
    ) as cli:
        # 步骤 1：拉登录页，抓 execution
        service = _build_service_url()
        login_page_url = f"https://auth.anta.com/login?service={service}"
        page = cli.get(login_page_url)
        if page.status_code >= 400:
            raise LoginError(f"拉取登录页失败: {page.status_code} {page.text[:200]}")
        execution = _extract_execution(page.text)

        # loginTraceId：HAR 中是 32 位 hex；优先从 HTML 抓，抓不到随机生成
        login_trace_id = _extract_login_trace_id(page.text) or secrets.token_hex(16)

        # 步骤 2：POST 登录表单
        form = {
            "pVersion": "1.1",
            "pReadTime": "",
            "pStatus": "",
            "pSkip": "1",
            "execution": execution,
            "_eventId": "submit",
            "geolocation": "",
            "loginWay": "7",
            "clientId": "",
            "redirect_uri": "",
            "service": service,
            "dingLoginTmpCode": "",
            "username": username,
            "password": password,
            "captcha": "",
            "mobile": "",
            "clCaptcha": "",
            "smsCaptcha": "",
            "loginTraceId": login_trace_id,
        }
        login_resp = cli.post(
            login_page_url,
            data=form,
            headers={"Referer": login_page_url},
        )
        if login_resp.status_code not in (301, 302):
            raise LoginError(
                f"登录未跳转（status={login_resp.status_code}），"
                f"账号密码可能错误或触发验证码。"
                + (f"响应片段: {login_resp.text[:300]}" if show_sensitive else "")
            )
        callback_url = login_resp.headers["location"]
        if "ticket=" not in callback_url:
            raise LoginError(f"登录跳转缺少 ticket: {callback_url}")

        # 步骤 3：GET callbackAuthorize → 连续跳转 → datav.anta.com/?access_token=...
        #   callbackAuthorize 302 → /standard-oauth2/authenticate 302 → datav.anta.com/?access_token=...&refresh_token=...
        #   开启 follow_redirects 跟完整个跳转链，然后从最终 URL 解析 token
        with httpx.Client(
            follow_redirects=True,
            timeout=30.0,
            headers={
                "User-Agent": cli.headers["User-Agent"],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        ) as web:
            final = web.get(callback_url)
            final_url = str(final.url)

        parsed = urlparse(final_url)
        qs = parse_qs(parsed.query)
        access_token = _first(qs, "access_token")
        refresh_token = _first(qs, "refresh_token")
        if not access_token or not refresh_token:
            # 兜底：token 也可能落在 cookie 或响应体重定向里
            access_token = access_token or _cookie_token(web, "access_token")
            refresh_token = refresh_token or _cookie_token(web, "refresh_token")
        if not access_token or not refresh_token:
            raise LoginError(
                f"登录跳转链结束后未拿到 access_token/refresh_token。最终 URL: {final_url}"
            )

        # 步骤 4：访问 datav 首页，触发后端用 access_token 签发 JWT
        with httpx.Client(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": cli.headers["User-Agent"]},
        ) as web:
            home = web.get(f"https://datav.anta.com/?access_token={access_token}&provider=standardoauth2&refresh_token={refresh_token}")
            jwt = _extract_jwt_from_cookies(web) or _extract_jwt_from_html(home.text)

        if not jwt:
            raise LoginError(
                "登录后未能从首页拿到 JWT（cookie uIdToken 缺失）。"
                "可手动访问 https://datav.anta.com 并从 DevTools 复制 token header。"
            )

        user_id = base64.b64encode(username.encode()).decode()
        # HAR 验证：x-dom-id header 发的是 Base64(明文)，如 Z3VhbmJp = guanbi
        dom_id_b64 = base64.b64encode(dom_id.encode()).decode()
        creds = Credentials(
            access_token=access_token,
            refresh_token=refresh_token,
            jwt=jwt,
            user_id=user_id,
            dom_id=dom_id_b64,
            expires_at=_decode_jwt_exp(jwt),
        )

        # 步骤 5：校验
        save_credentials(creds, CREDENTIALS_FILE)
        _verify_token(creds)

        return LoginResult(
            credentials=creds,
            message=f"登录成功，JWT 有效期至 {creds.expires_at}，凭证已写入 {CREDENTIALS_FILE}",
        )


# ---------- 辅助 ----------


def _build_service_url() -> str:
    """构造 CAS service 参数（OAuth callback URL）。"""
    from urllib.parse import quote

    inner = (
        f"client_id={CLIENT_ID}"
        f"&redirect_uri={quote(REDIRECT_URI, safe='')}"
        "&response_type=code"
        f"&state={quote(STATE_DEFAULT, safe='')}"
        "&client_name=CasOAuthClient"
    )
    return quote(
        f"https://auth.anta.com/oauth2.0/callbackAuthorize?{inner}",
        safe="",
    )


def _extract_execution(html: str) -> str:
    """从登录页 HTML 抓 CAS execution token（name="execution" value="e1s1"）。"""
    m = re.search(r'name=["\']execution["\']\s+value=["\']([^"\']+)["\']', html)
    if m:
        return m.group(1)
    # 兜底：HAR 里固定 e1s1，但实际随 webflow 状态变化
    return "e1s1"


def _extract_login_trace_id(html: str) -> Optional[str]:
    m = re.search(r'loginTraceId["\']?\s*[:=]\s*["\']([0-9a-f]{32})["\']', html)
    return m.group(1) if m else None


def _first(qs: dict, key: str) -> Optional[str]:
    v = qs.get(key)
    return v[0] if v else None


def _extract_jwt_from_cookies(web: httpx.Client) -> Optional[str]:
    """从 cookie 拿 JWT。

    HAR 验证：datav 首页 set-cookie: uIdToken=<JWT>（httponly）。
    兜底其它常见名字。
    """
    for ck in web.cookies.jar:
        if ck.name.lower() in ("uidtoken", "token", "jwt", "access_token"):
            if ck.value.count(".") == 2:  # JWT 形态
                return ck.value
    return None


def _cookie_token(web: httpx.Client, name: str) -> Optional[str]:
    """从 cookie 里取指定名字的值（用于 access_token/refresh_token 兜底）。"""
    for ck in web.cookies.jar:
        if ck.name == name:
            return ck.value
    return None


def _extract_jwt_from_html(html: str) -> Optional[str]:
    """首页 JS 可能把 JWT 注入 window.__INITIAL_STATE__ 之类。"""
    m = re.search(r'["\']token["\']\s*:\s*["\']([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)["\']', html)
    return m.group(1) if m else None


def _decode_jwt_exp(jwt: str) -> Optional[float]:
    """从 JWT payload 解 exp（不验签，仅读过期时间）。"""
    try:
        payload_b64 = jwt.split(".")[1]
        # 补 padding
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = base64.urlsafe_b64decode(payload_b64).decode("utf-8")
        import json

        data = json.loads(payload)
        exp = data.get("exp")
        return float(exp) if exp else None
    except Exception:
        return None


def _verify_token(creds: Credentials) -> None:
    """调 /api/validate-token 确认凭证可用，失败抛错。"""
    with httpx.Client(timeout=15.0) as cli:
        r = cli.get(
            "https://datav.anta.com/api/validate-token",
            headers={
                "token": creds.jwt,
                "user-id": creds.user_id,
                "x-dom-id": creds.dom_id,
                "Accept": "application/json",
            },
        )
        if r.status_code != 200:
            raise LoginError(f"validate-token 失败: {r.status_code} {r.text[:200]}")
