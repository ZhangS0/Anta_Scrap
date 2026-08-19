# data-io：数据进出与产物约定

## 取数两途

1. **`out/` 已有 CSV**：anta-bi 导出文件都在 `out/`（gitignore）。先 `head -2` 看表头再写节点。
2. **现导现用**：调 anta-bi MCP 工具 `export_report` 拿到 CSV 全文 → 落盘 `out/<名>.csv` → 进 DAG。
   字段怎么选、模板怎么写归 **anta-bi skill**（其 `metrics-glossary.md` 只 Grep，勿整读）。

BI 导出 CSV 特征（实测）：UTF-8 **带 BOM**；表头为中文列名；不同报表列集不同；
个别导出（如 page3.csv）无表头（`col_0..`）。

## 读入：节点内直接 pd.read_csv（官方惯用法，够用就别加装饰器）

```python
def raw_sales(csv_path: str) -> pd.DataFrame:
    """读取 BI 导出的原始 CSV（utf-8-sig 去 BOM）"""
    return pd.read_csv(csv_path, encoding="utf-8-sig")
```

路径需要由上游节点动态决定时才用声明式 `@load_from.csv(path=source("path_node"))`（见 decorators.md）。

## 清洗惯例

BI 数值列可能是文本形态（千分位 `1,963`、百分号 `30%`、占位 `--`/空），统一这么转：

```python
def cleaned_sales(raw_sales: pd.DataFrame) -> pd.DataFrame:
    """清洗：日期转 datetime，数值列转 float"""
    df = raw_sales.copy()                      # 不改上游节点输出
    df["日历日期"] = pd.to_datetime(df["日历日期"], errors="coerce")
    for col in ["流水", "预算流水目标"]:
        as_text = (
            df[col].astype("string")
            .str.replace(",", "", regex=False)
            .str.replace("%", "", regex=False)
        )
        df[col] = pd.to_numeric(as_text, errors="coerce")   # `--`/空 → NaN
    return df
```

除法防 0：目标列有 0/空（实测 kolon CSV 中 247 行）——`df["目标"].replace(0, pd.NA)` 再除。

## 产物约定（重要）

| 内容 | 位置 | 是否入库 |
|---|---|---|
| 分析 DAG 模块（.py 代码） | `analysis/<报告名>.py` | **入库** |
| 报告产物（.md / .xlsx） | `reports/` | 不入库（已 gitignore） |
| 原始/中间 CSV | `out/` | 不入库 |

- markdown 报告在终端节点函数里拼字符串并 `Path.write_text(..., encoding="utf-8")`，
  同时**返回报告全文**（终端节点也照常返回值，便于 execute 拿到）。
- 手写 markdown 表（参考 `scripts/kolon_report.py` 的 `_md_table`）；
  `df.to_markdown()` 需要额外装 `tabulate`，别依赖它。
- Excel：`df.to_excel(path, index=False)`，依赖 openpyxl（环境引导已装）。

## Materializer（进阶，可选）

想把"读文件/写文件"也变成 DAG 里可见的节点（获得元数据与可替换性）时用：

```python
from hamilton import driver
from hamilton.io.materialization import from_, to

dr = (
    driver.Builder()
    .with_modules(my_dag)
    .with_materializers(
        from_.csv(target="raw_sales", path="out/x.csv"),          # 替代 raw_sales 节点
        to.json(id="region_summary__json", dependencies=["region_summary"], path="reports/s.json"),
    )
    .build()
)
results = dr.execute(["region_summary__json"])
# 或不进 Builder、动态执行：metadata, results = dr.materialize(to.csv(...), additional_vars=[...])
```

简单分析报告用不到这层——节点内直接读写即可。

## 进阶（可选）

- **迭代加速（缓存）**：反复改报告节点重跑时，`driver.Builder().with_modules(m).with_cache().build()`
  可复用未变节点的结果。注意缓存按**源文件**做代码版本哈希——exec 出来的无源码模块会报
  `Unknown nodes`（实测），正常 `.py` 文件不受影响。
- **hamilton CLI**：另装 `typer` 后 `hamilton --help` 提供结构校验/出图子命令；本项目用
  `--list-nodes` 已覆盖校验需求。
- **hamilton-mcp**：venv 内的 `hamilton-mcp`（Linux: `.venv/bin/hamilton-mcp`，Windows: `.venv/Scripts/hamilton-mcp.exe`）可起本地 MCP 服务（validate/scaffold/
  execute 工具化，适合交互式调试）；本项目默认走脚本方式，需要时再接入 `.mcp.json`。
