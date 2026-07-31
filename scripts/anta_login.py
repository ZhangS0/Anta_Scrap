"""独立登录脚本：从 .env 读账号密码，跑登录链路，写凭证。

用法：
    python scripts/anta_login.py                # 用 .env 里的账号密码
    python scripts/anta_login.py -u <工号A> -p ***  # 命令行覆盖
"""

from __future__ import annotations

import sys
from pathlib import Path

# 让脚本无需 pip install 也能直接跑
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click

from anta_scrap.auth.login import LoginError, login
from anta_scrap.config import env, env_required


@click.command()
@click.option("-u", "--username", default=lambda: env("ANTA_USERNAME"))
@click.option("-p", "--password", default=lambda: env("ANTA_PASSWORD"))
@click.option("--dom-id", default=lambda: env("ANTA_DOM_ID", "guanbi"))
@click.option("--show-sensitive", is_flag=True, help="异常时回显响应片段（含敏感信息）")
def main(username, password, dom_id, show_sensitive):
    if not username or not password:
        click.echo("缺少账号或密码：请在 .env 设置 ANTA_USERNAME / ANTA_PASSWORD，或用 -u/-p 传入。")
        sys.exit(2)
    try:
        result = login(
            username=username,
            password=password,
            dom_id=dom_id,
            show_sensitive=show_sensitive,
        )
    except LoginError as e:
        click.echo(f"登录失败: {e}", err=True)
        sys.exit(1)
    click.echo(result.message)


if __name__ == "__main__":
    main()
