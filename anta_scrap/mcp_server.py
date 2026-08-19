"""anta-scrap MCP 服务：streamable-http 常驻，暴露唯一导出工具 export_report。

登录+查询下沉到本服务：外网 agent 只传 账号 + 查询模板，服务端登录 → 导出 CSV →
返回 CSV 全文文本。多用户凭证：按账号分别缓存 JWT（~/.anta_scrap/credentials.json），
账号密码存 ~/.anta_scrap/accounts.json（明文 0600）；仅首次登录或登录失败时需传
password，日常只传 username。报表/字段说明在 skill（anta-bi）的 references/ 里。

启动：
  anta-mcp                          # 默认 0.0.0.0:8000，路径 /mcp
  anta-mcp --host 0.0.0.0 --port 8000

鉴权：设环境变量 ANTA_MCP_API_KEY 后，所有调用须带 `Authorization: Bearer <key>`；
未设置则本地开放（仅供内网/调试）。外网暴露必须设该变量并走 HTTPS。

依赖：mcp、httpx、pyyaml。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Mapping, Optional

import yaml
from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from anta_scrap.auth.login import LoginError
from anta_scrap.auth.session import PasswordRequired, SessionExpired, resolve_credentials
from anta_scrap.client import AntaAPIError, AntaClient
from anta_scrap.config import get_report_class, get_report_registry
from anta_scrap.export import download, poll_task, trigger_export
from anta_scrap.templates import TemplateError, template_to_params

API_KEY = os.environ.get("ANTA_MCP_API_KEY", "").strip()

mcp = MCPServer(
    name="anta_bi_mcp",
    title="安踏 BI 查询导出",
    instructions="唯一工具 export_report：登录安踏 BI 并按 YAML 模板导出 CSV，返回 CSV 全文文本。",
)


def _check_auth(headers: Optional[Mapping[str, str]]) -> Optional[str]:
    """校验共享 bearer token；返回 None 表示通过，否则返回错误信息串。"""
    if not API_KEY:
        return None
    auth = ""
    if headers:
        auth = next(
            (v for k, v in headers.items() if k.lower() == "authorization"), ""
        ) or ""
    if auth == f"Bearer {API_KEY}":
        return None
    return "未授权：缺少或错误的 Authorization 头（应为 Bearer <ANTA_MCP_API_KEY>）"


def _export_sync(
    username: str,
    password: str,
    dom_id: str,
    template_yaml: str,
    output_name: str,
) -> str:
    """同步导出链：登录 → 解析模板 → 触发 → 轮询 → 下载，返回 CSV 文本。"""
    creds = resolve_credentials(username, password or None, dom_id or None)
    client = AntaClient(creds)
    try:
        tpl = yaml.safe_load(template_yaml)
        if not isinstance(tpl, dict):
            raise TemplateError("模板不是合法的 YAML 字典")
        report_key = tpl.get("report")
        if not report_key:
            raise TemplateError("模板缺少 report 字段（如 retail_daily_kolon）")
        if report_key not in get_report_registry():
            raise TemplateError(
                f"未知报表 '{report_key}'，可选: {', '.join(sorted(get_report_registry()))}"
            )
        rpt = get_report_class(report_key)(client)
        params = template_to_params(rpt, tpl)
        task_id = trigger_export(rpt, params)
        status = poll_task(client, task_id)
        if status in ("FAILED", "ERROR", "FAILURE"):
            raise AntaAPIError(f"导出任务失败: status={status}")
        content, _ = download(client, task_id, output_name or params.card_name)
        return content.decode("utf-8-sig")
    finally:
        client.close()


@mcp.tool(
    name="export_report",
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def export_report(
    username: str,
    template_yaml: str,
    password: str = "",
    dom_id: str = "",
    output_name: str = "",
    ctx: Optional[Context] = None,
) -> str:
    """登录安踏 BI 并按 YAML 模板导出 CSV，返回 CSV 全文文本。

    Args:
        username: 安踏 BI 账号（工号）。日常调用仅传此项。
        template_yaml: 查询模板（YAML 字符串），含 report/rows/metrics/filters/dynamic_params/limit。
        password: 密码。仅首次登录或登录失败时传入；日常可省略，服务端用已存密码/缓存 JWT 自动恢复。
        dom_id: 域标识，默认 guanbi；一般不传。
        output_name: 导出文件名（不含扩展名），缺省取模板 card_name。

    Returns:
        CSV 全文文本（UTF-8）；失败时返回带指引的错误说明串。
    """
    err = _check_auth(ctx.headers if ctx else None)
    if err:
        return err
    try:
        return await asyncio.to_thread(
            _export_sync, username, password, dom_id, template_yaml, output_name
        )
    except PasswordRequired as e:
        return f"需要密码: {e}"
    except LoginError as e:
        return f"登录失败（账号密码可能错误或触发验证码）: {e}"
    except SessionExpired as e:
        return f"凭证失效: {e}"
    except TemplateError as e:
        return f"模板错误: {e}"
    except KeyError as e:
        return f"字段未找到（字段名需与 BI 逐字一致）: {e}"
    except AntaAPIError as e:
        return f"查询/导出失败: {e}"
    except Exception as e:  # 兜底，避免服务端异常静默吞掉
        return f"未知错误: {type(e).__name__}: {e}"


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="anta-mcp", description="安踏 BI MCP 服务（streamable-http）")
    p.add_argument("--host", default=os.environ.get("MCP_HTTP_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("MCP_HTTP_PORT", "8000")))
    p.add_argument("--path", default="/mcp", help="streamable-http 端点路径")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = _parse_args(argv)
    if not API_KEY:
        print(
            "[warn] 未设置 ANTA_MCP_API_KEY，服务以开放模式运行（仅限内网/调试）。"
            "外网暴露前请设置该环境变量并走 HTTPS。",
            file=sys.stderr,
        )
    mcp.run(transport="streamable-http", host=args.host, port=args.port, streamable_http_path=args.path)


if __name__ == "__main__":
    main()
