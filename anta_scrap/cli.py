"""CLI 入口：anta-cli {login,fields,query,export}。

作为库的薄包装，所有逻辑都在 anta_scrap.* 模块里。
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from anta_scrap.auth.login import LoginError, login
from anta_scrap.auth.session import AntaSession, SessionExpired
from anta_scrap.config import OUTPUT_DIR, env, get_report_class
from anta_scrap.export import EXPORT_CSV, EXPORT_PIVOT, export_and_download
from anta_scrap.io_utils import page_to_dataframe, save_dataframe
from anta_scrap.paging import fetch_all, fetch_first_page, fetch_max_pages
from anta_scrap.templates import load_template, template_to_params


@click.group()
def main():
    """安踏 BI 抓取工具。"""


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


# ---------- fields ----------

@main.command()
@click.option("-r", "--report", default="retail_daily_descente", help="报表名（默认 retail_daily_descente）")
def fields(report):
    """列出报表可选字段和动态参数。"""
    try:
        with AntaSession.ensure() as sess:
            cls = get_report_class(report)
            rpt = cls(sess.client)
            buckets = rpt.dump_fields()
            click.echo("=== 维度字段 ===")
            for n in buckets["dimensions"]:
                click.echo(f"  {n}")
            click.echo("=== 指标字段 ===")
            for n in buckets["metrics"]:
                click.echo(f"  {n}")
            if buckets["others"]:
                click.echo("=== 其它 ===")
                for n in buckets["others"]:
                    click.echo(f"  {n}")
            click.echo("=== 动态参数（日期等）===")
            for dp in rpt.dump_dynamic_params():
                click.echo(f"  {dp['name']}  (type={dp['valueType']}, default={dp['defaultValue']})")
    except SessionExpired as e:
        click.echo(str(e), err=True)
        sys.exit(1)


main.add_command(fields, name="fields")


# ---------- query ----------

@main.command()
@click.option("-r", "--report", default="retail_daily")
@click.option("-t", "--template", default="retail_daily_descente.default", help="模板名或路径")
@click.option("--all", "fetch_all_", is_flag=True, help="翻页拉全部")
@click.option("--max-pages", type=int, default=None, help="最多翻几页")
@click.option("--limit", type=int, default=50, help="每页条数")
@click.option("-o", "--output", type=click.Path(), help="输出文件（.xlsx/.csv）；不传则打印前几行")
def query(report, template, fetch_all_, max_pages, limit, output):
    """按模板查询数据。默认只读第 1 页。"""
    try:
        with AntaSession.ensure() as sess:
            cls = get_report_class(report)
            rpt = cls(sess.client)
            tpl = load_template(template)
            params = template_to_params(rpt, tpl)
            params.limit = limit

            if fetch_all_:
                page = fetch_all(rpt, params)
            elif max_pages:
                page = fetch_max_pages(rpt, params, max_pages)
            else:
                page = fetch_first_page(rpt, params)

            click.echo(page.summary)
            if output:
                df = page_to_dataframe(page)
                out = save_dataframe(df, Path(output))
                click.echo(f"已写入 {out}（{len(df)} 行）")
            else:
                df = page_to_dataframe(page)
                click.echo(df.head(20).to_string())
    except SessionExpired as e:
        click.echo(str(e), err=True)
        sys.exit(1)


main.add_command(query, name="query")


# ---------- export ----------

@main.command()
@click.option("-r", "--report", default="retail_daily_descente")
@click.option("-t", "--template", default="retail_daily_descente.default")
@click.option("--format", "fmt", type=click.Choice(["xlsx", "csv", "df"]), default="xlsx")
@click.option("--name", "download_name", default=None, help="下载文件名（不含扩展名）")
@click.option("-o", "--out-dir", type=click.Path(), default=str(OUTPUT_DIR))
def export(report, template, fmt, download_name, out_dir):
    """导出数据。xlsx/csv 异步导出并保存，df 模式通过 CSV 转换输出到 stdout。"""
    try:
        with AntaSession.ensure() as sess:
            # 先加载模板获取报表名称
            tpl = load_template(template)
            report_name = tpl.get("report", report)
            cls = get_report_class(report_name)
            rpt = cls(sess.client)
            params = template_to_params(rpt, tpl)

            if fmt == "df":
                # DataFrame 模式：下载 CSV 后转换为 DataFrame，输出到 stdout
                import pandas as pd
                import tempfile
                type_op = EXPORT_CSV
                # 下载到临时文件
                with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp:
                    tmp_path = Path(tmp.name)
                out = export_and_download(
                    rpt, params, type_op,
                    out_dir=tmp_path.parent,
                    download_file_name=tmp_path.stem,
                )
                # 读取为 DataFrame
                df = pd.read_csv(out, encoding='utf-8-sig')
                # 输出 DataFrame 信息（用于程序化调用时解析）
                click.echo(f"DATAFRAME: {len(df)} rows x {len(df.columns)} columns")
                click.echo(f"COLUMNS: {','.join(df.columns)}")
                # 以 CSV 格式输出到 stdout（可被其他程序捕获）
                df.to_csv(sys.stdout, index=False, encoding='utf-8-sig')
                # 删除临时文件
                out.unlink()
            else:
                # xlsx/csv 异步导出
                type_op = EXPORT_PIVOT if fmt == "xlsx" else EXPORT_CSV
                out = export_and_download(
                    rpt, params, type_op,
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
