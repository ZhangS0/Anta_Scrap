"""底层 HTTP 客户端：封装 httpx，所有报表共用。

职责：
- 注入认证 header（token / user-id / x-dom-id）
- 401 自动触发 refresh_token 续期（由 AntaSession 完成）
- 提供轮询工具（导出任务用）
- 统一 JSON 解析与错误信息
"""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from anta_scrap.auth.token_store import Credentials


class AntaAPIError(RuntimeError):
    """BI API 返回非 2xx 或 result!=ok。"""


class AntaClient:
    BASE = "https://datav.anta.com"
    AUTH_BASE = "https://auth.anta.com"
    DEFAULT_TIMEOUT = 30.0

    def __init__(self, creds: Credentials, transport: Optional[httpx.BaseClient] = None):
        self._creds = creds
        self._client = httpx.Client(
            base_url=self.BASE,
            timeout=self.DEFAULT_TIMEOUT,
            follow_redirects=True,
            headers=self._auth_headers(),
        )

    def _auth_headers(self) -> dict:
        return {
            "token": self._creds.jwt,
            "user-id": self._creds.user_id,
            "x-dom-id": self._creds.dom_id,
            "Accept": "application/json, text/plain, */*",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
        }

    def update_credentials(self, creds: Credentials) -> None:
        """refresh 续期后，外部调此方法刷新 header。"""
        self._creds = creds
        for k, v in self._auth_headers().items():
            self._client.headers[k] = v

    @property
    def credentials(self) -> Credentials:
        return self._creds

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "AntaClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---------- HTTP 原语 ----------

    def get(self, path: str, params: Optional[dict] = None, **kw) -> httpx.Response:
        return self._request("GET", path, params=params, **kw)

    def post_json(self, path: str, body: Any, params: Optional[dict] = None, **kw) -> httpx.Response:
        return self._request("POST", path, params=params, json=body, **kw)

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        # 服务端校验 referer 防 CSRF，HAR 里所有 /api/* 都带 referer
        headers = kw.get("headers") or {}
        if not any(k.lower() == "referer" for k in headers):
            page_id = self._infer_page_id(path)
            headers["referer"] = (
                f"https://datav.anta.com/page/{page_id}" if page_id
                else "https://datav.anta.com/"
            )
        kw["headers"] = headers
        resp = self._client.request(method, path, **kw)
        # 401 由上层 AntaSession.handle_401 处理；其它非 2xx 抛错
        if resp.status_code == 401:
            return resp  # 让 session 层判断
        if resp.status_code >= 400:
            raise AntaAPIError(
                f"{method} {path} -> {resp.status_code}: {resp.text[:500]}"
            )
        return resp

    def _infer_page_id(self, path: str) -> Optional[str]:
        """对 /api/page/{page_id} 或 /api/card/{card_id}/data 返回上下文 page id。

        简化处理：返回 path 里第一个 ne 开头的 24 位 ID（datav 的 page_id 前缀）。
        card_id 前缀是 q，不能用作 page referer。
        """
        import re

        m = re.search(r"/(ne[0-9a-f]{22,})", path)
        return m.group(1) if m else None

    def get_json(self, path: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> Any:
        resp = self.get(path, params=params, headers=headers)
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            data = resp.json()
            _check_ok(data, path)
            return data
        return resp.content

    def post_json_ok(self, path: str, body: Any, params: Optional[dict] = None, headers: Optional[dict] = None) -> Any:
        resp = self.post_json(path, body, params=params, headers=headers)
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            data = resp.json()
            _check_ok(data, path)
            return data
        return resp.content  # 二进制（如导出文件）


def _check_ok(data: Any, path: str) -> None:
    """约定：BI API 返回 {result: 'ok', response: ...} 或 {code: 0, ...}。

    部分接口（如 /api/task/{id} 不带 raw-backend-response）直接返回
    {taskId, status, ...} 没有 result 字段，这种情况不算失败。
    """
    if isinstance(data, dict):
        # 凭证在服务端失效（本地 JWT 未到期也可能被作废，如被顶号/登出）
        if data.get("error_code") == 1018 or "Not Login" in str(data.get("error_message", "")):
            raise AntaAPIError(
                f"{path}: 凭证在服务端已失效（Not Login or token expired），"
                "请重跑 anta-cli login 或 python scripts/anta_login.py"
            )
        result = data.get("result")
        # result 可能是 "ok" 字符串，也可能是 dict（任务接口的 {success:True, exportPath:...}）
        if isinstance(result, str) and result not in ("ok", "OK"):
            raise AntaAPIError(f"{path} 返回失败: {data}")
        if isinstance(result, dict) and result.get("success") is False:
            raise AntaAPIError(f"{path} 返回失败: {data}")
        code = data.get("code")
        if code not in (None, 0, "0", "200"):
            raise AntaAPIError(f"{path} 返回失败: {data}")
        # 任务接口裸 schema（无 result 字段），用顶层 status 判断
        if result is None and "status" in data:
            st = data.get("status")
            if st in ("FAILED", "ERROR", "FAILURE"):
                raise AntaAPIError(f"{path} 任务失败: {data}")
