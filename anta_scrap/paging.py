"""分页策略：默认第一页 / 全量 / 最多 N 页。"""

from __future__ import annotations

import time
from typing import List, Tuple

from anta_scrap.models import Page, QueryParams
from anta_scrap.reports.base import BaseReport

# 翻页时的礼貌延迟（秒），避免触发 BI 限流
PAGE_DELAY_SECONDS = 0.3


def fetch_first_page(report: BaseReport, base: QueryParams) -> Page:
    """默认行为：只取第 1 页，返回 Page。调用方可用 page.summary 提示用户。"""
    return report.query(base)


def fetch_all(report: BaseReport, base: QueryParams) -> Page:
    """翻页拉完所有数据，合并到一个 Page 返回（count/has_more 用末次响应）。"""
    return _paginate(report, base, max_pages=None)


def fetch_max_pages(report: BaseReport, base: QueryParams, max_pages: int) -> Page:
    """最多翻 max_pages 页；不足则全量。"""
    return _paginate(report, base, max_pages=max_pages)


def _paginate(report: BaseReport, base: QueryParams, max_pages=None) -> Page:
    offset = 0
    merged_rows: List[List] = []
    column_defs: List[dict] = []
    last: Page = None
    page_no = 0
    while True:
        page_no += 1
        params = QueryParams(**{**base.__dict__, "offset": offset})
        page = report.query(params)
        last = page
        if page_no == 1:
            column_defs = page.column_defs
        merged_rows.extend(page.rows)
        if not page.has_more:
            break
        if max_pages is not None and page_no >= max_pages:
            break
        offset += page.limit
        time.sleep(PAGE_DELAY_SECONDS)

    # 合并后的 Page：用末次的 count/limit，offset 归零，has_more 由是否提前 break 决定
    stopped_early = max_pages is not None and last.has_more and page_no >= max_pages
    return Page(
        rows=merged_rows,
        column_defs=column_defs,
        count=last.count,
        has_more=stopped_early,
        limit=last.limit,
        offset=0,
    )
