"""CAS + OAuth2 自动登录链路。

流程（实测验证，2026-08）：
  1. GET  datav /standard-oauth2/authenticate（无 code）
       → 303 到 CAS /oauth2.0/authorize，携带 datav 自己生成的 state（内嵌 token，
         authenticate 端点会校验；硬编码旧 state 会 500）
       → 302 到 CAS 登录页
  2. POST 登录表单（username/password/execution/...）
       → 跳转链：callbackAuthorize → authorize → datav authenticate?code=...
       → 303 到 datav.anta.com/?access_token=AT-xxx&refresh_token=RT-xxx
  3. GET  最终 URL → set-cookie: uIdToken=<JWT>（httponly）
  4. GET  /api/validate-token（带 JWT）→ 200 表示登录态 OK

全程用一个 httpx Client 共享 cookie（CAS 会话 TGC 等）。
"""

from __future__ import annotations

import base64
import re
import secrets
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from anta_scrap.auth.token_store import Credentials, save_credentials
from anta_scrap.config import CREDENTIALS_FILE

DATAV_AUTHORIZE_ENTRY = "https://datav.anta.com/standard-oauth2/authenticate"

# refresh_credentials 用的 CAS OAuth client 配置（HAR 固定值）
CLIENT_ID = "100068"
REDIRECT_URI = "https://datav.anta.com/standard-oauth2/authenticate"


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
        follow_redirects=False,  # 手动跟跳转，便于在每步抓 token / 定位失败点
        timeout=30.0,
        headers={
            "User-Agent": _DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    ) as web:
        # 步骤 1：从 datav 发起 OAuth，跟到 CAS 登录页
        r = _follow_redirects(web, web.get(DATAV_AUTHORIZE_ENTRY))
        if "auth.anta.com/login" not in str(r.url) or r.status_code >= 400:
            raise LoginError(
                f"OAuth 发起后未落到 CAS 登录页: {r.status_code} {r.url}"
                + (f" 响应片段: {r.text[:300]}" if show_sensitive else "")
            )
        login_page_url = str(r.url)
        execution = _extract_execution(r.text)
        # loginTraceId：HAR 中是 32 位 hex；优先从 HTML 抓，抓不到随机生成
        login_trace_id = _extract_login_trace_id(r.text) or secrets.token_hex(16)

        # 步骤 2：POST 登录表单，跟完整跳转链到 /?access_token=...
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
            "service": login_page_url,
            "dingLoginTmpCode": "",
            "username": username,
            "password": password,
            "captcha": "",
            "mobile": "",
            "clCaptcha": "",
            "smsCaptcha": "",
            "loginTraceId": login_trace_id,
        }
        login_resp = web.post(login_page_url, data=form, headers={"Referer": login_page_url})
        if login_resp.status_code not in (301, 302, 303):
            raise LoginError(
                f"登录未跳转（status={login_resp.status_code}），"
                f"账号密码可能错误或触发验证码。"
                + (f"响应片段: {login_resp.text[:300]}" if show_sensitive else "")
            )
        final = _follow_redirects(web, login_resp)
        final_url = str(final.url)

        qs = parse_qs(urlparse(final_url).query)
        access_token = _first(qs, "access_token")
        refresh_token = _first(qs, "refresh_token")
        if not access_token or not refresh_token:
            raise LoginError(
                f"登录跳转链结束后未拿到 access_token/refresh_token。"
                f"最终: {final.status_code} {final_url} "
                + (f"响应片段: {final.text[:200]}" if show_sensitive else "")
            )

        # 步骤 3：访问带 token 的首页，后端签发 JWT（cookie uIdToken，httponly）
        web.get(final_url)
        jwt = _extract_jwt_from_cookies(web)
        if not jwt:
            raise LoginError(
                "登录后未能从 cookie uIdToken 拿到 JWT。"
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
            username=username,
        )

        # 步骤 4：校验
        save_credentials(creds, username=username)
        if not verify_token(creds):
            raise LoginError("validate-token 失败：登录链路完成但凭证校验不通过")

        return LoginResult(
            credentials=creds,
            message=f"登录成功，JWT 有效期至 {creds.expires_at}，凭证已写入 {CREDENTIALS_FILE}",
        )


def refresh_credentials(creds: Credentials) -> Credentials:
    """用 refresh_token 续期：换新 access_token → 兑换新 JWT → 覆写凭证文件。

    CAS OAuth2 标准端点 POST /oauth2.0/token（grant_type=refresh_token）。
    HAR 里没有捕获过续期请求，此实现按协议标准编写；任何一步失败抛
    LoginError，调用方（AntaSession.ensure）回退为提示重新登录。
    """
    with httpx.Client(
        follow_redirects=False,
        timeout=30.0,
        headers={"User-Agent": _DEFAULT_USER_AGENT},
    ) as cli:
        resp = cli.post(
            "https://auth.anta.com/oauth2.0/token",
            data={
                "grant_type": "refresh_token",
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "refresh_token": creds.refresh_token,
            },
        )
    if resp.status_code != 200:
        raise LoginError(
            f"refresh_token 续期失败（token 端点 {resp.status_code}）: {resp.text[:200]}"
        )
    tokens = _parse_token_response(resp)
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token") or creds.refresh_token
    if not access_token:
        raise LoginError(f"token 端点响应里没有 access_token: {resp.text[:200]}")

    jwt = _exchange_jwt(access_token, refresh_token)
    if not jwt:
        raise LoginError("续期后未能从 datav 首页拿到 JWT（cookie uIdToken 缺失）。")

    new_creds = Credentials(
        access_token=access_token,
        refresh_token=refresh_token,
        jwt=jwt,
        user_id=creds.user_id,
        dom_id=creds.dom_id,
        expires_at=_decode_jwt_exp(jwt),
        username=creds.username,
    )
    save_credentials(new_creds, username=creds.username)
    if not verify_token(new_creds):
        raise LoginError("续期后 validate-token 失败：新 JWT 校验不通过")
    return new_creds


# ---------- 辅助 ----------


def _exchange_jwt(
    access_token: str,
    refresh_token: str,
    user_agent: Optional[str] = None,
) -> Optional[str]:
    """访问 datav 首页，触发后端用 access_token 签发 JWT（cookie uIdToken）。"""
    with httpx.Client(
        follow_redirects=True,
        timeout=30.0,
        headers={"User-Agent": user_agent or _DEFAULT_USER_AGENT},
    ) as web:
        home = web.get(
            "https://datav.anta.com/"
            f"?access_token={access_token}&provider=standardoauth2&refresh_token={refresh_token}"
        )
        return _extract_jwt_from_cookies(web) or _extract_jwt_from_html(home.text)


def _parse_token_response(resp: httpx.Response) -> dict:
    """解析 /oauth2.0/token 响应；CAS 可能返回 JSON 或 form-encoded 两种形态。"""
    ct = resp.headers.get("content-type", "")
    if "json" in ct:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    return {k: v[0] for k, v in parse_qs(resp.text).items()}


_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)


def _follow_redirects(web: httpx.Client, resp: httpx.Response, max_hops: int = 10) -> httpx.Response:
    """手动跟随 3xx 跳转链（兼容相对路径），返回第一个非 3xx 响应。"""
    for _ in range(max_hops):
        if resp.status_code not in (301, 302, 303, 307, 308):
            return resp
        loc = urljoin(str(resp.url), resp.headers["location"])
        resp = web.get(loc)
    return resp


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


def verify_token(creds: Credentials) -> bool:
    """调 /api/validate-token 确认凭证在服务端仍有效（200 = 有效）。"""
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
        return r.status_code == 200
