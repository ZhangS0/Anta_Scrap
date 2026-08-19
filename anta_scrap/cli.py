"""CLI 入口：anta-cli {login,export}。

作为库的薄包装，所有逻辑都在 anta_scrap.* 模块里。
唯一功能：按 YAML 模板导出 CSV（异步导出三步走）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from anta_scrap.auth.login import LoginError, login
from anta_scrap.auth.session import AntaSession, SessionExpired
from anta_scrap.config import OUTPUT_DIR, env, get_report_class
from anta_scrap.export import export_csv
from anta_scrap.templates import load_template, template_to_params


@click.group()
def main():
    """安踏 BI 抓取工具（模板 → CSV 导出）。"""


# ---------- login ----------

@main.command()
@click.option("-u", "--username", default=lambda: env("ANTA_USERNAME"))
@click.option("-p", "--password", default=lambda: env("ANTA_PASSWORD"))
@click.option("--dom-id", default=lambda: env("ANTA_DOM_ID", "guanbi"))
@click.option("--show-sensitive", is_flag=True)
def login_cmd(username, password, dom_id, show_sensitive):
    """登录并把凭证写入 ~/.anta_scrap/credentials.json。"""
    if not username or not password:
        click.echo("缺少账号或密码（用 -u/-p 或在 .env 设置）。", err=True)
        sys.exit(2)
    try:
        result = login(username=username, password=password, dom_id=dom_id, show_sensitive=show_sensitive)
    except LoginError as e:
        click.echo(f"登录失败: {e}", err=True)
        sys.exit(1)
    click.echo(result.message)


# 兼容 click 的命令名注册
main.add_command(login_cmd, name="login")


# ---------- export ----------

@main.command()
@click.option("-r", "--report", default=None, help="报表名（默认取模板里的 report 字段）")
@click.option("-t", "--template", default="retail_daily_descente.default", help="模板名或路径")
@click.option("--name", "download_name", default=None, help="下载文件名（不含扩展名）")
@click.option("-o", "--out-dir", type=click.Path(), default=str(OUTPUT_DIR))
def export(report, template, download_name, out_dir):
    """按模板异步导出 CSV 并保存到本地。"""
    try:
        with AntaSession.ensure() as sess:  # ensure 内部自动校验/续期凭证
            tpl = load_template(template)
            cls = get_report_class(report or tpl.get("report"))
            rpt = cls(sess.client)
            params = template_to_params(rpt, tpl)
            out = export_csv(
                rpt, params,
                out_dir=Path(out_dir),
                download_file_name=download_name or params.card_name,
            )
            click.echo(f"已导出: {out}")
    except SessionExpired as e:
        click.echo(str(e), err=True)
        sys.exit(1)


main.add_command(export, name="export")


if __name__ == "__main__":
    main()
