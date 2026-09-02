"""anta-scrap MCP 服务：streamable-http 常驻，暴露两个工具 export_report + submit_feedback。

登录+查询下沉到本服务：外网 agent 只传 账号 + 查询模板，服务端登录 → 导出 CSV →
返回 CSV 全文文本。多用户凭证：按账号分别缓存 JWT（~/.anta_scrap/credentials.json），
账号密码存 ~/.anta_scrap/accounts.json（明文 0600）；仅首次登录或登录失败时需传
password，日常只传 username。报表/字段说明在 skill（anta-bi）的 references/ 里；
新报表的连接知识由调用方模板内联 report_spec 携带（服务端免注册）。

submit_feedback：agent 端结构化使用反馈（skill 调用记录 / 字段口径笔记 / 报表要求 /
问题），按天追加到项目 feedback/ 目录（不入库），供维护者改进 skills 与字段指引。

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
from anta_scrap.auth.token_store import load_account
from anta_scrap.client import AntaAPIError, AntaClient
from anta_scrap.config import FEEDBACK_DIR, create_report_from_template
from anta_scrap.export import download, poll_task, trigger_export
from anta_scrap.templates import TemplateError, template_to_params

API_KEY = os.environ.get("ANTA_MCP_API_KEY", "").strip()

mcp = MCPServer(
    name="anta_bi_mcp",
    title="安踏 BI 查询导出",
    instructions=(
        "export_report：登录安踏 BI 并按 YAML 模板导出 CSV，返回 CSV 全文文本。"
        "submit_feedback：上报使用反馈（skill 调用/字段口径/报表要求/问题），格式见工具说明。"
    ),
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


# ---------- submit_feedback：agent 使用反馈回传 ----------

_FEEDBACK_CATEGORIES = ("skill_call", "field_note", "report_note", "issue")
_FEEDBACK_BODY_LIMIT = 32_000  # body 字符上限，超长截断


def _redact_secrets(username: str, text: str) -> str:
    """把该账号已存密码替换为 ***，避免明文落进反馈文件。"""
    acct = load_account(username) or {}
    secret = acct.get("password")
    if isinstance(secret, str) and secret.strip():
        text = text.replace(secret, "***")
    return text


def _submit_feedback_sync(
    username: str,
    category: str,
    title: str,
    body: str,
    context_json: str,
) -> str:
    """校验、脱敏后按天追加到 feedback/YYYY-MM-DD.jsonl，返回确认串。"""
    import datetime as _dt
    import json as _json

    if category not in _FEEDBACK_CATEGORIES:
        return f"category 无效: '{category}'，可选: {', '.join(_FEEDBACK_CATEGORIES)}"
    title = (title or "").strip()
    if not title:
        return "title 不能为空"
    body = (body or "").strip()
    if not body:
        return "body 不能为空：请用一句话写明关键结果/结论（返回行数、核心数字或解法），空摘要反馈无价值"
    context: dict = {}
    if (context_json or "").strip():
        try:
            context = _json.loads(context_json)
        except _json.JSONDecodeError as e:
            return f"context_json 不是合法 JSON: {e}"
        if not isinstance(context, dict):
            return "context_json 必须是 JSON 对象（如 {\"report\": \"retail_daily_kolon\"}）"
    if len(body) > _FEEDBACK_BODY_LIMIT:
        body = body[:_FEEDBACK_BODY_LIMIT] + f"\n...[截断，原长 {len(body)} 字符]"
    body = _redact_secrets(username, body)
    title = _redact_secrets(username, title)
    # context 嵌套字符串同样脱敏：序列化→替换→还原
    if context:
        context = _json.loads(
            _redact_secrets(username, _json.dumps(context, ensure_ascii=False))
        )

    line = {
        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
        "username": username,
        "category": category,
        "title": title,
        "body": body,
        "context": context,
    }
    path = FEEDBACK_DIR / f"{_dt.date.today().isoformat()}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(_json.dumps(line, ensure_ascii=False) + "\n")
    seq = sum(1 for _ in path.open(encoding="utf-8"))
    return f"已记录 (#{seq} {category}: {title[:40]}) → {path.name}"


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
        # dispatch：report_spec 块（通用执行器，新报表免注册）优先，其次内置 registry key 别名
        rpt = create_report_from_template(tpl, client, username=username)
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
        template_yaml: 查询模板（YAML 字符串），含 report（内置报表 key）或 report_spec（新报表
            连接 spec 块，从该报表指引「报表连接 spec」小节复制）+ rows/metrics/filters/dynamic_params/limit。
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


@mcp.tool(
    name="submit_feedback",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    ),
)
async def submit_feedback(
    username: str,
    category: str,
    title: str,
    body: str = "",
    context_json: str = "",
    ctx: Optional[Context] = None,
) -> str:
    """上报使用反馈（结构化摘要），供项目维护者改进 skills 与字段指引。检查点必调：
    每次查询导出后、报告任务交付后、遇到报错或用户提出特殊口径要求时。

    Args:
        username: 上报者工号（与 export_report 同一账号体系）。
        category: 四选一。
            - skill_call：skill/查询调用记录（title=报表名+动作；body=关键摘要；
              context 放 report/skill/template 摘要/rows 数/metrics 数/状态/耗时秒）
            - field_note：字段口径坑与特殊要求（静默丢指标、字段不可用、口径澄清）
            - report_note：报表级要求（筛选依赖、固定口径、格式偏好、新报表约定）
            - issue：报错现象与解决过程（含工具返回的错误串与最终解法）
        title: 一行标题（必填，≤40 字为宜），如 "retail_daily_kolon 导出成功 3500 行"。
        body: 摘要正文（必填，至少一句话；≤32k 字符，超长自动截断）。只写结论与关键数据
              （返回行数、核心数字或解法），**严禁包含密码、API key、全量对话转写**。
        context_json: 可选 JSON 对象字符串（必须形如 {} 的对象），放结构化上下文，
              常用键：report、skill、template_yaml、rows、metrics、status、run、duration_s。

    Returns:
        确认串（含当日序号与类别）；参数不合法时返回错误说明。
    """
    err = _check_auth(ctx.headers if ctx else None)
    if err:
        return err
    return await asyncio.to_thread(
        _submit_feedback_sync, username, category, title, body, context_json
    )


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
