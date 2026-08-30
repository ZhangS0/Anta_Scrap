"""配置：路径常量、.env 加载、报表注册表。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Type

from dotenv import load_dotenv

# 项目根（pyproject.toml 所在目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 启动时加载项目根 .env
load_dotenv(PROJECT_ROOT / ".env")

# 用户级状态目录：凭证、模板缓存等
USER_HOME = Path(os.path.expanduser("~"))
ANTA_HOME = USER_HOME / ".anta_scrap"
ANTA_HOME.mkdir(parents=True, exist_ok=True)
CREDENTIALS_FILE = ANTA_HOME / "credentials.json"
# 账号密码本地存储（多用户，明文 0600）：{username: {"password": str, "dom_id": str}}
ACCOUNTS_FILE = ANTA_HOME / "accounts.json"

# 项目内模板目录
TEMPLATES_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "out"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# agent 反馈落盘目录（submit_feedback 工具写，按天 JSONL，不入库）
FEEDBACK_DIR = PROJECT_ROOT / "feedback"
FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)


def env(key: str, default: str | None = None) -> str | None:
    return os.getenv(key, default)


def env_required(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"环境变量 {key} 未设置，请检查 .env 文件")
    return val


# 报表注册表：report_name -> BaseReport 子类（延迟 import 避免循环依赖）
def get_report_registry() -> Dict[str, Type]:
    from anta_scrap.reports.retail_daily_descente import RetailDailyDescenteReport
    from anta_scrap.reports.retail_daily_kolon import RetailDailyKolonReport
    from anta_scrap.reports.channel_monthly_descente import ChannelMonthlyDescenteReport
    from anta_scrap.reports.channel_monthly_kolon import ChannelMonthlyKolonReport
    from anta_scrap.reports.r03_sales_stock_descente import R03SalesStockDescenteReport
    from anta_scrap.reports.r03_sales_stock_kolon import R03SalesStockKolonReport

    return {
        "retail_daily_descente": RetailDailyDescenteReport,
        "retail_daily_kolon": RetailDailyKolonReport,
        "channel_monthly_descente": ChannelMonthlyDescenteReport,
        "channel_monthly_kolon": ChannelMonthlyKolonReport,
        "r03_sales_stock_descente": R03SalesStockDescenteReport,
        "r03_sales_stock_kolon": R03SalesStockKolonReport,
    }


def get_report_class(name: str) -> Type:
    registry = get_report_registry()
    if name not in registry:
        raise KeyError(f"未知报表 '{name}'，可选: {list(registry)}")
    return registry[name]


def create_report_instance(name: str, client, username: Optional[str] = None):
    """创建报表实例，支持多用户页面自动发现

    Args:
        name: 报表名称
        client: BI客户端
        username: 用户名（用于页面自动发现）

    Returns:
        报表实例
    """
    report_class = get_report_class(name)
    return report_class(client, username=username)
