"""anta-bi MCP 直连调用（JSON-RPC over streamable-http，仅标准库）。

「会话未注册 anta-bi MCP 服务器」时的逃生通道（2026-09-16 实测走通）：
平台客户端没注入 mcp_servers.json / `claude mcp add` 不可用时，直接对服务端
端点发 JSON-RPC initialize → tools/call，等价于 MCP 工具调用。

用法：
  python scripts/anta_mcp_call.py export_report --args '{"username": "1385118", "template_yaml": "..."}'
  python scripts/anta_mcp_call.py submit_feedback --args '{...}'

端点解析优先级：--url > 项目 .mcp.json（mcpServers["anta-bi"]）> http://127.0.0.1:8002/mcp
鉴权：透传 .mcp.json 里配置的 headers（如 Authorization: Bearer <ANTA_MCP_API_KEY>）。
输出：工具文本结果（CSV 全文）原样打到 stdout；错误串打到 stderr 并以非零码退出。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Union

DEFAULT_URL = "http://127.0.0.1:8002/mcp"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MCP_JSON = PROJECT_ROOT / ".mcp.json"

Json = Union[dict, list, str, int, float, bool, None]


def resolve_endpoint(url: Optional[str]) -> tuple[str, dict[str, str]]:
    """返回 (端点 URL, 附加 HTTP 头)。优先级：--url > .mcp.json > 默认本地。"""
    if url:
        return url, {}
    if MCP_JSON.exists():
        cfg = json.loads(MCP_JSON.read_text(encoding="utf-8"))
        srv = (cfg.get("mcpServers") or {}).get("anta-bi") or {}
        endpoint = srv.get("url")
        if endpoint:
            headers = {
                k: v
                for k, v in (srv.get("headers") or {}).items()
                if isinstance(k, str) and isinstance(v, str)
            }
            return endpoint, headers
    return DEFAULT_URL, {}


def _parse_sse(body: str) -> list:
    """解析 text/event-stream 响应，取出全部 data: 行的 JSON 消息。"""
    msgs = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            chunk = line[len("data:"):].strip()
            if chunk and chunk != "[DONE]":
                try:
                    msgs.append(json.loads(chunk))
                except json.JSONDecodeError:
                    pass
    return msgs


class McpDirectClient:
    """最小 streamable-http 客户端：initialize → notifications/initialized → tools/call。"""

    def __init__(self, endpoint: str, extra_headers: dict[str, str], timeout: float) -> None:
        self.endpoint = endpoint
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **extra_headers,
        }
        self.timeout = timeout
        self.session_id = ""
        self._next_id = 0

    def _post(self, payload: dict) -> Optional[Json]:
        req = urllib.request.Request(
            self.endpoint, data=json.dumps(payload).encode("utf-8"), method="POST"
        )
        for k, v in self.headers.items():
            req.add_header(k, v)
        if self.session_id:
            req.add_header("mcp-session-id", self.session_id)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            sid = resp.headers.get("mcp-session-id")
            if sid:
                self.session_id = sid
            ctype = resp.headers.get("content-type", "")
            body = resp.read().decode("utf-8")
        if "text/event-stream" in ctype:
            return _parse_sse(body)
        return json.loads(body) if body.strip() else None

    def rpc(self, method: str, params: Optional[dict] = None, *, notify: bool = False) -> Optional[dict]:
        """发一条 JSON-RPC；notify=True 为通知（无 id、不等待响应）。"""
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        resp_id: Optional[int] = None
        if not notify:
            self._next_id += 1
            resp_id = self._next_id
            msg["id"] = resp_id
        data = self._post(msg)
        if notify:
            return None
        msgs = data if isinstance(data, list) else [data]
        for m in msgs:
            if isinstance(m, dict) and m.get("id") == resp_id and ("result" in m or "error" in m):
                return m
        return None

    def initialize(self) -> None:
        resp = self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "anta-mcp-call", "version": "1.0"},
            },
        )
        if resp is None:
            raise RuntimeError("initialize 无响应（端点不是 streamable-http MCP 服务？）")
        if "error" in resp:
            raise RuntimeError(f"initialize 失败: {resp['error']}")
        self.rpc("notifications/initialized", notify=True)

    def call_tool(self, name: str, arguments: dict) -> tuple[str, bool]:
        """调用工具，返回 (文本, is_error)。"""
        resp = self.rpc("tools/call", {"name": name, "arguments": arguments})
        if resp is None:
            raise RuntimeError("tools/call 无响应")
        if "error" in resp:
            return f"MCP 错误: {resp['error']}", True
        result = resp.get("result") or {}
        content = result.get("content")
        if content is None and isinstance(result.get("data"), dict):
            # 兼容平台客户端落盘包裹形态 {data: {result: {content: [...]}}}
            content = (result["data"].get("result") or {}).get("content")
        texts = [c.get("text", "") for c in content or [] if isinstance(c, dict)]
        return "\n".join(t for t in texts), bool(result.get("isError"))


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="anta_mcp_call", description="anta-bi MCP 直连调用（会话未注册 MCP 时的逃生通道）"
    )
    p.add_argument("tool", help="工具名：export_report / submit_feedback")
    p.add_argument("--args", default="{}", help="工具参数 JSON 串，键见对应工具 docstring")
    p.add_argument("--url", default=None, help="MCP 端点（缺省读 .mcp.json，再缺省本地 8002）")
    p.add_argument("--timeout", type=float, default=600.0, help="单请求超时秒（导出耗时任务，默认 600）")
    ns = p.parse_args(argv)

    try:
        arguments = json.loads(ns.args)
        if not isinstance(arguments, dict):
            raise ValueError("--args 必须是 JSON 对象")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"参数错误: {e}", file=sys.stderr)
        return 2

    endpoint, extra_headers = resolve_endpoint(ns.url)
    client = McpDirectClient(endpoint, extra_headers, ns.timeout)
    try:
        client.initialize()
        text, is_error = client.call_tool(ns.tool, arguments)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        print(f"HTTP {e.code} 调用 {endpoint} 失败: {detail}", file=sys.stderr)
        return 1
    except Exception as e:  # 连接失败/协议错误统一兜底到 stderr
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if is_error:
        print(text, file=sys.stderr)
        return 1
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
