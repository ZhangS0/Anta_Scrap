"""anta_scrap —— 安踏 BI 抓取库。

公共入口：
    from anta_scrap import AntaSession
    from anta_scrap.reports.retail_daily import RetailDailyReport
"""

from anta_scrap.auth.session import AntaSession, PasswordRequired, SessionExpired, resolve_credentials
from anta_scrap.client import AntaClient

__all__ = [
    "AntaSession",
    "AntaClient",
    "SessionExpired",
    "PasswordRequired",
    "resolve_credentials",
]
__version__ = "0.1.0"
