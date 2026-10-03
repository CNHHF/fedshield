# -*- coding: utf-8 -*-
"""跨境支付隐私计算引擎。

包含三大核心场景的算法实现：

1. `federated`   —— 跨境电商联合风控建模：横向联邦学习（FedAvg/FedProx）
                    + 拉普拉斯差分隐私 + Paillier 同态密文聚合 + 参数压缩
2. `oblivious`   —— 外贸 B2B 黑名单匿踪查询：Paillier 密文域比对（文档架构）
                    与 RSA 盲签名 OPRF（生产模式，支撑全量清单 ≤300ms）
3. `joint_stats` —— 全球交易联合统计：地区本地聚合 + Paillier 密文域求和
                    + 差分隐私计数，输出监管申报口径结果
"""

from . import federated, joint_stats, oblivious  # noqa: F401

__all__ = ["federated", "oblivious", "joint_stats"]
