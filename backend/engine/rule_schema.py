"""Bounded boolean rule schema shared by AI generation and execution."""
import math
REGIONS={'CN','EU','US','SEA','APAC','ME','AF','LATAM','UK','NA','OTHER'}
BOOLEANS={'authorized','hasScc','hasDpia','crossBorder','customerIdPresent'}
NUMBERS={'amount','fieldCount','lineCount','quantity'}
TEXTS={'sourceRegion','targetRegion','dataLevel','currency','purpose','customerCountry'}
LABELS={'amount':'单笔金额','fieldCount':'批次记录数','lineCount':'订单明细数','quantity':'商品件数','authorized':'已登记授权','hasScc':'已登记传输依据','hasDpia':'已登记影响评估','crossBorder':'跨境处理','customerIdPresent':'含客户编号','sourceRegion':'来源地区','targetRegion':'处理目的地','dataLevel':'数据级别','currency':'币种','purpose':'用途','customerCountry':'客户国家'}
def validate_expression(expr,depth=0,budget=None):
    budget=[0] if budget is None else budget
    if depth>4 or not isinstance(expr,dict):raise ValueError('条件组深度或结构无效')
    group=[k for k in ('all','any') if k in expr]
    if group:
        if len(group)!=1 or set(expr)!={group[0]}:raise ValueError('条件组须明确为全部或任一')
        children=expr[group[0]]
        if not isinstance(children,list) or not 1<=len(children)<=12:raise ValueError('条件组须包含1–12项')
        return {group[0]:[validate_expression(c,depth+1,budget) for c in children]}
    if set(expr)!={'field','op','value'}:raise ValueError('条件须包含field、op、value')
    field,op,value=expr['field'],expr['op'],expr['value'];budget[0]+=1
    if budget[0]>24 or not isinstance(field,str) or field not in BOOLEANS|NUMBERS|TEXTS:raise ValueError('条件过多或字段不受支持')
    if field in BOOLEANS:
        if op not in ('eq','ne') or not isinstance(value,bool):raise ValueError('布尔条件类型错误')
    elif field in NUMBERS:
        if op not in ('eq','ne','gt','gte','lt','lte') or isinstance(value,bool) or not isinstance(value,(float,int)) or abs(value)>1e12 or not math.isfinite(value):raise ValueError('数值条件无效')
    else:
        if op not in ('eq','ne','in','contains'):raise ValueError('文本操作符不受支持')
        values=value if op=='in' else [value]
        if not isinstance(values,list) or not 1<=len(values)<=20 or any(not isinstance(v,str) or not 1<=len(v)<=160 for v in values):raise ValueError('文本条件值无效')
        if field.endswith('Region') and any(v not in REGIONS for v in values):raise ValueError('地区代码无效')
        if field=='dataLevel' and any(v not in ('P1','P2','P3') for v in values):raise ValueError('分级无效')
    return dict(expr)
def flatten(expr):
    if 'field' in expr:return [expr]
    return [c for children in expr.values() for e in children for c in flatten(e)]
def summarize(expr):
    if 'field' in expr:
        ops={'eq':'等于','ne':'不等于','gt':'大于','gte':'不少于','lt':'小于','lte':'不超过','in':'属于','contains':'包含'}
        value='是' if expr['value'] is True else '否' if expr['value'] is False else str(expr['value'])
        return LABELS[expr['field']]+' '+ops[expr['op']]+' '+value
    k=next(iter(expr));return (' 且 ' if k=='all' else ' 或 ').join('（'+summarize(c)+'）' for c in expr[k])
def compile_spec(spec):
    if not isinstance(spec,dict):raise ValueError('规则生成结果无效')
    if spec.get('needsClarification'):raise ValueError(str(spec['needsClarification'])[:300])
    expr=validate_expression(spec.get('condition'))
    name=spec.get('name');actions=spec.get('actions')
    if not isinstance(name,str) or not 1<=len(name)<=80:raise ValueError('规则名称无效')
    if not isinstance(actions,list) or not 1<=len(actions)<=4:raise ValueError('需要1–4个执行动作')
    nodes=[{'id':'ai-trigger','type':'trigger','name':'数据传输校验','x':40,'y':160,'config':{'event':'data.transfer'}}]
    conditions=[expr if 'field' not in expr else {'all':[expr]}]
    for i,c in enumerate(conditions):nodes.append({'id':f'ai-condition-{i}','type':'condition','name':summarize(c)[:100],'x':300,'y':30+i*95,'config':dict(c) if 'field' in c else {'expression':c}})
    edges=[{'source':'ai-trigger','target':n['id']} for n in nodes[1:]]
    action_nodes=[]
    for i,a in enumerate(actions):
        if not isinstance(a,dict) or a.get('action') not in ('block','require','notify','audit','allow'):raise ValueError('动作不受支持')
        message=a.get('message','')
        if not isinstance(message,str) or len(message)>300:raise ValueError('动作说明过长')
        action_nodes.append({'id':f'ai-action-{i}','type':'action','name':{'block':'阻断','require':'要求补充材料','notify':'记录告警','audit':'记录审计','allow':'本规则校验满足'}[a['action']],'x':650,'y':50+i*100,'config':{'action':a['action'],'message':message,'notify':[]}})
    for n in nodes[1:]:
        for a in action_nodes:edges.append({'source':n['id'],'target':a['id']})
    return {'mode':'DeepSeek · 规则配置','name':name,'description':summarize(expr),'scene':'data_transfer','priority':10,'enabled':False,'condition':expr,'conditions':flatten(expr),'summary':summarize(expr),'nodes':nodes+action_nodes,'edges':edges}
