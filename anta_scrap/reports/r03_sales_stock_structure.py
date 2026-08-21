"""报表：R03-任意时间段销存结构分析（新）(page mfeaf38ca3b1e41be8d5f47a / card jfdefcec0ca0e4075b897312)。

商品运营分析（销存结构）：最细到「店仓 × 货号 × 尺码颜色」颗粒，含销售/库存/齐码/动销/库销比/采购报废等 70 度量。
特色动态参数：同期开始/结束日期（自定义对比期）、配货季多选（如 2026Q3）。
指标说明见 test/商品运营分析-指标说明.xlsx。
"""

from __future__ import annotations

import json
from pathlib import Path

from anta_scrap.models import DynamicParam, FieldDef, FilterItem, QueryParams
from anta_scrap.reports.base import BaseReport

# HAR 抓取的完整查询配置态字段（147 项，含 metric 必备的 fieldFormat）。
# 页面字段池里有上百个「XX流水占比」计算字段，某卡片配置态存在 name=流水 的占比字段，
# 会把基础「流水」挤掉（实测导出成占比小数）。故本报表以 HAR 字段定义最高优先。
_HAR_FIELDS_FILE = Path(__file__).parent / "r03_har_fields.json"


class R03SalesStockStructureReport(BaseReport):
    page_id = "mfeaf38ca3b1e41be8d5f47a"
    card_id = "jfdefcec0ca0e4075b897312"
    name = "R03-任意时间段销存结构分析（新）"
    # HAR 抓取：主数据集（维度/筛选字段所在）
    default_ds_id = "f0c3a1724bd3144ba8d3d91b"

    # 动态参数定义（HAR 抓取，5 个）：
    # 本期起止 + 同期起止（自定义对比期，不必是去年同期）+ 配货季多选
    DYNAMIC_PARAMS = {
        "开始日期-户外-R02": {
            "dpId": "o944f3df227424be599bf18f",
            "valueType": "DATE",
            "sourceCdId": "a48060ff14a344413b3e6461",
        },
        "结束日期-户外-R02": {
            "dpId": "k66f14015af12438c86fe041",
            "valueType": "DATE",
            "sourceCdId": "u154229b437ec42c7a6522b1",
        },
        "同期开始日期-户外": {
            "dpId": "ra44d7ad5092d4d3c8a99f4e",
            "valueType": "DATE",
            "sourceCdId": "eaa84ac566f6e41ebb887709",
        },
        "同期结束日期-户外": {
            "dpId": "n315a56bf7c2d469dbca16d4",
            "valueType": "DATE",
            "sourceCdId": "wb69b1895dcb942308df9cfa",
        },
        "户外_配货季(多选)": {
            "dpId": "q03e7207daa3e4635bf6d1d7",
            "valueType": "STRING",
            "sourceCdId": "fa3871168420c41689f53b46",
        },
    }

    # 字段 → filter 的 sourceCdId 映射（HAR 抓取，14 个）
    FIELD_SOURCE_CDID = {
        "渠道品牌": "kb21cec87f5864c8ab9dd2a1",
        "品牌大区": "xdea2bf9ee90b41e98c2e69b",
        "商品品牌": "r7ecb1b0f74894a6a9e23b0e",
        "区域": "e941dad11e62e4337b7d5076",
        "办事处": "p25ef0261a609468eb87c59f",
        "店仓编码": "b65ca6106d93742ba9bd748f",
        "店仓名称": "g47f56cf9d8c343b78849ef8",
        "店铺类型明细": "xe1d9c976c0724f93bea2a6d",
        "货号": "kb726214b0ed349b7ad4860f",
        "性别": "wdafbcbf7308347dd8aa319f",
        "大类": "sbd2a7eac8839429382346f6",
        "中类": "g96525db448374567a7ed37c",
        "系列": "x800daeb8085c4cb2a3b0679",
        "子系列": "s512af00eb6a24bd3989082f",
    }

    def default_template(self) -> QueryParams:
        """基础销存结构查询（按中类汇总销售与库存）。"""
        rows = [
            self.field("中类"),
            self.field("货号"),
        ]
        metrics = [
            self.field("流水"),
            self.field("流水同期"),
            self.field("销售数量"),
            self.field("库存数量"),
            self.field("动销率"),
            self.field("月库销比"),
            self.field("齐码率"),
        ]
        filters = [
            self._filter("渠道品牌", ["KOLON"]),
        ]
        dynamic_params = [
            self._dp("开始日期-户外-R02", "2026-08-01"),
            self._dp("结束日期-户外-R02", "2026-08-07"),
            self._dp("同期开始日期-户外", "2025-08-01"),
            self._dp("同期结束日期-户外", "2025-08-07"),
            self._dp("户外_配货季(多选)", "2026Q3"),
        ]
        return QueryParams(
            rows=rows,
            metrics=metrics,
            filters=filters,
            dynamic_params=dynamic_params,
            limit=50,
            offset=0,
            card_name=self.name,
        )

    def _index_fields(self) -> None:
        """HAR 配置态字段优先索引，页面元数据字段仅作补充。

        页面字段池同名冲突（如 name=流水 实为占比字段）会把基础指标解析错，
        因此先加载 r03_har_fields.json 的真实查询字段，再让基类补缺。
        """
        super()._index_fields()  # 先按基类双源策略建索引
        prior_by_name = dict(self._fields_by_name)
        prior_by_pair = dict(self._fields_by_name_and_ds)
        self._fields_by_name.clear()
        self._fields_by_name_and_ds.clear()
        try:
            har_items = json.loads(_HAR_FIELDS_FILE.read_text(encoding="utf-8"))
        except Exception:
            har_items = []
        for item in har_items:
            self._add_field_from_item(item, default_ds_id=self.default_ds_id)
        # 页面元数据里 HAR 没有的字段（如未用过的维度）作兜底
        for k, v in prior_by_name.items():
            self._fields_by_name.setdefault(k, v)
        for k, v in prior_by_pair.items():
            self._fields_by_name_and_ds.setdefault(k, v)

    def _filter(self, name: str, values: list) -> FilterItem:
        """构造 filter 并自动从 FIELD_SOURCE_CDID 注入 sourceCdId。"""
        fd = self.field(name)
        fd.source_cd_id = self.FIELD_SOURCE_CDID.get(name)
        return FilterItem(field=fd, values=values)

    def _dp(self, name: str, value: str) -> DynamicParam:
        """按名字取动态参数定义；名字必须在 DYNAMIC_PARAMS 里。"""
        if name not in self.DYNAMIC_PARAMS:
            avail = list(self.DYNAMIC_PARAMS.keys())
            raise KeyError(f"未找到动态参数 '{name}'，可选: {avail}")
        cfg = self.DYNAMIC_PARAMS[name]
        return DynamicParam(
            dp_id=cfg["dpId"],
            name=name,
            value=value,
            value_type=cfg.get("valueType", "DATE"),
            source_cd_id=cfg.get("sourceCdId"),
        )
