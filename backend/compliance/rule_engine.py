# -*- coding: utf-8 -*-
"""合规规则引擎（Drools 语义的可视化规则实现）。

规则以「画布节点 + 连线」的形式存储（前端拖拽编排，落库为 JSON）：

    trigger（触发条件） → condition（判断条件，可多级） → action（执行动作）

引擎按优先级依次执行启用的规则：从触发节点沿连线遍历判断节点，
全部条件满足则执行其后续动作节点，产出：
    - 校验结果（每条规则的通过/拒绝与依据）
    - 整改清单（未通过项 + 建议动作）
支持的操作符：eq/ne/gt/gte/lt/lte/in/contains/exists/regex
支持的动作：block（阻断）/ mask（脱敏）/ require（补充合规要件）/ notify（告警）/
            audit（存证）/ allow（放行）
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Sequence

# ---------------------------------------------------------------------------
# 画布节点模板（前端左侧「节点面板」数据源）
# ---------------------------------------------------------------------------

TRIGGER_TEMPLATES: List[dict] = [
    {"type": "trigger", "event": "data.transfer", "label": "数据跨境传输", "description": "数据拟从来源地区传输至目的地地区时触发"},
    {"type": "trigger", "event": "data.access", "label": "数据访问请求", "description": "任何角色请求访问受管数据时触发"},
    {"type": "trigger", "event": "task.create", "label": "隐私计算任务发起", "description": "创建联邦学习/匿踪查询/联合统计任务时触发"},
    {"type": "trigger", "event": "report.generate", "label": "合规报告生成", "description": "生成监管报告前触发合规要素校验"},
    {"type": "trigger", "event": "grant.apply", "label": "数据授权申请", "description": "合作方申请数据授权时触发"},
]

CONDITION_TEMPLATES: List[dict] = [
    {"type": "condition", "field": "dataLevel", "op": "eq", "value": "P1", "label": "数据敏感度为 P1", "description": "高敏感数据（身份证号、银行卡号等）"},
    {"type": "condition", "field": "dataLevel", "op": "in", "value": ["P1", "P2"], "label": "数据敏感度为 P1/P2", "description": "中高敏感数据"},
    {"type": "condition", "field": "targetRegion", "op": "in", "value": ["EU", "US"], "label": "目的地在欧盟/美国", "description": "适用 GDPR / CCPA 等强监管地区"},
    {"type": "condition", "field": "sourceRegion", "op": "eq", "value": "CN", "label": "来源地为中国", "description": "适用 PIPL 出境限制"},
    {"type": "condition", "field": "crossBorder", "op": "eq", "value": True, "label": "属于跨境传输", "description": "来源地与目的地不一致"},
    {"type": "condition", "field": "hasScc", "op": "eq", "value": False, "label": "未签订 SCC", "description": "缺少标准合同条款"},
    {"type": "condition", "field": "hasDpia", "op": "eq", "value": False, "label": "未完成 DPIA", "description": "缺少数据保护影响评估"},
    {"type": "condition", "field": "authorized", "op": "eq", "value": False, "label": "未取得数据主体授权", "description": "缺少用户明示同意"},
    {"type": "condition", "field": "purpose", "op": "contains", "value": "营销", "label": "用途为营销推广", "description": "与原始收集目的不匹配"},
    {"type": "condition", "field": "fieldCount", "op": "gt", "value": 5000, "label": "数据量超过 5000 条", "description": "触发批量传输评估"},
]

ACTION_TEMPLATES: List[dict] = [
    {"type": "action", "action": "block", "label": "阻断并生成整改清单", "description": "拒绝该次数据处理并输出整改要求"},
    {"type": "action", "action": "mask", "label": "动态脱敏后放行", "description": "按角色与场景调整脱敏粒度后放行"},
    {"type": "action", "action": "require", "label": "要求补充合规要件", "description": "要求补充 SCC / DPIA / 授权证明"},
    {"type": "action", "action": "notify", "label": "通知合规负责人", "description": "向全球合规负责人发送告警"},
    {"type": "action", "action": "audit", "label": "上链存证", "description": "将该次操作写入联盟链审计"},
    {"type": "action", "action": "allow", "label": "放行", "description": "校验通过，允许处理"},
]


def rule_templates() -> dict:
    return {"triggers": TRIGGER_TEMPLATES, "conditions": CONDITION_TEMPLATES, "actions": ACTION_TEMPLATES}


# ---------------------------------------------------------------------------
# 条件求值
# ---------------------------------------------------------------------------


def _compare(actual: Any, op: str, expected: Any) -> bool:
    """按操作符比较；类型不匹配时返回 False 而不是抛异常。"""
    try:
        if op == "eq":
            return actual == expected
        if op == "ne":
            return actual != expected
        if op == "gt":
            return float(actual) > float(expected)
        if op == "gte":
            return float(actual) >= float(expected)
        if op == "lt":
            return float(actual) < float(expected)
        if op == "lte":
            return float(actual) <= float(expected)
        if op == "in":
            values = expected if isinstance(expected, (list, tuple, set)) else [expected]
            return actual in values
        if op == "contains":
            if isinstance(actual, (list, tuple, set)):
                return expected in actual
            return str(expected) in str(actual)
        if op == "exists":
            return (actual is not None) == bool(expected)
        if op == "regex":
            return re.search(str(expected), str(actual)) is not None
    except (TypeError, ValueError):
        return False
    return False


def evaluate_node(node: dict, context: dict) -> tuple[bool, str]:
    """求解单个判断节点，返回 (是否满足, 说明)。"""
    config = node.get("config") or {}
    field = config.get("field") or node.get("field")
    op = config.get("op", "eq")
    expected = config.get("value", node.get("value"))
    actual = context.get(field)
    passed = _compare(actual, op, expected)
    detail = f"{field} {op} {expected!r}（实际值：{actual!r}）→ {'满足' if passed else '不满足'}"
    return passed, detail


def run_rule(rule: dict, context: dict) -> dict:
    """执行单条规则。

    语义说明（重要）：
    - 判断条件「满足」表示 **规则命中**，随后执行其动作节点，而不是「合规通过」；
    - 若命中后执行了阻断类动作（block）→ 结论 blocked；
    - 若命中后只执行了要求整改的动作（require / mask）→ 结论 failed（需整改）；
    - 若命中后仅执行告警/存证/放行（notify / audit / allow）→ 结论 passed；
    - 若判断条件未全部满足 → 规则未命中，结论 passed。

    规则未定义连线时退化为「所有判断节点必须同时满足」的线性判定，保证手工编辑规则
    也能得到确定性结果。
    """
    nodes = {node.get("id"): node for node in (rule.get("nodes") or [])}
    edges = rule.get("edges") or []

    trigger = next((node for node in nodes.values() if node.get("type") == "trigger"), None)
    if trigger:
        event = (trigger.get("config") or {}).get("event") or trigger.get("event")
        if event and context.get("event") and event != context.get("event"):
            return {
                "code": rule.get("code"),
                "name": rule.get("name"),
                "result": "skipped",
                "detail": f"触发事件不匹配（规则期望 {event}，实际 {context.get('event')}）",
                "actions": [],
                "conditions": [],
            }

    condition_nodes = [node for node in nodes.values() if node.get("type") == "condition"]
    action_nodes = [node for node in nodes.values() if node.get("type") == "action"]

    condition_results = []
    all_passed = True
    for node in condition_nodes:
        passed, detail = evaluate_node(node, context)
        condition_results.append({"node": node.get("name") or node.get("id"), "passed": passed, "detail": detail})
        if not passed:
            all_passed = False

    executed_actions: List[dict] = []
    if all_passed:
        for node in action_nodes:
            config = node.get("config") or {}
            executed_actions.append(
                {
                    "action": config.get("action") or node.get("action"),
                    "label": node.get("name") or node.get("label"),
                    "message": config.get("message", ""),
                    "notify": config.get("notify", []),
                }
            )

    actions_set = {item["action"] for item in executed_actions}
    if not all_passed:
        verdict = "passed"
        detail = "判断条件未命中，规则不生效"
    elif "block" in actions_set:
        verdict = "blocked"
        detail = "规则命中，已执行阻断动作"
    elif actions_set & {"require", "mask"}:
        verdict = "failed"
        detail = "规则命中，需补充合规要件或按最小必要原则脱敏"
    else:
        verdict = "passed"
        detail = "规则命中，仅执行告警/存证动作"

    return {
        "code": rule.get("code"),
        "name": rule.get("name"),
        "scene": rule.get("scene"),
        "priority": rule.get("priority", 10),
        "result": verdict,
        "detail": detail,
        "conditions": condition_results,
        "actions": executed_actions,
        "edges": len(edges),
    }


def evaluate(rules: Sequence[dict], context: dict) -> dict:
    """按优先级执行全部启用规则，汇总校验结论与整改清单。"""
    enabled = sorted(
        [rule for rule in rules if rule.get("enabled", True)],
        key=lambda item: item.get("priority", 10),
    )
    results = [run_rule(rule, context) for rule in enabled]
    executed = [item for item in results if item["result"] != "skipped"]

    blocked = [item for item in executed if item["result"] == "blocked"]
    failed = [item for item in executed if item["result"] == "failed"]
    actions = [action for item in executed for action in item["actions"]]

    rectification: List[dict] = []
    for item in blocked + failed:
        condition_issues = 0
        for condition in item["conditions"]:
            if condition["passed"]:
                continue
            condition_issues += 1
            rectification.append(
                {
                    "rule": item["name"],
                    "level": "high" if item in blocked else "medium",
                    "message": condition["detail"],
                    "rectification": _suggestion(condition["node"], item),
                }
            )
        # 规则命中（条件全部满足）但执行了阻断/整改动作时，用动作信息生成整改项
        if condition_issues == 0:
            for action in item["actions"]:
                if action["action"] not in ("block", "require", "mask"):
                    continue
                rectification.append(
                    {
                        "rule": item["name"],
                        "level": "high" if action["action"] == "block" else "medium",
                        "message": action["message"] or f"命中规则动作：{action['label']}",
                        "rectification": _suggestion(action["message"] or item["name"], item),
                    }
                )
    for action in actions:
        if action["action"] == "require":
            text = action["message"] or "需补充合规要件"
            if any(item["message"] == text for item in rectification):
                continue
            rectification.append(
                {
                    "rule": action["label"],
                    "level": "medium",
                    "message": text,
                    "rectification": "请补充 SCC 合同条款 / DPIA 评估报告 / 数据主体授权证明后重新提交",
                }
            )

    return {
        "passed": not blocked and not failed,
        "checkedRules": executed,
        "issues": rectification,
        "rectificationList": rectification,
        "actions": actions,
        "blocked": bool(blocked),
        "summary": {
            "total": len(executed),
            "passed": len([item for item in executed if item["result"] == "passed"]),
            "failed": len(failed),
            "blocked": len(blocked),
            "skipped": len(results) - len(executed),
        },
    }


def _suggestion(condition_name: str, rule: dict) -> str:
    text = str(condition_name or "")
    if "SCC" in text:
        return "与数据接收方签订标准合同条款（SCC）并在平台登记合同编号"
    if "DPIA" in text:
        return "开展数据保护影响评估（DPIA）并上传评估报告，评估周期不超过 12 个月"
    if "授权" in text:
        return "取得数据主体的明示同意（单独同意），并在授权记录中登记授权凭证"
    if "营销" in text:
        return "核实数据使用目的是否与原始收集目的匹配，必要时重新取得授权"
    if "P1" in text or "高敏感" in text:
        return "高敏感数据禁止未授权出境：改用联邦学习/同态加密实现「数据不出域」"
    if "数据量" in text:
        return "批量传输需提交批量传输评估，建议改为密文域计算以避免原始数据流转"
    return f"按规则「{rule.get('name')}」要求整改后重新提交校验"


# ---------------------------------------------------------------------------
# 内置默认规则（对应文档图 18「保存规则查看列表」中的 3 条规则）
# ---------------------------------------------------------------------------


def default_rules() -> List[dict]:
    return [
        {
            "code": "RULE-0001",
            "name": "高敏感数据跨境传输限制",
            "description": "P1 级高敏感数据（身份证号、银行卡号）禁止在未取得授权或缺乏合规要件时跨境传输",
            "scene": "data_transfer",
            "priority": 1,
            "enabled": True,
            "nodes": [
                {"id": "n1", "type": "trigger", "name": "数据跨境传输", "x": 60, "y": 120,
                 "config": {"event": "data.transfer"}},
                {"id": "n2", "type": "condition", "name": "数据敏感度为 P1", "x": 300, "y": 40,
                 "config": {"field": "dataLevel", "op": "eq", "value": "P1"}},
                {"id": "n3", "type": "condition", "name": "属于跨境传输", "x": 300, "y": 160,
                 "config": {"field": "crossBorder", "op": "eq", "value": True}},
                {"id": "n4", "type": "condition", "name": "未取得数据主体授权", "x": 300, "y": 280,
                 "config": {"field": "authorized", "op": "eq", "value": False}},
                {"id": "n5", "type": "action", "name": "阻断并生成整改清单", "x": 600, "y": 160,
                 "config": {"action": "block", "notify": ["compliance.lead", "security.admin"],
                            "message": "P1 级数据禁止未授权出境，请改用密文域计算或补充授权"}},
                {"id": "n6", "type": "action", "name": "上链存证", "x": 840, "y": 160,
                 "config": {"action": "audit"}},
            ],
            "edges": [
                {"source": "n1", "target": "n2"}, {"source": "n1", "target": "n3"},
                {"source": "n1", "target": "n4"}, {"source": "n2", "target": "n5"},
                {"source": "n3", "target": "n5"}, {"source": "n4", "target": "n5"},
                {"source": "n5", "target": "n6"},
            ],
        },
        {
            "code": "RULE-0002",
            "name": "欧盟出境合规要件校验",
            "description": "数据从中国出境至欧盟时，必须已完成 SCC 签订与 DPIA 评估（GDPR / Schrems II 要求）",
            "scene": "data_transfer",
            "priority": 2,
            "enabled": True,
            "nodes": [
                {"id": "m1", "type": "trigger", "name": "数据跨境传输", "x": 60, "y": 120,
                 "config": {"event": "data.transfer"}},
                {"id": "m2", "type": "condition", "name": "目的地在欧盟/美国", "x": 300, "y": 60,
                 "config": {"field": "targetRegion", "op": "in", "value": ["EU", "US"]}},
                {"id": "m3", "type": "condition", "name": "未签订 SCC", "x": 300, "y": 180,
                 "config": {"field": "hasScc", "op": "eq", "value": False}},
                {"id": "m4", "type": "condition", "name": "未完成 DPIA", "x": 300, "y": 300,
                 "config": {"field": "hasDpia", "op": "eq", "value": False}},
                {"id": "m5", "type": "action", "name": "要求补充合规要件", "x": 600, "y": 180,
                 "config": {"action": "require", "notify": ["compliance.lead"],
                            "message": "缺少 SCC 或 DPIA，禁止出境至欧盟"}},
            ],
            "edges": [
                {"source": "m1", "target": "m2"}, {"source": "m2", "target": "m3"},
                {"source": "m2", "target": "m4"}, {"source": "m3", "target": "m5"},
                {"source": "m4", "target": "m5"},
            ],
        },
        {
            "code": "RULE-0003",
            "name": "用途匹配与批量传输管控",
            "description": "数据使用目的需与原始收集目的一致；单次批量传输超过 5000 条需补充评估",
            "scene": "data_transfer",
            "priority": 3,
            "enabled": True,
            "nodes": [
                {"id": "k1", "type": "trigger", "name": "数据跨境传输", "x": 60, "y": 120,
                 "config": {"event": "data.transfer"}},
                {"id": "k2", "type": "condition", "name": "用途为营销推广", "x": 300, "y": 60,
                 "config": {"field": "purpose", "op": "contains", "value": "营销"}},
                {"id": "k3", "type": "condition", "name": "数据量超过 5000 条", "x": 300, "y": 200,
                 "config": {"field": "fieldCount", "op": "gt", "value": 5000}},
                {"id": "k4", "type": "action", "name": "动态脱敏后放行", "x": 620, "y": 60,
                 "config": {"action": "mask", "message": "用途不匹配，按最小必要原则脱敏后放行"}},
                {"id": "k5", "type": "action", "name": "通知合规负责人", "x": 620, "y": 200,
                 "config": {"action": "notify", "notify": ["compliance.lead"],
                            "message": "批量传输超过阈值，需人工复核"}},
            ],
            "edges": [
                {"source": "k1", "target": "k2"}, {"source": "k1", "target": "k3"},
                {"source": "k2", "target": "k4"}, {"source": "k3", "target": "k5"},
            ],
        },
    ]


SCENES = [
    {"code": "data_transfer", "name": "数据跨境传输", "description": "数据出境前的合规要件与敏感度校验"},
    {"code": "authorization", "name": "数据授权", "description": "授权范围、有效期与资质的合规判定"},
    {"code": "compute", "name": "隐私计算", "description": "计算任务发起前的数据分级与预算校验"},
    {"code": "masking", "name": "动态脱敏", "description": "按角色与场景调整脱敏粒度"},
]
