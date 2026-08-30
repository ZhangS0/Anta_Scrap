"""可隆(KOLON)品牌报表：R03-任意时间段销存结构分析（新）(page wed51d6cd2b894d11a788c29 / card n795c23de94e4455da7f0e9c)。

商品运营分析（销存结构）：最细到「店仓 × 货号 × 尺码/颜色」颗粒，76 维度 × 74 度量。
特色（对比迪桑特 R03）：
- SKC 指标按 门店/办事处/区域/全国 四级组织口径展开（迪桑特版是 鞋服/正价折扣 口径变体）
- 多一组「同期款」指标（流水_同期款/库存吊牌额_同期款 等，按同期同款对比）
- 维度多 本期/同期产品年季、同期款号、同期款吊牌价、产品备注、仪表盘维度 等
- 筛选多 上市日期、产品备注
指标说明见 captures/商品运营分析-指标说明.xlsx。
"""

from __future__ import annotations

import json
from pathlib import Path

from anta_scrap.models import DynamicParam, FieldDef, FilterItem, QueryParams
from anta_scrap.reports.base import BaseReport

# HAR 抓取的完整查询配置态字段（150 项，含 metric 必备的 fieldFormat）。
# 页面字段池同名冲突风险高（同 R03 迪桑特版），以 HAR 字段定义最高优先。
_HAR_FIELDS_FILE = Path(__file__).parent / "r03_sales_stock_kolon_har_fields.json"


class R03SalesStockKolonReport(BaseReport):
    page_id = "wed51d6cd2b894d11a788c29"
    card_id = "n795c23de94e4455da7f0e9c"
    name = "R03-任意时间段销存结构分析（新）-KOLON"
    # HAR 抓取：主数据集（维度/筛选字段所在）
    default_ds_id = "o2f2b45d02f0f4b6c9185588"

    # 动态参数定义（查询参数抓取，5 个）：
    # 本期起止 + 同期起止（自定义对比期）+ 配货季多选（逗号分隔多值）
    DYNAMIC_PARAMS = {
        "开始日期-户外-R02": {
            "dpId": "o944f3df227424be599bf18f",
            "valueType": "DATE",
            "sourceCdId": "r1fc98053262441ce9ad0670",
        },
        "结束日期-户外-R02": {
            "dpId": "k66f14015af12438c86fe041",
            "valueType": "DATE",
            "sourceCdId": "beca11b1cd8c84508ba37cda",
        },
        "同期开始日期-户外": {
            "dpId": "ra44d7ad5092d4d3c8a99f4e",
            "valueType": "DATE",
            "sourceCdId": "f4020c1bf20904a84a5df660",
        },
        "同期结束日期-户外": {
            "dpId": "n315a56bf7c2d469dbca16d4",
            "valueType": "DATE",
            "sourceCdId": "v10ef2a5d4acf47efa79a3f9",
        },
        "户外_配货季(多选)": {
            "dpId": "q03e7207daa3e4635bf6d1d7",
            "valueType": "STRING",
            "sourceCdId": "af3979ad4204b497f9958c57",
        },
    }

    # 字段 → filter 的 sourceCdId 映射（查询参数抓取，12 个）
    FIELD_SOURCE_CDID = {
        "渠道品牌": "cedb8180fbcb342feaa704b0",
        "品牌大区": "c86152e0447154a2ea12d59d",
        "区域": "qcfd6c56910c34b43aac5ec0",
        "办事处": "pb7836e4a84fa4ea29c2c4c9",
        "店铺类型明细": "l3a7b55bc979c4d0aa87e6b0",
        "性别": "v4bc72727c598414996743a1",
        "大类": "bf1df4e27eceb47bdb54b6ea",
        "中类": "lcaa0925090f042e697aa804",
        "系列": "b68a15cbaab894a1d9d28447",
        "子系列": "a69d9f007c0d44cc4862d262",
        "上市日期": "j1dbe3b866b3c4f948c0237f",
        "产品备注": "h8c483c4332974210845ca79",
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
        """HAR 配置态字段优先索引，页面元数据字段仅作补充（同 R03 迪桑特版策略）。"""
        super()._index_fields()
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
