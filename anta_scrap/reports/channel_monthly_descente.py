"""迪桑特品牌报表：渠道运营分析-月报 (page nfbcf31a97f654358b087bb6 / card vc833a1254db9434e80823d1)。

特别说明（来自指标说明 Excel）：
- 月度维度：月流水、月店效、月坪效、月有效店数等
- 年累维度：年累流水、年累店效、年累坪效、年累店数等
- 改造分析：改造前后店效/坪效对比
- 同店分析：同店类型、形象店龄等维度
"""

from __future__ import annotations

from anta_scrap.models import DynamicParam, FieldDef, FilterItem, QueryParams
from anta_scrap.reports.base import BaseReport


class ChannelMonthlyDescenteReport(BaseReport):
    page_id = "nfbcf31a97f654358b087bb6"
    card_id = "vc833a1254db9434e80823d1"
    name = "渠道运营分析-月报"
    # 从 HAR 抓取：数据集 ID
    default_ds_id = "cf397decca0e2412c87d7aa0"

    # 月报无动态参数（通过筛选字段 日历月份 控制时间）
    DYNAMIC_PARAMS = {}

    # 字段 → filter 的 sourceCdId 映射（从请求负载抓取）
    FIELD_SOURCE_CDID = {
        "渠道品牌": "k74fead4dce3b43648bc4ead",
        "店铺类型明细": "ueca3c2eeeec04b318d2eecc",
        "日历月份": "xaebbf46184314912aaf95ea",
        "区域": "a415c80251dec487db72701c",
        "办事处": "l67a34399ba76427a8ae7c2a",
        "城市_映射": "q12054980b0d0463d8d792b7",
        "店铺编码": "kad3acb11fe004846a54e466",
        "店铺名称": "b747e65e02a9e4e29b231226",
        "门店性质": "ad301b4ed9f1c46dd9486e4e",
        "是否有效店": "t25bcb4c5e78e4756bbe07d8",
        "是否保有店": "b987d79cde2f7464ebcc5d13",
        "是否新开店": "i1eb988afc37a4939acce352",
        "是否改造店": "m89cc3fd5b2dc4c568c3f47f",
        "是否关闭店": "j9a72e56809fd49baad18172",
        "形象店龄": "ecb8bcdf66d2f4103b2aebb8",
        "门店类型": "id040d9f1b091402fb99a413",
        "商场体系": "m4756b7024daf4b0ea3a61de",
        "新开/关闭店年累流水是否为0": "e18a391dccfd8498da9f8deb",
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
            self.field("月店效本期"),
            self.field("月店效同期"),
            self.field("月有效店数本期"),
            self.field("月保有店数本期"),
            self.field("年累流水本期"),
            self.field("年累流水同期"),
            self.field("年累店效本期"),
            self.field("年累店效同期"),
        ]
        filters = [
            self._filter("渠道品牌", ["DESCENTE"]),
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

    def _filter(self, name: str, values: list) -> FilterItem:
        """构造 filter 并自动从 FIELD_SOURCE_CDID 注入 sourceCdId。"""
        fd = self.field(name)
        fd.source_cd_id = self.FIELD_SOURCE_CDID.get(name)
        return FilterItem(field=fd, values=values)

    def _dp(self, name: str, value: str) -> DynamicParam:
        """月报无动态参数，直接抛错。"""
        raise NotImplementedError(f"月报无动态参数 '{name}'，请使用筛选字段控制时间")
