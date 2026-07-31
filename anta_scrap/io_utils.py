"""把 Page 转成 DataFrame 并保存为 xlsx/csv。"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from anta_scrap.models import Page


def page_to_dataframe(page: Page):
    """Page.rows 是 [[{v:val},...], ...]，转成扁平 DataFrame。"""
    import pandas as pd

    columns = _extract_column_names(page)
    rows = [[(cell.get("v") if isinstance(cell, dict) else cell) for cell in row] for row in page.rows]
    return pd.DataFrame(rows, columns=columns)


def _extract_column_names(page: Page) -> List[str]:
    """从 column_defs 提取列名；找不到时用 col_0/col_1..."""
    names = []
    for i, cd in enumerate(page.column_defs or []):
        if isinstance(cd, dict):
            n = cd.get("name") or cd.get("alias") or cd.get("title") or cd.get("fdName")
            if n:
                names.append(n)
                continue
        names.append(f"col_{i}")
    # 长度对齐到数据列数
    if page.rows:
        n_cols = max(len(r) for r in page.rows)
        while len(names) < n_cols:
            names.append(f"col_{len(names)}")
    return names


def save_dataframe(df, out_path: Path) -> Path:
    """按扩展名自动选 xlsx 或 csv。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ext = out_path.suffix.lower()
    if ext == ".xlsx":
        df.to_excel(out_path, index=False)
    elif ext == ".csv":
        df.to_csv(out_path, index=False, encoding="utf-8-sig")  # utf-8-sig 让 Excel 正确显示中文
    else:
        raise ValueError(f"不支持的输出扩展名: {ext}（仅支持 .xlsx/.csv）")
    return out_path
