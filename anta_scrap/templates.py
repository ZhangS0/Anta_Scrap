"""YAML 模板加载：把 templates/*.yaml 翻译成 QueryParams。

模板 schema：
    report: retail_daily
    rows: [渠道品牌]
    metrics: [零售流水目标]
    filters:
      - { name: 渠道品牌, values: [DESCENTE] }
      - { name: 商品品牌, values: [迪桑特] }
    dynamic_params:
      开始日期-户外-R02: 2026-07-22
      结束日期-户外-R02: 2026-07-29
    limit: 50
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import yaml

from anta_scrap.config import TEMPLATES_DIR
from anta_scrap.models import DynamicParam, FilterItem, QueryParams
from anta_scrap.reports.base import BaseReport


class TemplateError(RuntimeError):
    pass


def find_template(name: str, templates_dir: Path = TEMPLATES_DIR) -> Path:
    """按名字找模板文件，支持 'foo' / 'foo.yaml'。"""
    candidates = [templates_dir / f"{name}.yaml", templates_dir / f"{name}.yml", templates_dir / name]
    for c in candidates:
        if c.exists():
            return c
    raise TemplateError(f"未找到模板 '{name}'，查找路径: {templates_dir}")


def load_template(name_or_path: str, templates_dir: Path = TEMPLATES_DIR) -> dict:
    """加载 YAML 并返回原始 dict。name_or_path 可以是名字或绝对路径。"""
    p = Path(name_or_path)
    if not p.is_absolute():
        p = find_template(name_or_path, templates_dir)
    with p.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise TemplateError(f"模板格式错误（应为 dict）: {p}")
    return data


def template_to_params(report: BaseReport, tpl: dict) -> QueryParams:
    """把模板 dict 转成 QueryParams，字段名运行时解析为 fdId。"""
    rows = [report.field(n) for n in tpl.get("rows", []) or []]
    columns = [report.field(n) for n in tpl.get("columns", []) or []]
    metrics = [report.field(n) for n in tpl.get("metrics", []) or []]

    filters = []
    for f in tpl.get("filters", []) or []:
        fd = report.field(f["name"])
        # 若报表定义了 FIELD_SOURCE_CDID，注入 sourceCdId（None.get 报错的关键）
        src_map = getattr(report, "FIELD_SOURCE_CDID", {}) or {}
        if fd.source_cd_id is None and f["name"] in src_map:
            fd.source_cd_id = src_map[f["name"]]
        filters.append(FilterItem(field=fd, values=list(f["values"])))

    dynamic_params = []
    # 报表级的动态参数定义（含 sourceCdId 等内部字段）
    dp_defs = getattr(report, "DYNAMIC_PARAMS", {}) or {}
    for dp_name, dp_value in (tpl.get("dynamic_params", {}) or {}).items():
        # YAML 会把 2026-07-22 解析成 datetime.date，转回字符串
        import datetime as _dt
        if isinstance(dp_value, (_dt.date, _dt.datetime)):
            dp_value = dp_value.strftime("%Y-%m-%d")
        if dp_name not in dp_defs:
            raise TemplateError(f"模板里的 dynamic_param '{dp_name}' 在报表中不存在，可选: {list(dp_defs)}")
        cfg = dp_defs[dp_name]
        dynamic_params.append(DynamicParam(
            dp_id=cfg["dpId"],
            name=dp_name,
            value=dp_value,
            value_type=cfg.get("valueType", "DATE"),
            source_cd_id=cfg.get("sourceCdId"),
        ))

    return QueryParams(
        rows=rows,
        columns=columns,
        metrics=metrics,
        filters=filters,
        dynamic_params=dynamic_params,
        limit=int(tpl.get("limit", 50)),
        offset=int(tpl.get("offset", 0)),
        card_name=tpl.get("card_name") or report.name,
    )
