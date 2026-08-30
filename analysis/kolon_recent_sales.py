"""KOLON 最近两周流水分析 DAG（hamilton-report skill 用例，2026-08-16）。

数据源: out/kolon_recent*.csv（templates/kolon_recent_sales/daily.yaml 导出，
窗口 2026-08-02 ~ 2026-08-15，店 × 日颗粒）。复制自 skill 的 scripts/kolon_report.py 模板。

运行:
    PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe analysis/kolon_recent_sales.py
产物: reports/kolon_recent_sales.md

DAG 结构:
    csv_path ─→ raw_sales ─→ cleaned_sales ─→ daily_trend ─┬→ overall_attainment ─┐
                              │               ├→ seven_day_compare ──────────────┤
                              ├→ region_summary ─────────────────────────────────┤→ report_markdown
                              └→ store_top10 ────────────────────────────────────┤
                              ─→ overall_yoy / same_store_yoy ───────────────────┘
"""
import argparse
import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd
from hamilton import driver
from hamilton.function_modifiers import check_output, tag

NUMERIC_COLS = ["流水", "预算流水目标", "流水同期", "同店流水", "同店流水同期"]


def raw_sales(csv_path: str) -> pd.DataFrame:
    """读取 KOLON 最近两周 BI 导出 CSV（UTF-8 带 BOM）"""
    return pd.read_csv(csv_path, encoding="utf-8-sig")


def cleaned_sales(raw_sales: pd.DataFrame) -> pd.DataFrame:
    """清洗：日历日期转 datetime；数值列去千分位/百分号后转 float"""
    df = raw_sales.copy()
    df["日历日期"] = pd.to_datetime(df["日历日期"], errors="coerce")
    for col in NUMERIC_COLS:
        as_text = (
            df[col]
            .astype("string")
            .str.replace(",", "", regex=False)
            .str.replace("%", "", regex=False)
        )
        df[col] = pd.to_numeric(as_text, errors="coerce")
    return df


def daily_trend(cleaned_sales: pd.DataFrame) -> pd.DataFrame:
    """日走势：按日汇总流水/目标/同期，含日环比与同比"""
    trend = (
        cleaned_sales.groupby("日历日期", as_index=False)[
            ["流水", "预算流水目标", "流水同期"]
        ]
        .sum()
        .sort_values("日历日期")
        .reset_index(drop=True)
    )
    trend["环比"] = trend["流水"].pct_change()
    trend["同比"] = trend["流水"] / trend["流水同期"].replace(0, pd.NA) - 1
    return trend


