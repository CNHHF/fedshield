# -*- coding: utf-8 -*-
"""FedShield 隐私计算平台后端包。

子包说明：
- `crypto`     ：密码学与隐私计算基础库（Paillier / SM4 / AES-GCM / 差分隐私 / PSI）
- `engine`     ：跨境支付隐私计算引擎（联邦学习/匿踪查询/联合统计/隐私求交）
- `compliance` ：全流程合规校验（智能分级/规则引擎/法规库/合规报告）
- `audit`      ：联盟链存证与审计日志
- `api`        ：REST 接口蓝图
"""

__version__ = "1.0.0"
__all__ = ["crypto", "engine", "compliance", "audit", "api"]
