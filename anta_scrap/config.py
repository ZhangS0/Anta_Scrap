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

# 项目内模板目录
TEMPLATES_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "out"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


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

    return {
        "retail_daily_descente": RetailDailyDescenteReport,
        "retail_daily_kolon": RetailDailyKolonReport,
    }


def get_report_class(name: str) -> Type:
    registry = get_report_registry()
    if name not in registry:
        raise KeyError(f"未知报表 '{name}'，可选: {list(registry)}")
    return registry[name]
