"""迪桑特品牌报表：零售运营分析-日报 (page ne63f6cf08bbb40c28b814e8 / card q72769bce32b04f91873eeee)。"""

from __future__ import annotations

from anta_scrap.models import DynamicParam, FieldDef, FilterItem, QueryParams
from anta_scrap.reports.base import BaseReport


class RetailDailyDescenteReport(BaseReport):
    page_id = "ne63f6cf08bbb40c28b814e8"  # 默认页面
    # 候选页面ID列表（根据实际发现的用户页面添加）
    candidate_page_ids = []

    card_id = "q72769bce32b04f91873eeee"
    name = "零售运营分析-日报-迪桑特"
    # HAR 验证：本报表的字段全部来自数据集 d480975549d784546887c757
    default_ds_id = "d480975549d784546887c757"

    # 动态参数定义（HAR 抓取）：页面的日期筛选器控件。
    # 服务端校验不严，传 dpId + defaultValue 即可生效。
    # 后续若页面控件改动，重新从 HAR 复制对应字段。
    DYNAMIC_PARAMS = {
        "开始日期-户外-R02": {
            "dpId": "o944f3df227424be599bf18f",
            "valueType": "DATE",
            "sourceCdId": "c048212453d4a4a3cbdf3c68",
        },
        "结束日期-户外-R02": {
            "dpId": "k66f14015af12438c86fe041",
            "valueType": "DATE",
            "sourceCdId": "tb80534a2f65440e2a1288dd",
        },
    }

    # 字段 → filter 的 sourceCdId 映射（HAR/请求负载抓取）。
    # sourceCdId 是该字段对应的"选择器卡片"ID（不同于数据集 dsId）。
    # BI 后端在处理 filter 时会按 sourceCdId 找选择器配置，缺失会 None.get 报错。
    FIELD_SOURCE_CDID = {
        "渠道品牌": "me03a1f830c364f44989e8a6",
        "商品品牌": "a9fc640f1ce7d42c788df11b",
        "品牌大区": "a436b9a27fd674252b76ff63",
        "区域": "v2ccab58704084c55914ea29",
        "城市_映射": "kb4c6703f0369424a80c1dd1",
        "办事处": "b51648f09eff64a7ea0ddee1",
        "店铺编码": "i7cc57ae94c734cdab990b9a",
        "店铺名称": "m5b8996b737964b9cb58c010",
        "零售经理": "b9456e1d933db4604836571d",
        "店铺类型明细": "q8a34909a03164207a1c6931",
        "门店性质": "qe417bacf6b2b41518278b23",
        "门店类型": "q622fca569b4143c1be1c34d",
        "店铺等级编码": "cff74089e7a2546478216f96",
        "经营类型": "lc6ff4662113340e28ccd142",
        "集合店属性": "l3c755afafca641878e3c26c",
        "商场体系": "c6e4e95cc12d840658ebee87",
    }

    def default_template(self) -> QueryParams:
        """HAR 验证过的完整字段配置（4 维度 + 9 指标 + 2 filter + 2 日期）。"""
        rows = [self.field("渠道品牌"), self.field("店铺名称"), self.field("城市等级"), self.field("商品品牌")]
        metrics = [
            self.field("零售流水目标"), self.field("零售达成"),
            self.field("流水"), self.field("流水同期"), self.field("流水同比"),
            self.field("客单价"),
            self.field("同店流水"), self.field("同店流水同期"), self.field("同店流水同比"),
        ]
        filters = [
            self._filter("渠道品牌", ["DESCENTE"]),
            self._filter("商品品牌", ["迪桑特"]),
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
