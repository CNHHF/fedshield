# 分享数据来源

数据来自既有本地快照，并非本次重新抓取的最新数据。各记录的来源ID、原始定位、文件摘要和采集时间保留在数据库中。

| 来源 | 内容 | 许可或再使用说明 | 原始入口 |
|---|---|---|---|
| UCI / Chen D. (2015) | Online Retail 商品明细与订单 | CC BY 4.0；保留引用和转换说明 | https://archive.ics.uci.edu/dataset/352/online-retail ，DOI 10.24432/C5BW33 |
| ECB | 历史参考汇率 | 公开统计，注明来源；非实时交易报价 | https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html |
| World Bank | 国家年度个人汇款收支指标 | CC BY 4.0；年度宏观统计，不是逐笔资金流 | https://data.worldbank.org/indicator/BX.TRF.PWKR.CD.DT |
| OFAC | 名单、别名和地址历史快照 | 美国政府公开信息；候选名称匹配不等于确认同一主体 | https://ofac.treasury.gov/specially-designated-nationals-list-sdn-list |

许可文本：https://creativecommons.org/licenses/by/4.0/ 。数据库的标准化、订单聚合、派生主键和原始缺失保留方式，见 `docs/FINANCIAL_DATABASE.md` 与来源表。不得将不同来源的数据合并描述为同一批实时跨境支付流水。

现有CTU-BERKA和ULB-1597来源记录没有列明可随包再分发的开放许可，分享包不附带其数据及派生预测；源码保留下载处理工具，由使用者自行核查和获取。

前端使用IBM Plex字体，字体许可证保留在 `frontend/src/assets/fonts/OFL.txt`（以项目实际目录为准）。
