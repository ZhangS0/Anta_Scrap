"""可隆(KOLON)品牌报表：渠道运营分析-月报 (page t7ca8e27fad254726b0f8dc6 / card s7d5ec3e4ece24b38a0d348f)。

KOLON 月度渠道报表：39 维度 × 250 度量（本库最大度量集）。
覆盖：销售/同店/客流人次/店数/店效/坪效/面积/改造前后 的 月度+年累 × 本期/同期/同比 全组合，以及零售/预算目标。
无动态参数——时间用筛选字段 `日历月份`（YYYY-MM）控制，与迪桑特月报一致。
指标说明见 captures/渠道运营分析-月报-可隆 指标说明.xlsx。
"""

from __future__ import annotations

import json
from pathlib import Path

from anta_scrap.models import DynamicParam, FieldDef, FilterItem, QueryParams
from anta_scrap.reports.base import BaseReport

# HAR 抓取的完整查询配置态字段（288 项，含 metric 必备的 fieldFormat）。
# 与 R03 相同的策略：页面字段池同名冲突风险高，以 HAR 字段定义最高优先。
_HAR_FIELDS_FILE = Path(__file__).parent / "channel_monthly_kolon_har_fields.json"


class ChannelMonthlyKolonReport(BaseReport):
    page_id = "t7ca8e27fad254726b0f8dc6"
    card_id = "s7d5ec3e4ece24b38a0d348f"
    name = "渠道运营分析-月报-KOLON"
    # HAR 抓取：主数据集
    default_ds_id = "o0752bf1095bf43eb9af11b6"

    # 月报无动态参数（时间用 日历月份 筛选控制，格式 YYYY-MM）
    DYNAMIC_PARAMS = {}

    # 字段 → filter 的 sourceCdId 映射（查询参数抓取，14 个）
    FIELD_SOURCE_CDID = {
        "渠道品牌": "aef3341dab6214e37a94d55c",
        "店铺类型明细": "m0f85f089855b43b4bf63c73",
        "日历月份": "tc50d888ab6f847d8bd78386",
        "区域": "ld9655fe2ab84423a99f554d",
        "城市_映射": "w20d7411c246c4dcd8fd4366",
        "门店性质": "abfeb038e707c47b5b36719b",
        "是否有效店本期（1是,0否）": "e34d3b1bb4c354ee89aaed70",
        "是否保有店（计算数量:1是,0否）": "m99b67832890f460589f01ea",
        "是否新开店（计算数量:1是,0否）": "i1d3b22668cf04c86ab29266",
        "是否改造店（计算数量-改造结束月份）": "oe0a0d6ad08af46ea8d1e40f",
        "是否撤消店（计算数量:1是,0否）": "d50350d0284d14ced957e0c5",
        "商场体系": "a7c6c6086c39a489c90b11da",
        "店铺编码": "p86ccf11df3304d70a36d714",
        "店铺名称": "k23fcad442ddc4d71991c158",
    }

    def default_template(self) -> QueryParams:
        """基础月度指标配置（月流水+店效+店数）。"""
        rows = [
            self.field("日历月份"),
            self.field("区域"),
            self.field("店铺名称"),
        ]
        metrics = [
            self.field("月流水本期"),
            self.field("月流水同期"),
            self.field("月流水同比"),
            self.field("月店效本期"),
            self.field("月度坪效本期"),
            self.field("月有效店数本期"),
            self.field("月保有店数本期"),
            self.field("年累流水本期"),
            self.field("年累流水同期"),
            self.field("年累流水同比"),
        ]
        filters = [
            self._filter("渠道品牌", ["KOLON"]),
            self._filter("店铺类型明细", ["正价店", "折扣店"]),
            self._filter("日历月份", ["2026-08"]),
        ]
        return QueryParams(
            rows=rows,
            metrics=metrics,
            filters=filters,
            dynamic_params=[],
            limit=50,
            offset=0,
            card_name=self.name,
        )

    def _index_fields(self) -> None:
        """HAR 配置态字段优先索引，页面元数据字段仅作补充（同 R03 策略）。"""
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
        """月报无动态参数，直接抛错。"""
        raise NotImplementedError(f"月报无动态参数 '{name}'，请使用筛选字段 日历月份 控制时间")