def seven_day_compare(daily_trend: pd.DataFrame) -> pd.DataFrame:
    """窗口对半分前 7 天 / 近 7 天对比（14 天窗口下即 08-02~08-08 vs 08-09~08-15）"""
    dates = pd.DatetimeIndex(daily_trend["日历日期"].unique()).sort_values()
    mid = dates[len(dates) // 2]  # 后半段起点

    def _agg(df: pd.DataFrame, label: str) -> dict[str, object]:
        sales = df["流水"].sum()
        target = df["预算流水目标"].sum()
        prior = df["流水同期"].sum()
        return {
            "时段": label,
            "流水": sales,
            "预算流水目标": target,
            "达成率": sales / target if target else np.nan,
            "同比": sales / prior - 1 if prior else np.nan,
        }

    out = pd.DataFrame(
        [
            _agg(daily_trend[daily_trend["日历日期"] < mid], f"前7天({dates[0]:%m-%d}~{mid - pd.Timedelta(days=1):%m-%d})"),
            _agg(daily_trend[daily_trend["日历日期"] >= mid], f"近7天({mid:%m-%d}~{dates[-1]:%m-%d})"),
        ]
    )
    out["环比"] = out["流水"].pct_change()
    return out


@tag(owner="bi", grain="region")
def region_summary(cleaned_sales: pd.DataFrame) -> pd.DataFrame:
    """区域汇总：流水、目标、达成率、同比、同店同比；按流水降序"""
    agg = cleaned_sales.groupby("区域", as_index=False).agg(
        流水=("流水", "sum"),
        预算流水目标=("预算流水目标", "sum"),
        流水同期=("流水同期", "sum"),
        同店流水=("同店流水", "sum"),
        同店流水同期=("同店流水同期", "sum"),
    )
    agg["达成率"] = agg["流水"] / agg["预算流水目标"].replace(0, pd.NA)
    agg["同比"] = agg["流水"] / agg["流水同期"].replace(0, pd.NA) - 1
    agg["同店同比"] = agg["同店流水"] / agg["同店流水同期"].replace(0, pd.NA) - 1
    return agg.sort_values("流水", ascending=False).reset_index(drop=True)


def store_top10(cleaned_sales: pd.DataFrame) -> pd.DataFrame:
    """近两周门店流水 Top10（含所属区域）"""
    by_store = cleaned_sales.groupby(["店铺名称", "区域"], as_index=False)["流水"].sum()
    return by_store.nlargest(10, "流水").reset_index(drop=True)


@check_output(data_type=np.float64, range=(0.0, 10.0), importance="warn")
def overall_attainment(daily_trend: pd.DataFrame) -> float:
    """整体预算达成率 = 流水合计 / 目标合计（np.float64 以通过严格类型校验）"""
    target = daily_trend["预算流水目标"].sum()
    if pd.isna(target) or target == 0:
        return np.float64("nan")
    return np.float64(daily_trend["流水"].sum() / target)


def overall_yoy(cleaned_sales: pd.DataFrame) -> float:
    """整体同比 = 全窗口流水 / 流水同期 - 1"""
    prior = cleaned_sales["流水同期"].sum()
    if pd.isna(prior) or prior == 0:
        return np.float64("nan")
    return np.float64(cleaned_sales["流水"].sum() / prior - 1)


def same_store_yoy(cleaned_sales: pd.DataFrame) -> float:
    """同店同比 = 同店流水 / 同店流水同期 - 1"""
    prior = cleaned_sales["同店流水同期"].sum()
    if pd.isna(prior) or prior == 0:
        return np.float64("nan")
    return np.float64(cleaned_sales["同店流水"].sum() / prior - 1)


def report_markdown(
    daily_trend: pd.DataFrame,
    seven_day_compare: pd.DataFrame,
    region_summary: pd.DataFrame,
    store_top10: pd.DataFrame,
    overall_attainment: float,
    overall_yoy: float,
    same_store_yoy: float,
    csv_path: str,
    out_path: str,
) -> str:
    """汇总各节点结果生成 markdown 报告并写盘，返回报告全文"""
    report = "\n".join(
        [
            "# KOLON 流水分析（最近两周）",
            "",
            f"- 数据源: `{csv_path}`",
            f"- 窗口: {daily_trend['日历日期'].min():%Y-%m-%d} ~ {daily_trend['日历日期'].max():%Y-%m-%d}"
            f"（{len(daily_trend)} 天，店×日颗粒）",
            f"- 流水合计: {daily_trend['流水'].sum():,.0f}",
            f"- 总体预算达成率: **{overall_attainment:.1%}**，同比 **{overall_yoy:+.1%}**，同店同比 **{same_store_yoy:+.1%}**",
            "",
            "## 前 7 天 vs 近 7 天",
            _md_table(seven_day_compare, pct_cols=("达成率", "同比", "环比")),
            "",
            "## 日走势",
            _md_table(daily_trend, pct_cols=("环比", "同比")),
            "",
            "## 区域汇总",
            _md_table(region_summary, pct_cols=("达成率", "同比", "同店同比")),
            "",
            "## 门店流水 Top10",
            _md_table(store_top10),
            "",
        ]
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(report, encoding="utf-8")
    return report


def _md_table(
    df: pd.DataFrame,
    float_fmt: str = "{:,.1f}",
    pct_cols: tuple[str, ...] = (),
) -> str:
    """DataFrame → markdown 表（下划线前缀，Hamilton 不收录）"""

    def fmt(col: str, value: object) -> str:
        if pd.isna(value):
            return "-"
        if col in pct_cols:
            return f"{value:+.1%}" if col in ("环比", "同比", "同店同比") else f"{value:.1%}"
        if isinstance(value, pd.Timestamp):
            return f"{value:%m-%d}"
        if isinstance(value, float):
            return float_fmt.format(value)
        return str(value)

    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep = "|" + "|".join(["---"] * len(df.columns)) + "|"
    rows = [
        "| " + " | ".join(fmt(col, val) for col, val in row.items()) + " |"
        for _, row in df.iterrows()
    ]
    return "\n".join([header, sep, *rows])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KOLON 最近两周流水分析 DAG")
    parser.add_argument("--csv", default=None, help="输入 CSV；默认取 out/kolon_recent*.csv 最新一个")
    parser.add_argument("--out", default="reports/kolon_recent_sales.md", help="报告输出路径")
    parser.add_argument("--list-nodes", action="store_true", help="仅列出 DAG 全部节点")
    args = parser.parse_args()

    csv_path = args.csv
    if csv_path is None:
        candidates = sorted(glob.glob("out/kolon_recent*.csv"), key=os.path.getmtime)
        if not candidates:
            raise SystemExit("out/ 下没有 kolon_recent*.csv；先导出，或用 --csv 指定路径")
        csv_path = candidates[-1]

    import __main__  # noqa: F401 —— 单文件 dataflow：把当前模块对象交给 Hamilton

    dr = driver.Builder().with_modules(__main__).build()

    if args.list_nodes:
        for var in dr.list_available_variables():
            print(f"- {var.name}")
        raise SystemExit(0)

    results = dr.execute(
        ["report_markdown"],
        inputs=dict(csv_path=csv_path, out_path=args.out),
    )
    print(results["report_markdown"])
    print(f"报告已写入: {args.out}")
