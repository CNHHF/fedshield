"""DAG execution: connected parents join with AND; OR lives in a condition group."""
def validate_graph(nodes,edges):
    if not isinstance(nodes,list) or not 1<=len(nodes)<=64 or not isinstance(edges,list) or len(edges)>128:raise ValueError('画布节点或连线数量无效')
    if any(not isinstance(n,dict) or not isinstance(n.get('id'),str) or not 1<=len(n['id'])<=80 or n.get('type') not in ('trigger','condition','action') or not isinstance(n.get('config',{}),dict) for n in nodes):raise ValueError('画布节点结构无效')
    mapping={n['id']:n for n in nodes}
    for n in nodes:
        cfg=n.get('config') or {}
        if n['type']=='action' and (cfg.get('action') or n.get('action')) not in ('block','require','mask','notify','audit','allow'):raise ValueError('动作类型无效')
        if n['type']=='condition' and not cfg.get('expression') and not (cfg.get('field') or n.get('field')):raise ValueError('判断节点缺少条件')
    if len(mapping)!=len(nodes):raise ValueError('节点编号重复')
    if sum(n['type']=='trigger' for n in nodes)!=1:raise ValueError('画布必须有一个触发节点')
    incoming={k:set() for k in mapping};outgoing={k:set() for k in mapping}
    for e in edges:
        if not isinstance(e,dict) or not isinstance(e.get('source'),str) or not isinstance(e.get('target'),str) or e['source'] not in mapping or e['target'] not in mapping:raise ValueError('连线端点无效')
        a,b=e['source'],e['target']
        if mapping[b]['type']=='trigger':raise ValueError('触发节点不能作为连线终点')
        incoming[b].add(a);outgoing[a].add(b)
    ready=[k for k in mapping if not incoming[k]];counts={k:len(v) for k,v in incoming.items()};order=[]
    while ready:
        k=ready.pop();order.append(k)
        for child in outgoing[k]:
            counts[child]-=1
            if counts[child]==0:ready.append(child)
    if len(order)!=len(nodes):raise ValueError('规则连线存在循环')
    return mapping,incoming,outgoing,order
def execute(rule,context,evaluate_node):
    nodes=rule.get('nodes') or [];edges=rule.get('edges') or []
    mapping,incoming,outgoing,order=validate_graph(nodes,edges)
    active={};conditions=[];actions=[];missing=False
    from ..engine.rule_schema import validate_expression
    def missing_expression(expr):
        if 'field' in expr:
            if context.get(expr['field']) is None:return None,{expr['field']}
            value,_=evaluate_node({'config':expr},context)
            return value,set()
        key='all' if 'all' in expr else 'any'
        items=[missing_expression(c) for c in expr[key]]
        # An irrelevant branch must not demand inputs that cannot affect its result.
        decisive=False if key=='all' else True
        if any(v is decisive for v,_ in items):return decisive,set()
        absent=set().union(*(m for v,m in items if v is None))
        return (None,absent) if absent else (not decisive,set())
    for k in order:
        node=mapping[k];kind=node['type'];config=node.get('config') or {}
        if kind=='trigger':active[k]=True;continue
        reached=bool(incoming[k]) and all(active.get(p,False) for p in incoming[k])
        if not reached:active[k]=False;continue
        if kind=='condition':
            expr=config.get('expression')
            if expr:_,absent=missing_expression(validate_expression(expr))
            else:absent=[f for f in [config.get('field') or node.get('field')] if f and context.get(f) is None]
            if absent:
                missing=True;passed=False;detail='缺少规则输入：'+', '.join(sorted(set(absent)))
            else:passed,detail=evaluate_node(node,context)
            active[k]=passed;conditions.append({'node':node.get('name',k),'passed':passed,'detail':detail})
        else:
            active[k]=True;actions.append({'action':config.get('action') or node.get('action'),'label':node.get('name') or node.get('label'),'message':config.get('message',''),'notify':config.get('notify',[])})
    return conditions,actions,missing
