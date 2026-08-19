"""KOLON 品牌报表：零售运营分析-日报 (card bdea3dc0adfc24d9b9e3f9a3)。"""

from __future__ import annotations

from anta_scrap.models import DynamicParam, FieldDef, FilterItem, QueryParams
from anta_scrap.reports.base import BaseReport


class RetailDailyKolonReport(BaseReport):
    page_id = "ne63f6cf08bbb40c28b814e8"  # 与 DESCENTE 共享同一页面
    card_id = "bdea3dc0adfc24d9b9e3f9a3"
    name = "零售运营分析-日报-KOLON"
    # HAR 验证：本报表的字段全部来自数据集 df905751149c646e4a760566
    default_ds_id = "df905751149c646e4a760566"

    # 动态参数定义（HAR 抓取）：KOLON 专用日期筛选器控件
    DYNAMIC_PARAMS = {
        "开始日期-户外-R02": {
            "dpId": "o944f3df227424be599bf18f",
            "valueType": "DATE",
            "sourceCdId": "mbe3a806f444e461a88fcc14",
        },
        "结束日期-户外-R02": {
            "dpId": "k66f14015af12438c86fe041",
            "valueType": "DATE",
            "sourceCdId": "u8ac950fae3f849f4a14e727",
        },
    }

    # 字段 → filter 的 sourceCdId 映射（HAR 抓取）
    # 注意：同一个字段在不同查询场景下可能使用不同的 sourceCdId
    FIELD_SOURCE_CDID = {
        "渠道品牌": "lf5837e58c3db4e31b93f159",  # 通用筛选
        "区域": "gbc980ddf6fc84ffa9146679",       # 店效查询专用
    }

    def default_template(self) -> QueryParams:
        """HAR 验证过的完整字段配置（35 维度 + 101 指标 + 1 filter + 2 日期）。"""
        # 维度字段（从 HAR 查询体提取的前 10 个常用维度）
        rows = [
            self.field("日历日期"),
            self.field("渠道品牌"),
            self.field("店铺编码"),
            self.field("店铺名称"),
            self.field("商品品牌"),
            self.field("省份"),
            self.field("城市等级"),
            self.field("区域"),
            self.field("商场体系"),
            self.field("门店性质"),
        ]

        # 指标字段（从 HAR 查询体提取的常用指标）
        metrics = [
            self.field("流水"),
            self.field("预算流水目标"),
            self.field("零售达成"),
            self.field("流水同期"),
            self.field("流水同比"),
            self.field("同店流水"),
            self.field("同店流水同期"),
            self.field("同店流水同比"),
            self.field("预算达成"),
            self.field("有效店标识"),
        ]

        filters = [
            self._filter("渠道品牌", ["KOLON"]),
        ]

        dynamic_params = [
            self._dp("开始日期-户外-R02", "2026-07-22"),
            self._dp("结束日期-户外-R02", "2026-07-29"),
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
