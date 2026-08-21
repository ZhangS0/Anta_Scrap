"""KOLON 品牌报表：零售运营分析-日报 (card bdea3dc0adfc24d9b9e3f9a3)。

注意：不同用户可能访问不同的页面实例！
- 用户 <工号A> 使用页面: ne63f6cf08bbb40c28b814e8
- 用户 <工号B> 使用页面: e71d78d5bb6234d5ead169a2
"""

from __future__ import annotations

from anta_scrap.models import DynamicParam, FieldDef, FilterItem, QueryParams
from anta_scrap.reports.base import BaseReport


class RetailDailyKolonReport(BaseReport):
    # 支持多页面ID（不同用户可能被分配到不同页面实例）
    page_id = "ne63f6cf08bbb40c28b814e8"  # 默认页面
    candidate_page_ids = ["e71d78d5bb6234d5ead169a2"]  # 候选页面

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

    # 字段 → filter 的 sourceCdId 映射（请求负载抓取）
    # 注意：同一个字段在不同查询场景下可能使用不同的 sourceCdId
    FIELD_SOURCE_CDID = {
        "渠道品牌": "lf5837e58c3db4e31b93f159",
        "品牌大区": "d6e8318bf0ecb42959a05e12",
        "店铺编码": "k8f31e96608d6498486fe128",
        "店铺名称": "f616c47a3ec25492593e46ab",
        "零售经理": "r6dd7534a4e024b768f8fd68",
        "办事处": "t63163974763f49ba9048118",
        "城市_映射": "nd3632c0253244a70bfe025d",
        "区域": "gbc980ddf6fc84ffa9146679",
        "店铺类型明细": "w922418861a644192b249e5e",
        "门店类型": "d68af6ba33b1441d59e4231b",
        "店铺分级编码": "g96b4ed2652db4420a08113f",
        "经营类型": "r9799397d563440d8a593c42",
        "集合店属性": "we69c80761ef749d4bdb3268",
        "商场体系": "h300ada0d53cd47dd843278f",
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