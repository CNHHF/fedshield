"""Produce a traceable, text-only report from the actual workflow evidence."""
from datetime import datetime, timezone
import hashlib


def build_report(run, rows, check, frozen):
    def clean(v):
        return str(v).replace('|', '／').replace('\r', ' ').replace('\n', ' ')
    lines = ['# FedShield 数据处理与合规核查报告', '',
        '## 1 申报对象', f'- 流程：{run.id}', f'- 申报账号：{run.actor}',
        f'- 交易：{len(rows)} 笔；币种：{clean(run.config.get("currency", "—"))}',
        f'- 来源：{clean(" / ".join(check["sourceRegions"]))}；目的地：{clean(check["targetRegion"])}',
        '- 数据性质：'+('真实公开匿名银行流水，按原始账户和交易主键回查；对手国家未知。' if run.config.get('financialSource') else 'UCI真实公开交易，原始行及汇总过程可回查。' if run.config.get('sourceDataset') else '历史演示或账号导入；不得自动认定为已核验真实数据。'),
        f'- 报告依据：{"已保存的合规阶段快照" if frozen else "当前申报预检，规则或材料变化后须重新校验"}',
        '', '## 2 基础材料', '| 类型 | 文件 | 字节数 | SHA-256 |', '|---|---|---:|---|']
    for m in check.get('materials', []):
        lines.append(f'| {clean(m["kindName"])} | {clean(m["filename"])} | {m["size"]} | {m["digest"]} |')
    if not check.get('materials'):
        lines.append('| — | 未登记附件 | — | — |')
    lines += ['', '材料登记及哈希仅证明已收到对应文件，文件内容、授权效力和法律适用仍须人工审核。',
        '', '## 3 规则校验与整改', '| 核查项 | 结果 | 依据或整改要求 |', '|---|---|---|']
    for c in check['checks']:
        lines.append(f'| {clean(c["name"])} | {"满足" if c["passed"] else "未满足"} | {clean(c["actual"] if c["passed"] else c["required"])} |')
    remedies=[]
    for group in check.get('rules', []):
        versions = {v['code']: v['version'] for v in group.get('versions', [])}
        for r in group['checkedRules']:
            lines.append(f'| {clean(group["sourceRegion"])} · {clean(r["name"])} ({clean(r["code"])} v{versions.get(r["code"], "—")}) | {clean(r["result"])} | {clean(r.get("detail", ""))} |')
        for issue in group.get('rectificationList', []):
            remedies.append(f'- 整改：{clean(issue.get("rectification", issue.get("message", "")))}')
    lines += ['']+remedies
    lines += ['', '参考条目：'+'、'.join(clean(p['code']+' '+p['name']) for p in check['policies']),
        '', '## 4 保护及风险处理', '| 阶段 | 实测耗时（ms） |', '|---|---:|']
    for s in run.stages or []:
        lines.append(f'| {clean(s["title"])} | {s["durationMs"]} |')
    lines.append('')
    for s in run.stages or []:
        if s['key'] == 'protect':
            pub = s['detail']['publication']
            lines.append(f'- P1：SM4-CBC+HMAC / Paillier 密钥封装；P2/P3：AES-256-GCM。统计发布 ε={pub["epsilon"]}，敏感度={pub["sensitivity"]}；不披露原始均值或实际噪声。')
    lines += ['', f'## 5 结论：{"规则预检满足" if check["passed"] else "需整改，禁止继续处理"}',
        '本报告为本地原型的申报与规则校验记录，不构成监管批准、法律意见或真实资金处理凭证。',
        ('本批采用真实订单拟合的Isolation Forest异常初筛；无欺诈标签，不输出欺诈概率。' if run.config.get('sourceDataset') else '模型及数据依据原流程记录核查。')+'联邦训练仍为独立模块。']
    if run.config.get('sourceDataset'):
        m=run.config['sourceDataset']
        lines += ['','## 6 数据来源与处理记录',m['sourceUrl'],m['attribution'],m['license'],
                  '原始工作簿SHA-256：'+m['workbookSha256'],m['transformation'],m['limitations']]
    if run.config.get('financialSource'):
        m=run.config['financialSource'];lines+=['','## 6 金融流水来源与入库血缘',m['citation'],m['source_url'],m['limitations'],'本流程尚未配置银行流水专用风险模型，转人工核查；不套用零售或信用卡基准模型。']
        for file in m['files']:lines.append('- 原始快照 '+file['filename']+'；SHA-256 '+file['sha256'])
    text = '\n'.join(lines)+'\n'
    return {'title': '数据处理与合规核查报告', 'runId': run.id, 'passed': check['passed'],
        'frozen': frozen, 'generatedAt': datetime.now(timezone.utc).isoformat(), 'markdown': text,
        'checks': check['checks'], 'materials': check.get('materials', []), 'rules': check.get('rules', []),
        'policies': check['policies'],
        'digest': hashlib.sha256(text.encode()).hexdigest()}
