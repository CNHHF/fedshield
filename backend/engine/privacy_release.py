"""Bounded scalar statistics with replace-one adjacency and secure randomness."""
import math
import random

from ..crypto.dp import laplace_mechanism


def release(values, lower, upper, epsilon, statistic):
    if not values or not all(math.isfinite(x) for x in values):
        raise ValueError("数据必须是非空的有限数值列表")
    if not all(math.isfinite(x) for x in (lower, upper, epsilon)) or not lower < upper:
        raise ValueError("裁剪上下界必须有限且下界小于上界")
    if not 0.01 <= epsilon <= 10:
        raise ValueError("ε 必须在 0.01 到 10 之间")
    if statistic not in ("mean", "sum"):
        raise ValueError("仅支持均值或总和")
    clipped = [min(upper, max(lower, x)) for x in values]
    divisor = len(values) if statistic == "mean" else 1
    sensitivity = (upper - lower) / divisor
    value = math.fsum(clipped) / divisor
    if not all(math.isfinite(x) for x in (sensitivity, value, sensitivity / epsilon)):
        raise ValueError("数值范围过大，请调整裁剪上下界")
    noisy = laplace_mechanism(value, sensitivity, epsilon, random.SystemRandom())
    return {"value": noisy, "epsilon": epsilon, "sensitivity": sensitivity,
            "noiseScale": sensitivity / epsilon, "statistic": statistic,
            "lower": lower, "upper": upper,
            "adjacency": "固定样本量，替换一条记录；每条记录视作一个保护单元",
            "note": "仅发布加噪后的统计量；不返回原值或实际噪声。重复发布按 ε 累加记账。"}
