# -*- coding: utf-8 -*-
"""FedShield 密码学与隐私计算基础库。

模块划分：
- `paillier` ：Paillier 半同态加密（密文域比对、密文域聚合）
- `sm4`      ：国密 SM4 分组密码（CBC + HMAC，含纯 Python 降级实现）
- `aes_gcm`  ：AES-256-GCM 认证加密
- `dp`       ：差分隐私（拉普拉斯/高斯/指数机制 + 隐私预算会计）
- `psi`      ：隐私求交集（RSA 盲签名协议）
- `policy`   ：P1/P2/P3 分级加密策略统一出口
"""

from . import aes_gcm, dp, paillier, policy, psi, sm4  # noqa: F401

__all__ = ["paillier", "sm4", "aes_gcm", "dp", "psi", "policy"]
