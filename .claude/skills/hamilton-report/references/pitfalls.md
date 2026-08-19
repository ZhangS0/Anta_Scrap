# pitfalls：排错对照（症状 → 原因 → 修法）

以下条目多为实测踩坑（标注 ✔ 的在示例开发中实际触发过）。

## 1. `NameError: name '__main__' is not defined` ✔

单文件 dataflow 里直接写 `with_modules(__main__)` 会 NameError——`__main__` 只是 `__name__`
字符串，拿模块对象必须显式 import：

```python
if __name__ == "__main__":
    import __main__
    from hamilton import driver
    dr = driver.Builder().with_modules(__main__).build()
```

## 2. `ValueError: Missing type hint for return value in function <名>` ✔

节点函数缺**返回值**类型注解，build 阶段直接报错。参数与返回值都必须注解；
发现「变量不存在」也先查注解。

## 3. `@check_output(data_type=pd.DataFrame)` 报 `No registered subclass ... available` ✔

默认校验器只支持**标量类型**（np.float64/np.int32/…），DataFrame/Series 不行。
DataFrame 校验用 pandera 插件；或把校验放在派生的 float 节点上。

## 4. 校验告警 `Requires data type: numpy.float64. Got data type: float` ✔

类型校验**严格匹配**：builtin `float` ≠ `np.float64`。返回值显式 `np.float64(...)`。

## 5. 首列名变成 `﻿日历日期` / KeyError 找不到列

BI 导出 CSV 是 UTF-8 **带 BOM**：`pd.read_csv(path, encoding="utf-8-sig")`（不是 utf-8）。

## 6. 控制台 `UnicodeEncodeError`（打印中文时）

Windows 控制台默认 GBK。跑脚本统一加前缀：
`PYTHONIOENCODING=utf-8 $PY xxx.py`（`$PY` 探测见 SKILL.md 环境引导：Linux 用 `.venv/bin/python`，Windows 用 `.venv/Scripts/python.exe`）。

## 7. BI CSV 数字解析成 NaN / 字符串

数值列可能是 `1,963`（千分位）、`30%`、`--`、空串。清洗模式见 data-io.md
（`astype("string")` → 去 `,`/`%` → `pd.to_numeric(errors="coerce")`）。
有的导出干脆无表头（如 page3.csv 是 `col_0..col_8`）：先 `head -2` 确认，必要时
`pd.read_csv(..., header=None, names=[...])` 手工命名。

## 8. 达成率/同比出现 `inf`

目标或同期为 0 的行（实测 kolon CSV 中预算目标有 247 行为 0/空）：除之前
`分母.replace(0, pd.NA)`，让结果为 NaN 而不是 inf。

## 9. 中文函数名/列名能不能用？

能——中文是合法 Python 标识符（PEP 3131），`def 流水合计(...)` 与 `agg(流水=(...))`
都合法。惯例：英文函数名 + 中文 docstring，列名保持中文原样。

## 10. 路径含空格/中文（`out/kolon_daily 2026-08-15 ....csv`）

bash 里必须双引号包路径；脚本内用 `pathlib.Path` 与 `glob.glob()`，默认取最新用
`max(glob(...), key=os.path.getmtime)`（参考 scripts/kolon_report.py）。

## 11. 装错包 / 可视化失败

- pip 包名是 **`apache-hamilton`**（`sf-hamilton` 是旧名）。
- DAG 出图（`dr.display_all_functions("dag.png")`）需要系统级 Graphviz（`dot -V` 检测），
  本机未装就跳过，不影响其他功能。

## 12. pandas 3.x 兼容性

apache-hamilton 1.90.0 + pandas 3.0.5 + Python 3.13 实测兼容（2026-08-16）。
若未来升级后报 pandas 相关错误，先 `pip install "pandas<3"` 回退并把版本记到 SKILL.md。
