# decorators：函数修饰器速查

全部来自 `from hamilton.function_modifiers import ...`。多个装饰器可叠加，自下而上生效。

## 速查表

| 装饰器 | 用途 | 示例 |
|---|---|---|
| `@tag` | 给节点挂元数据（不影响计算） | `@tag(owner="bi", grain="region")` |
| `@schema.output` | 声明输出 DataFrame 列 schema（仅元数据） | `@schema.output(("流水", float), ("目标", float))` |
| `@check_output` | 输出数据校验 | `@check_output(data_type=np.float64, range=(0, 10), importance="warn")` |
| `@extract_columns` | 把 DataFrame 节点输出拆成多个列节点 | `@extract_columns("流水", "预算流水目标")` |
| `@parameterize` | 一个函数生成多个节点 | 见下 |
| `@parameterize_values` / `@parameterize_sources` | `@parameterize` 简化版（只变常量 / 只变来源） | 见下 |
| `@config.when` 系列 | 按 config 选择加载哪个变体函数 | 见下 |
| `@load_from.csv` / `.json` | 声明式读外部文件 | `@load_from.csv(path=source("csv_path"))` |
| `@save_to.csv` | 节点结果顺带落盘 | `@save_to.csv(path="out/x.csv", output_name_="raw_df")` |
| `@dataloader()` / `@datasaver()` | 自定义可复用 IO 适配器 | 进阶，一般用不到 |

## @parameterize（一函数多节点）

`source()` 引用数据流中其他节点的输出，`value()` 传编译期常量；docstring 里的 `{占位符}` 会被插入：

```python
from hamilton.function_modifiers import parameterize, source, value

@parameterize(
    revenue_by_region=dict(df=source("cleaned_sales"), groupby_col=value("区域")),
    revenue_by_province=dict(df=source("cleaned_sales"), groupby_col=value("省份")),
)
def dimension_summary(df: pd.DataFrame, groupby_col: str) -> pd.DataFrame:
    """按 {groupby_col} 汇总流水"""
    return df.groupby(groupby_col, as_index=False)["流水"].sum()
```

只变常量时用简化版 `@parameterize_values(parameter="groupby_col", assigned_output={"按区域": "区域", "按省份": "省份"})`。

## @config.when（按配置切换实现）

同一逻辑多个实现的场景（如开发读 CSV / 生产读库）。变体函数名加**双下划线后缀**，加载后缀自动去掉，图中只有基名：

```python
@config.when(env="dev")
def base_df__csv(csv_path: str) -> pd.DataFrame:
    """开发环境：读本地 CSV"""
    return pd.read_csv(csv_path, encoding="utf-8-sig")


@config.when_not(env="dev")
def base_df__db(conn_str: str) -> pd.DataFrame:
    """其他环境：读数据库"""
    ...

# 运行侧：
dr = driver.Builder().with_modules(mod).with_config({"env": "dev"}).build()
dr.execute(["base_df"], ...)   # 请求基名，不是 base_df__csv
```

同族：`@config.when_not(key=...)`、`@config.when_in(key=[...])`、`@config.when_not_in(key=[...])`。

## @check_output（输出校验，实测两条硬约束）

```python
import numpy as np
from hamilton.function_modifiers import check_output

@check_output(data_type=np.float64, range=(0.0, 10.0), importance="warn")
def overall_attainment(daily_total: pd.DataFrame) -> float:
    """达成率：必须在 0~10 之间"""
    ...
```

- `importance="warn"` 校验失败只打日志；`"fail"` 直接中断执行。
- **约束 1**：`data_type` 默认校验器**只支持标量类型**（`np.float64`/`np.int32` 等），
  传 `pd.DataFrame`/`pd.Series` 会在 build 时 `ValueError`。DataFrame 校验用 pandera 插件
  （`pip install "apache-hamilton[pandera]"` 后 `@check_output(schema=...)`）。
- **约束 2**：类型校验是**严格匹配**——函数返回 builtin `float` 而 `data_type=np.float64`
  会告警不匹配。返回值显式转 `np.float64(...)`。
- 校验器会在 `list_available_variables()` 里展开成 `<节点>_raw` 与 `<节点>_<校验器名>` 节点，正常现象。

## @extract_columns（拆列）

```python
from hamilton.function_modifiers import extract_columns

@extract_columns("流水", "预算流水目标")
def cleaned_sales(raw_sales: pd.DataFrame) -> pd.DataFrame:
    """清洗后的明细（列可作为独立节点被下游引用）"""
    ...
```

下游可写 `def total(sales: pd.Series) -> float`（参数名 = 列名）。**注意**：拆出的列节点名
若与已有函数同名会冲突——模块内所有输出名必须全局唯一。

## @load_from / @save_to（声明式 IO）

```python
from hamilton.function_modifiers import load_from, save_to, source

@load_from.csv(path=source("csv_path"))        # path 可来自上游节点，运行时再定
def cleaned_sales(raw_df: pd.DataFrame) -> pd.DataFrame:
    """清洗（raw_df 由 loader 注入）"""
    ...

@save_to.csv(path="out/clean.csv", output_name_="cleaned_to_csv")
def cleaned_sales(...)   # output_name_ 是落盘节点的请求名
```

路径固定、场景简单时，直接在节点里 `pd.read_csv()` / `to_csv()` 更直白（见 data-io.md）。
