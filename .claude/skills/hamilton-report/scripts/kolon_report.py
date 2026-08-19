"""KOLON 零售日报分析 DAG —— hamilton-report skill 的自检示例，也是新建分析 DAG 的复制模板。

数据源: out/kolon_daily*.csv（anta-bi skill / anta-mcp export_report 导出的 BI CSV，UTF-8 带 BOM）。
运行（项目根目录，bash）:
    PYTHONIOENCODING=utf-8 $PY .claude/skills/hamilton-report/scripts/kolon_report.py
    # $PY 探测（Linux 沙盒用 .venv/bin/python，Windows 用 .venv/Scripts/python.exe）:
    #   [ -x .venv/bin/python ] && PY=.venv/bin/python || PY=.venv/Scripts/python.exe
    # 变体: --list-nodes（列出自省） / --csv <路径>（换数据源） / --out <路径>（换输出）
产物: reports/kolon_report.md

Hamilton 模型速记（详见 references/quickstart.md）:
    函数名 = 节点/输出名，参数名 = 上游依赖（按名自动连线），docstring = 节点说明。
    csv_path / out_path 不是任何函数的输出 → 运行时输入，由 execute(inputs=...) 提供。

DAG 结构（DOT，箭头 = 数据流向；先画 DOT 再写代码，见 references/quickstart.md）:
    digraph kolon_report {
        csv_path [shape=box]; out_path [shape=box];
        csv_path -> raw_sales -> cleaned_sales;
        cleaned_sales -> daily_total;
        daily_total -> overall_attainment;
        cleaned_sales -> region_summary;
        cleaned_sales -> store_top10;
        csv_path -> report_markdown;
        out_path -> report_markdown;
        daily_total -> report_markdown;
        overall_attainment -> report_markdown;
        region_summary -> report_markdown;
        store_top10 -> report_markdown;
    }
"""
import argparse
import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd
from hamilton import driver
from hamilton.function_modifiers import check_output, tag

# BI 导出的数值列：可能带千分位/百分号/`--`，清洗时统一转 float
NUMERIC_COLS = ["流水", "预算流水目标", "流水同期", "同店流水", "同店流水同期"]


def raw_sales(csv_path: str) -> pd.DataFrame:
    """读取 BI 导出的原始 CSV（UTF-8 带 BOM，必须用 utf-8-sig）"""
    return pd.read_csv(csv_path, encoding="utf-8-sig")


def cleaned_sales(raw_sales: pd.DataFrame) -> pd.DataFrame:
    """清洗：日历日期转 datetime；数值列去千分位/百分号后转 float（`--` 等不可解析值 → NaN）"""
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


def daily_total(cleaned_sales: pd.DataFrame) -> pd.DataFrame:
    """按日汇总流水与预算流水目标"""
    return cleaned_sales.groupby("日历日期", as_index=False)[
        ["流水", "预算流水目标"]
    ].sum()


@tag(owner="bi", grain="region")
def region_summary(cleaned_sales: pd.DataFrame) -> pd.DataFrame:
    """区域维度汇总：流水、目标、达成率（目标为 0/空 → NaN）、同比；按流水降序"""
    agg = cleaned_sales.groupby("区域", as_index=False).agg(
        流水=("流水", "sum"),
        预算流水目标=("预算流水目标", "sum"),
        流水同期=("流水同期", "sum"),
    )
    agg["达成率"] = agg["流水"] / agg["预算流水目标"].replace(0, pd.NA)
    agg["同比"] = agg["流水"] / agg["流水同期"].replace(0, pd.NA) - 1
    return agg.sort_values("流水", ascending=False).reset_index(drop=True)


def store_top10(cleaned_sales: pd.DataFrame) -> pd.DataFrame:
    """门店流水 Top10"""
    by_store = cleaned_sales.groupby("店铺名称", as_index=False)["流水"].sum()
    return by_store.nlargest(10, "流水").reset_index(drop=True)


@check_output(data_type=np.float64, range=(0.0, 10.0), importance="warn")
def overall_attainment(daily_total: pd.DataFrame) -> float:
    """整体预算达成率 = 流水合计 / 目标合计（区间累计口径；目标缺失 → NaN）

    注意: @check_output 的默认校验器只支持标量类型（np.float64/np.int32/…），
    data_type=pd.DataFrame 会直接报 ValueError——DataFrame 校验需用 pandera 插件。
    """
    sales = daily_total["流水"].sum()
    target = daily_total["预算流水目标"].sum()
    if pd.isna(target) or target == 0:
        return np.float64("nan")
    # 返回 np.float64 而非 builtin float：@check_output 的类型校验是严格匹配
    return np.float64(sales / target)


def report_markdown(
    region_summary: pd.DataFrame,
    store_top10: pd.DataFrame,
    daily_total: pd.DataFrame,
    overall_attainment: float,
    csv_path: str,
    out_path: str,
) -> str:
    """汇总各节点结果生成 markdown 报告并写盘，返回报告全文"""
    report = "\n".join(
        [
            "# KOLON 零售日报分析报告",
            "",
            f"- 数据源: `{csv_path}`",
            f"- 日期区间: {daily_total['日历日期'].min():%Y-%m-%d} ~ {daily_total['日历日期'].max():%Y-%m-%d}",
            f"- 流水合计: {daily_total['流水'].sum():,.1f}",
            f"- 预算目标合计: {daily_total['预算流水目标'].sum():,.1f}",
            f"- 总体预算达成率: {overall_attainment:.1%}",
            "",
            "## 区域汇总",
            _md_table(region_summary, pct_cols=("达成率", "同比")),
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
    """DataFrame → markdown 表（手写实现，避免 to_markdown 的 tabulate 依赖）。

    下划线前缀的函数不会被 Hamilton 收录为节点。
    """

    def fmt(col: str, value: object) -> str:
        if pd.isna(value):
            return "-"
        if col in pct_cols:
            return f"{value:.1%}"
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
    parser = argparse.ArgumentParser(
        description="KOLON 零售日报分析 DAG（hamilton-report skill 示例）"
    )
    parser.add_argument("--csv", default=None, help="输入 CSV；默认取 out/kolon_daily*.csv 最新一个")
    parser.add_argument("--out", default="reports/kolon_report.md", help="报告输出路径")
    parser.add_argument(
        "--list-nodes", action="store_true", help="仅列出 DAG 全部节点（Driver 自省演示）"
    )
    args = parser.parse_args()

    csv_path = args.csv
    if csv_path is None:
        candidates = sorted(glob.glob("out/kolon_daily*.csv"), key=os.path.getmtime)
        if not candidates:
            raise SystemExit("out/ 下没有 kolon_daily*.csv；先用 anta-bi skill 导出，或用 --csv 指定路径")
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
