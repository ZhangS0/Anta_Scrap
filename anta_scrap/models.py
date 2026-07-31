"""数据模型：QueryParams / FieldDef / Page。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class FieldDef:
    """一个可被选入 row/column/metric 的字段。

    raw 是从报表元数据抠出的完整 zone item 字典；构造 payload 时透传 raw，
    避免 BI 后端因缺字段报错（HAR 验证 metric item 含 fieldFormat/alias 等必要字段）。
    """

    fd_id: str
    name: str  # 用户可读名
    fd_type: str  # STRING / DOUBLE / DATE ...
    meta_type: str  # DIM / METRIC / MPH ...
    key: Optional[str] = None
    aggr_type: Optional[str] = None  # SUM / AVG ...（仅 metric）
    ds_id: Optional[str] = None  # 数据集 ID（filter 需要）
    source_cd_id: Optional[str] = None  # 来源 card ID（filter 需要）
    raw: Optional[dict] = None  # 元数据里的原始字典

    def to_zone_item(self) -> dict:
        """构造 zoneFilter.zoneData.{row/column/metric}[] 里的一项。

        策略：透传 raw（若来自 chartMain.zoneData 已是配置态，含全部 metric 必备字段），
        否则用 FieldDef 属性拼最小项，并按 HAR 默认值补全 key/aggrType/fieldFormat。
        raw 来自 dsInfos.columns（字段池）时剔除 dsId/seqNo/fdGroupId 等。
        """
        # dsInfos.columns 里需要剔除的键（HAR zone item 里没有这些）
        DROP_KEYS = {"baseFdType", "seqNo", "fdGroupId", "hidden",
                     "isDetectionSensitive", "isSensitive"}

        if self.raw:
            # 判断是否已是"配置态"（含 calculationType）
            is_configured = "calculationType" in self.raw
            if is_configured:
                item = dict(self.raw)
            else:
                item = {k: v for k, v in self.raw.items() if k not in DROP_KEYS}
        else:
            item = {
                "fdId": self.fd_id,
                "name": self.name,
                "fdType": self.fd_type,
                "metaType": self.meta_type,
                "level": "dataset",
            }

        if not is_configured:
            # 通用补全（仅对未配置态）
            item.setdefault("isAggregated", False)
            item.setdefault("calculationType", "normal")
            item.setdefault("level", "dataset")
            item.setdefault("annotation", "")
            item.setdefault("key", self.key or _gen_key())
            item.setdefault("nameTranslated", self.name)
            item.setdefault("alias", self.name)
            if self.meta_type == "METRIC":
                item.setdefault("aggrType", self.aggr_type or "SUM")
                item.setdefault("fieldFormat", _DEFAULT_METRIC_FORMAT)
        return item


def _gen_key() -> str:
    """生成 10 位 base62 key，模拟 HAR 里前端生成的字段 key。"""
    import random
    import string
    return "".join(random.choices(string.ascii_letters + string.digits, k=10))


_DEFAULT_METRIC_FORMAT = {
    "numberFormat": {
        "formatType": "NUMBER",
        "decimalPlaces": 2,
        "useThousandsSeparator": True,
        "showPrefixUnit": True,
        "suffix": "",
    },
    "conditionFormat": {"thresholdType": "SINGLE_COLOR"},
}


@dataclass
class FilterItem:
    """一个查询条件（IN 筛选）。"""

    field: FieldDef
    values: List[Any]  # 实际值，如 ["DESCENTE"]
    filter_type: str = "IN"

    def to_payload(self, card_id: str) -> dict:
        item = {
            "name": self.field.name,
            "fdId": self.field.fd_id,
            "cdId": card_id,
            "fdType": self.field.fd_type,
            "filterType": self.filter_type,
            "originFilterType": self.filter_type,
            "filterValue": self.values,
            "displayValue": self.values,
        }
        if self.field.ds_id:
            item["dsId"] = self.field.ds_id
        if self.field.source_cd_id:
            item["sourceCdId"] = self.field.source_cd_id
        return item


@dataclass
class DynamicParam:
    """日期等动态参数。"""

    dp_id: str
    name: str
    value: Any
    value_type: str = "DATE"
    source_cd_id: Optional[str] = None

    def to_payload(self) -> dict:
        item = {
            "dpId": self.dp_id,
            "name": self.name,
            "valueType": self.value_type,
            "defaultValue": self.value,
            "customize": False,
            "multiple": False,
            "optionValue": [""],
            "inheritParent": True,
            "missingRequiredValue": False,
        }
        if self.source_cd_id:
            item["sourceCdId"] = self.source_cd_id
        return item


@dataclass
class QueryParams:
    """一次查询的全部输入。"""

    rows: List[FieldDef] = field(default_factory=list)
    columns: List[FieldDef] = field(default_factory=list)
    metrics: List[FieldDef] = field(default_factory=list)
    filters: List[FilterItem] = field(default_factory=list)
    dynamic_params: List[DynamicParam] = field(default_factory=list)
    limit: int = 50
    offset: int = 0
    card_name: str = ""


@dataclass
class Page:
    """一次查询的响应。"""

    rows: List[List[Any]]  # 每行每列的值
    column_defs: List[dict]  # 列定义（含字段名/类型/标题）
    count: int  # 总行数
    has_more: bool
    limit: int
    offset: int

    @property
    def total_pages(self) -> int:
        if self.limit <= 0:
            return 1
        return max(1, math.ceil(self.count / self.limit))

    @property
    def current_page(self) -> int:
        return self.offset // self.limit + 1 if self.limit else 1

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def summary(self) -> str:
        return (
            f"共 {self.count} 行 / {self.total_pages} 页，"
            f"当前仅读取第 {self.current_page} 页（{self.row_count} 行），"
            f"如需全部请加 --all 或 --max-pages N"
        )
