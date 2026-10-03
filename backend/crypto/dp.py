# -*- coding: utf-8 -*-
"""差分隐私（Differential Privacy）核心实现：拉普拉斯机制 + 隐私预算会计。

对应文档：
- 拉普拉斯机制：向数值型结果注入噪声，噪声强度与全局敏感度 Δf 正相关、与隐私预算 ε 负相关；
- 动态隐私预算分配：εₘ = ε_total · (sₘ · cₘ) / Σ(sᵢ · cᵢ)，
  其中 sₘ 为数据敏感度系数、cₘ 为数据对模型的贡献值，实现「高敏感数据高保护、低敏感数据低消耗」；
- 隐私预算会计（Privacy Accountant）：按串行组合（basic composition）与并行组合累计消耗，
  支撑「隐私预算动态管理模块」的剩余额度、超阈值告警。

创新点（对应文档「算法创新性与优化」）：
1. 动态分配隐私预算：按数据敏感度与贡献值调整 ε，平衡保护与效率；
2. 时序衰减因子：聚合时提升近期数据权重；
3. 噪声注入与参数压缩协同，减少冗余传输。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Sequence

# 数据敏感度系数：P1 高敏感数据获得更高的隐私保护强度
SENSITIVITY_COEFFICIENT: Dict[str, float] = {"P1": 2.0, "P2": 1.2, "P3": 0.6}


def laplace_noise(scale: float, rng: random.Random | None = None) -> float:
    """采样拉普拉斯噪声 Lap(0, scale)。

    采用逆变换采样：X = -b·sgn(u)·ln(1-2|u|)，u ~ Uniform(-0.5, 0.5)。
    """
    if scale <= 0:
        return 0.0
    rng = rng or random
    u = rng.uniform(-0.5, 0.5)
    return -scale * math.copysign(1.0, u) * math.log(1.0 - 2.0 * abs(u))


def laplace_mechanism(value: float, sensitivity: float, epsilon: float,
                      rng: random.Random | None = None) -> float:
    """拉普拉斯机制：M(D) = f(D) + Lap(Δf / ε)。"""
    if epsilon <= 0:
        raise ValueError("隐私预算 ε 必须大于 0")
    return value + laplace_noise(sensitivity / epsilon, rng)


def gaussian_sigma(sensitivity: float, epsilon: float, delta: float = 1e-5) -> float:
    """高斯机制噪声尺度 σ，允许极小概率 δ 的失败（用于高维参数场景）。"""
    if epsilon <= 0 or not 0 < delta < 1:
        raise ValueError("参数非法：需 ε>0 且 0<δ<1")
    return sensitivity * math.sqrt(2 * math.log(1.25 / delta)) / epsilon


def gaussian_mechanism(value: float, sensitivity: float, epsilon: float,
                       delta: float = 1e-5, rng: random.Random | None = None) -> float:
    rng = rng or random
    return value + rng.gauss(0.0, gaussian_sigma(sensitivity, epsilon, delta))


def exponential_mechanism(candidates: Sequence[float], utility, sensitivity: float,
                          epsilon: float, rng: random.Random | None = None):
    """指数机制：用于非数值型输出（如按指数概率选择输出项）。"""
    rng = rng or random
    weights = [math.exp(epsilon * utility(c) / (2 * sensitivity)) for c in candidates]
    total = sum(weights)
    if total <= 0:
        return rng.choice(list(candidates))
    threshold = rng.random() * total
    acc = 0.0
    for candidate, weight in zip(candidates, weights):
        acc += weight
        if acc >= threshold:
            return candidate
    return candidates[-1]


def allocate_budget(total_epsilon: float, items: Sequence[dict]) -> List[dict]:
    """动态隐私预算分配。

    入参 items: [{"name": "P1-收付款方信息", "level": "P1", "contribution": 0.8}, ...]
    返回: 每项分配到的 ε，以及最小/最大值（保证每项至少获得 total_epsilon 的 2%）。
    """
    if total_epsilon <= 0:
        raise ValueError("总隐私预算必须大于 0")
    weights = []
    for item in items:
        coefficient = SENSITIVITY_COEFFICIENT.get(str(item.get("level", "P3")).upper(), 1.0)
        contribution = float(item.get("contribution", 1.0))
        weights.append(coefficient * contribution)
    weight_sum = sum(weights) or 1.0
    floor = total_epsilon * 0.02
    allocated = []
    for item, weight in zip(items, weights):
        epsilon = max(floor, total_epsilon * weight / weight_sum)
        allocated.append(
            {
                "name": item.get("name"),
                "level": str(item.get("level", "P3")).upper(),
                "contribution": float(item.get("contribution", 1.0)),
                "weight": round(weight, 4),
                "epsilon": round(epsilon, 6),
            }
        )
    return allocated


def noise_impact(epsilon: float, sensitivity: float = 1.0) -> dict:
    """隐私保护水平与数据效用的量化关系（对应文档「隐私-效率平衡的理论验证」）。

    - 隐私保护水平 PL = 1/(1+ε)：ε 越大保护水平越低（与文档图 43 趋势一致）；
    - 精度损失模型（隐私-效率平衡函数）：loss(ε) = exp(-α·ε)，
      其中 α = ln(1/0.07)/2 ≈ 1.3328，由行业经验值 ε=2 时精度损失约 7% 拟合得到，
      满足跨境交易场景「精度损失 ≤8%」的业务要求；
    - 数据效用 U = 1 - loss(ε)，ε 越大效用越高（与文档图 45 趋势一致）。
    """
    if epsilon <= 0:
        raise ValueError("ε 必须大于 0")
    alpha = math.log(1 / 0.07) / 2
    loss = math.exp(-alpha * epsilon) * sensitivity
    return {
        "epsilon": epsilon,
        "noiseScale": round(sensitivity / epsilon, 6),
        "privacyLevel": round(1.0 / (1.0 + epsilon), 6),
        "accuracyLoss": round(loss, 4),
        "utility": round(max(0.0, 1 - loss), 4),
        "alpha": round(alpha, 4),
    }


@dataclass
class BudgetAccount:
    """隐私预算会计：串行组合累计消耗，支持剩余额度与熔断阈值判断。"""

    total: float
    consumed: float = 0.0
    warning_ratio: float = 0.8
    history: List[dict] = field(default_factory=list)

    @property
    def remaining(self) -> float:
        return max(0.0, self.total - self.consumed)

    @property
    def used_ratio(self) -> float:
        return 0.0 if self.total <= 0 else min(1.0, self.consumed / self.total)

    def spend(self, epsilon: float, scene: str = "", project: str = "") -> dict:
        """消耗预算；预算不足时抛 ValueError（上层转换为 5001 错误码）。"""
        if epsilon <= 0:
            raise ValueError("单次消耗必须大于 0")
        if epsilon > self.remaining + 1e-9:
            raise ValueError(
                f"隐私预算不足：剩余 {self.remaining:.4f}，本次请求 {epsilon:.4f}"
            )
        self.consumed += epsilon
        record = {
            "scene": scene,
            "project": project,
            "epsilon": round(epsilon, 6),
            "consumed": round(self.consumed, 6),
            "remaining": round(self.remaining, 6),
            "warning": self.used_ratio >= self.warning_ratio,
        }
        self.history.append(record)
        return record

    def snapshot(self) -> dict:
        return {
            "total": round(self.total, 6),
            "consumed": round(self.consumed, 6),
            "remaining": round(self.remaining, 6),
            "usedRatio": round(self.used_ratio, 4),
            "remainingRatio": round(1 - self.used_ratio, 4),
            "warning": self.used_ratio >= self.warning_ratio,
            "records": len(self.history),
        }


def validate_dp(epsilon: float, sensitivity: float, true_value: float,
                runs: int = 200, rng: random.Random | None = None) -> dict:
    """蒙特卡洛验证：统计噪声均值/方差与理论值的一致性（用于自测与实验报告）。"""
    rng = rng or random.Random(2026)
    samples = [laplace_mechanism(true_value, sensitivity, epsilon, rng) for _ in range(runs)]
    mean = sum(samples) / runs
    variance = sum((s - mean) ** 2 for s in samples) / runs
    theoretical = 2 * (sensitivity / epsilon) ** 2
    return {
        "epsilon": epsilon,
        "sampleMean": round(mean, 6),
        "bias": round(mean - true_value, 6),
        "sampleVariance": round(variance, 6),
        "theoreticalVariance": round(theoretical, 6),
        "relativeError": round(abs(variance - theoretical) / theoretical, 4),
    }


def perturb_vector(values: Iterable[float], sensitivity: float, epsilon: float,
                   rng: random.Random | None = None) -> List[float]:
    """对向量逐元素加噪（用于联邦学习梯度扰动）。"""
    values = list(values)
    if not values:
        return []
    per_dimension = epsilon / math.sqrt(len(values))  # 按维度分摊预算
    return [laplace_mechanism(v, sensitivity, per_dimension, rng) for v in values]
