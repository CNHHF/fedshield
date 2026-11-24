"""End-to-end local workflow, source/policy/ciphertext vault and experiments."""
import csv
import base64
import hashlib
import io
import math
import time
import uuid
from datetime import datetime

from flask import Blueprint, current_app, request, Response
from sqlalchemy import update

from ..audit import logger as audit_logger
from ..compliance import regulation_lib, rule_engine
from ..crypto import policy, vault
from ..engine import workbench as core
from ..engine import public_dataset
from ..engine.privacy_release import release
from ..extensions import db
from ..models import (BudgetItem, BudgetTrend, Transaction, WorkbenchExperiment,
                      WorkbenchImport, WorkbenchRun, WorkbenchMaterial, ComplianceRule, iso, now)
from ..utils.deps import auth_required, current_user, require_permission
from ..utils.response import ApiError, body, ok

bp = Blueprint("workbench", __name__, url_prefix="/api/workbench")
REGIONS = {"CN": "中国", "EU": "欧盟", "US": "美国", "SEA": "东南亚", "APAC": "亚太",
           "ME": "中东", "AF": "非洲", "LATAM": "拉丁美洲", "UK": "英国", "NA": "北美其他地区", "OTHER": "其他或未细分地区"}
DECISIONS = {"approve": "自动通过", "reject": "自动拒绝", "manual": "待人工复核", "blocked": "合规阻断"}
IMPORT_FIELDS={'code','merchantCode','amount','currency','region','destRegion','category','account','counterparties','occurredAt'}


def identity():
    return current_user().username


def require_public_database():
    if not current_app.testing and not public_dataset.available():
        raise ApiError('真实交易数据库未就绪，请运行 python tools/import_public_transactions.py；不会回退模拟数据',code=503)


def current_model(rows=None):
    require_public_database()
    real=public_dataset.available() if rows is None else bool(rows) and all(r.get('datasetId')=='uci-online-retail-352' for r in rows)
    if real:
        from ..engine.public_risk import model
        return model()[4]
    if current_app.testing:return core.model()[2]
    return {'name':'该导入来源尚未配置模型，转人工核查','kind':'unavailable','trainingRows':0,'validationRows':0,'validationAuc':None,'features':[],'scope':'不会把合成标签模型应用于未核验的导入来源。'}


def seal(rows):
    """Store source snapshots encrypted; originals are decrypted only locally."""
    token, _ = vault.encrypt({"rows": rows})
    return {"format": "local-vault-v1", "ciphertext": token}


def unseal(value):
    # Accept development snapshots created before encryption-at-rest was added.
    if isinstance(value, dict):
        if value.get("format") == "local-vault-v1":
            return vault.decrypt(value["ciphertext"])["rows"]
        return policy.decrypt_payload(value["sealed"])["rows"]
    return value or []


def owned_run(run_id):
    row = WorkbenchRun.query.filter_by(id=run_id, actor=identity()).first()
    if row is None:
        raise ApiError("流程不存在或无权访问", code=404)
    return row


def seeded(t):
    return {"key": f"seed:{t.id}", "code": t.code, "merchantCode": t.merchantCode,
        "region": t.region, "destRegion": t.destRegion, "amount": t.amount,
        "currency": t.currency, "category": t.category, "counterparties": t.counterparties,
        "occurredAt": iso(t.occurredAt), "origin": "项目内置仿真交易"}


def sources(include_imports=False):
    require_public_database()
    real = public_dataset.available()
    rows = public_dataset.orders()[0] if real else [seeded(t) for t in Transaction.query.order_by(Transaction.id).all()]
    if real and not include_imports:return rows
    for batch in WorkbenchImport.query.filter_by(actor=identity()).order_by(WorkbenchImport.createdAt.desc()).all():
        for i, r in enumerate(unseal(batch.records)):
            rows.append({**{k:v for k,v in r.items() if k in IMPORT_FIELDS}, "key": f"import:{batch.id}:{i}", "origin": batch.filename})
    return rows


def serialize(run, detail=True):
    data = {"id": run.id, "status": run.status, "version": run.version,
        "createdAt": iso(run.createdAt), "updatedAt": iso(run.updatedAt), "config": run.config,
        "count": len(unseal(run.source)), "stages": run.stages or []}
    if detail:
        data["materials"] = [material_meta(m) for m in material_rows(run)]
        data["decisions"] = [{**r, "finalDecision": (run.reviews or {}).get(r["code"], {}).get("decision", r["decision"]),
            "review": (run.reviews or {}).get(r["code"])} for r in (run.decisions or [])]
        data["protected"] = [{"code": r["code"], "groups": [{"level": e["level"], "cipher": e["cipher"],
            "digest": e["digest"], "length": e["length"], "ciphertext": e["ciphertext"]}
            for e in r["envelopes"]]} for r in (run.protected or [])]
    return data


MATERIAL_KINDS = {"authorization": "处理授权", "basis": "跨境传输依据", "assessment": "影响评估"}


def material_rows(run):
    return WorkbenchMaterial.query.filter_by(runId=run.id, actor=identity()).order_by(WorkbenchMaterial.createdAt).all()


def material_meta(m):
    return {"id": m.id, "kind": m.kind, "kindName": MATERIAL_KINDS[m.kind],
            "filename": m.filename, "digest": m.digest, "size": m.size, "createdAt": iso(m.createdAt)}


@bp.post("/runs/<run_id>/materials")
@auth_required
@require_permission("engine:task:manage")
def upload_material(run_id):
    run = owned_run(run_id)
    if any(s["key"] == "compliance" for s in run.stages or []):
        raise ApiError("合规结果已固定，请新建流程提交新材料", code=409)
    kind, file = request.form.get("kind"), request.files.get("file")
    if kind not in MATERIAL_KINDS or file is None:
        raise ApiError("请选择材料类型和文件")
    name = (file.filename or "").replace("\\", "/").split("/")[-1]
    if not name or len(name) > 160 or any(ord(c) < 32 for c in name):
        raise ApiError("文件名无效")
    content = file.stream.read(2*1024*1024+1)
    if not content or len(content) > 2*1024*1024:
        raise ApiError("材料限 2 MB，且不能为空")
    suffix = name.rsplit(".", 1)[-1].lower()
    if suffix == "pdf":
        if not content.startswith(b"%PDF-"):
            raise ApiError("PDF 文件头无效")
    elif suffix in ("txt", "csv"):
        try:
            decoded = content.decode("utf-8-sig")
            if "\x00" in decoded:
                raise ValueError()
        except (UnicodeError, ValueError):
            raise ApiError("文本材料须为 UTF-8 编码")
    else:
        raise ApiError("支持 PDF、UTF-8 TXT 或 CSV")
    claimed = db.session.execute(update(WorkbenchRun).where(WorkbenchRun.id == run.id,
        WorkbenchRun.version == run.version).values(version=run.version+1))
    if claimed.rowcount != 1:
        db.session.rollback()
        raise ApiError("流程已更新，请刷新后提交", code=409)
    if len(material_rows(run)) >= 6:
        raise ApiError("单个流程最多 6 份材料")
    token, _ = vault.encrypt({"base64": base64.b64encode(content).decode("ascii")})
    m = WorkbenchMaterial(id="MAT-"+uuid.uuid4().hex, runId=run.id, actor=identity(), kind=kind,
        filename=name, digest=hashlib.sha256(content).hexdigest(), size=len(content), sealed={"ciphertext": token})
    db.session.add(m)
    audit_logger.record_from_request("workflow.material", target=run.id, operation="创建",
        detail=f"登记材料 {m.id}，SHA-256 {m.digest}", commit=False)
    db.session.commit()
    return ok(serialize(run))


@bp.get("/runs/<run_id>/materials/<material_id>")
@auth_required
@require_permission("engine:task:manage")
def download_material(run_id, material_id):
    run = owned_run(run_id)
    m = WorkbenchMaterial.query.filter_by(id=material_id, runId=run.id, actor=identity()).first()
    if m is None:
        raise ApiError("材料不存在", code=404)
    from urllib.parse import quote
    content = base64.b64decode(vault.decrypt(m.sealed["ciphertext"])["base64"])
    return Response(content, mimetype="application/octet-stream", headers={
        "Content-Disposition": "attachment; filename*=UTF-8''"+quote(m.filename, safe=""),
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@bp.get("/overview")
@auth_required
@require_permission("engine:task:manage")
def overview():
    require_public_database()
    own = WorkbenchRun.query.filter_by(actor=identity())
    runs = own.order_by(WorkbenchRun.createdAt.desc()).limit(10).all()
    return ok({"regions": [{"value": k, "label": v} for k, v in REGIONS.items()],
        "sourceCount": public_dataset.manifest()['eligibleOrders'] if public_dataset.available() else len(sources()), "sourceMode": "public" if public_dataset.available() else "fixture", "policy": regulation_lib.coverage_stats(),
        "protectedCount": sum(len(r.protected or []) for r in own.all()),
        "runs": [serialize(r, False) for r in runs], "model": current_model(),
        "stages": [{"key": k, "title": title} for k, title in core.STAGES]})


@bp.get("/sources")
@auth_required
@require_permission("engine:task:manage")
def source_list():
    if request.args.get('scope')=='bank':
        from ..engine import financial_warehouse
        if not financial_warehouse.available():raise ApiError('金融数据仓未就绪，不回退零售或模拟记录',code=503)
        try:page,size=max(1,int(request.args.get('page',1))),max(1,min(100,int(request.args.get('size',20))))
        except ValueError:raise ApiError('分页参数必须为整数')
        if request.args.get('region') not in (None,'','EU'):return ok({'items':[],'total':0,'page':page,'size':size,'sourceMode':'bank'})
        rows,total=financial_warehouse.bank_orders(page=page,size=size,q=request.args.get('q','')[:100])
        return ok({'items':rows,'total':total,'page':page,'size':size,'sourceMode':'bank'})
    require_public_database()
    if public_dataset.available() and request.args.get('scope')!='imports':
        try:page,size=max(1,int(request.args.get('page',1))),max(1,min(100,int(request.args.get('size',20))))
        except ValueError:raise ApiError('分页参数必须为整数')
        rows,total=public_dataset.orders(q=request.args.get('q','').strip(),region=request.args.get('region',''),page=page,size=size)
        return ok({'items':rows,'total':total,'page':page,'size':size,'sourceMode':'public'})
    rows = sources(include_imports=True)
    if public_dataset.available():rows=[r for r in rows if r['key'].startswith('import:')]
    q = request.args.get("q", "").strip().lower()
    region = request.args.get("region", "")
    if region:
        rows = [r for r in rows if r["region"] == region]
    if q:
        rows = [r for r in rows if q in str(r).lower()]
    try:
        page, size = max(1, int(request.args.get("page", 1))), max(1, min(100, int(request.args.get("size", 20))))
    except ValueError as exc:
        raise ApiError("分页参数必须是整数") from exc
    return ok({"items": rows[(page-1)*size:page*size], "total": len(rows), "page": page, "size": size})


@bp.get('/public-records/<code>')
@auth_required
@require_permission('engine:task:manage')
def public_record(code):
    if not public_dataset.available():raise ApiError('公开数据库未就绪',code=404)
    try:page=max(1,int(request.args.get('page',1)))
    except ValueError:raise ApiError('分页参数无效')
    result=public_dataset.raw_record(code,page)
    if result is None:raise ApiError('记录不存在',code=404)
    return ok(result)


@bp.get("/provenance")
@auth_required
@require_permission("engine:task:manage")
def provenance():
    require_public_database()
    """Account-scoped inventory; imported files are not asserted to be authentic."""
    if public_dataset.available():
        m=public_dataset.manifest()
        return ok({'total':m['eligibleOrders'],'seeded':0,'imported':0,'merchants':1,'currencies':['GBP'],
            'generator':'UCI 官方下载 → 原始明细入库 → 发票汇总','source':m['name']+' · 真实公开交易；默认业务库不再使用模拟交易。',
            'imports':[],'fields':[{'key':k,'name':core.FIELDS[k][0],'level':core.FIELDS[k][1],'basis':basis} for k,basis in public_dataset.FIELD_MAP.items()],
            'model':current_model(), 'modelSource':'真实订单按时间划分；Isolation Forest无监督异常初筛，不是合成标签分类器。', 'dataset':m})
    rows = sources()
    return ok({
        "total": len(rows),
        "seeded": sum(r["key"].startswith("seed:") for r in rows),
        "imported": sum(r["key"].startswith("import:") for r in rows),
        "merchants": len({r["merchantCode"] for r in rows}),
        "currencies": sorted({r["currency"] for r in rows}),
        "generator": "backend/seed.py · random.Random(20260518)",
        "source": "项目生成的仿真交易；非企业客户数据，也不是公开金融数据集。",
        "imports": [{"filename": b.filename, "count": len(unseal(b.records)), "createdAt": iso(b.createdAt)}
                    for b in WorkbenchImport.query.filter_by(actor=identity()).order_by(WorkbenchImport.createdAt.desc()).all()],
        "fields": [{"key": k, "name": name, "level": level, "basis": "项目字段字典；不是法规自动定级"}
                   for k, (name, level) in core.FIELDS.items()],
        "model": core.model()[2],
        "modelSource": "backend/engine/workbench.py · seed=20261105 · 合成标签 · 1800 训练 / 600 留出",
    })


@bp.post("/imports")
@auth_required
@require_permission("engine:task:create")
def import_csv():
    file = request.files.get("file")
    if file is None:
        raise ApiError("请选择 CSV 文件")
    raw = file.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ApiError("CSV 不得超过 2 MB")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        required = {"code", "merchantCode", "amount", "currency", "region", "destRegion"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("缺少必填列：" + ", ".join(sorted(required)))
        rows, codes = [], set()
        for i, record in enumerate(reader):
            if i >= 500:
                raise ValueError("单次最多导入 500 行")
            r = {k: str(record.get(k) or "").strip() for k in IMPORT_FIELDS if record.get(k) is not None}
            if any(len(v) > 160 for v in r.values()) or not all(r.get(k) for k in required):
                raise ValueError(f"第 {i+2} 行缺少字段或字段过长")
            if r["code"] in codes:
                raise ValueError(f"第 {i+2} 行交易编号重复")
            codes.add(r["code"])
            r["amount"] = float(r["amount"])
            r["counterparties"] = int(r.get("counterparties") or 1)
            if not math.isfinite(r["amount"]) or not 0 <= r["amount"] <= 1e12 or not 1 <= r["counterparties"] <= 10000:
                raise ValueError(f"第 {i+2} 行金额或交易对手数超出范围")
            if r["region"] not in REGIONS or r["destRegion"] not in REGIONS:
                raise ValueError(f"第 {i+2} 行地区编码不支持")
            r["occurredAt"] = r.get("occurredAt") or now().strftime("%Y-%m-%d %H:%M:%S")
            datetime.strptime(r["occurredAt"], "%Y-%m-%d %H:%M:%S")
            rows.append(r)
        if not rows:
            raise ValueError("CSV 中没有交易数据")
    except (UnicodeError, ValueError, csv.Error, TypeError) as exc:
        raise ApiError(str(exc)) from exc
    batch = WorkbenchImport(id=uuid.uuid4().hex, actor=identity(), filename=(file.filename or "导入交易.csv")[:160], records=seal(rows))
    db.session.add(batch)
    audit_logger.record_from_request("data.import", target=batch.id, operation="创建", detail=f"导入 {len(rows)} 条交易；不在日志中记录原始字段")
    return ok({"id": batch.id, "count": len(rows)})


@bp.get("/protected")
@auth_required
@require_permission("engine:task:manage")
def protected_list():
    rows = WorkbenchRun.query.filter_by(actor=identity()).order_by(WorkbenchRun.createdAt.desc()).all()
    return ok([{**record, "runId": run.id, "createdAt": iso(run.createdAt)}
               for run in rows for record in serialize(run)["protected"]])


@bp.post("/runs")
@auth_required
@require_permission("engine:task:create")
def create_run():
    p = body()
    if not isinstance(p, dict):
        raise ApiError("请求必须是 JSON 对象")
    keys = p.get("keys")
    if not isinstance(keys, list) or not 2 <= len(keys) <= 100 or any(not isinstance(k, str) for k in keys) or len(set(keys)) != len(keys):
        raise ApiError("请选择 2–100 条不同交易")
    financial=any(k.startswith('finance:') for k in keys)
    if financial:
        from ..engine import financial_warehouse
        if not all(k.startswith('finance:') for k in keys):raise ApiError('银行流水与其他来源请分开建流程')
        if not financial_warehouse.available():raise ApiError('金融数据仓未就绪',code=503)
        bank_rows,_=financial_warehouse.bank_orders(keys=keys,size=100)
        mapping={r['key']:r for r in bank_rows}
    else:mapping = {r["key"]: r for r in sources(include_imports=True)}
    if any(k not in mapping for k in keys):
        raise ApiError("所选交易不存在或无权访问")
    if len({mapping[k]["code"] for k in keys}) != len(keys):
        raise ApiError("同一流程不能包含重复的交易编号，请选择唯一编号的交易")
    currencies = {mapping[k]["currency"] for k in keys}
    if len({mapping[k].get('datasetId','custom') for k in keys})!=1:
        raise ApiError('请将不同数据来源分开建流程，以便核对模型和统计口径')
    if len(currencies) != 1:
        raise ApiError("请选择同一币种的交易，不能直接合并不同币种统计")
    try:
        config = {"targetRegion": p.get("targetRegion", "EU"), "epsilon": float(p.get("epsilon", 1)),
            "lower": float(p.get("lower", 0)), "upper": float(p.get("upper", 1000000)),
            "budgetId": int(p.get("budgetId")), "authorized": p.get("authorized") is True,
            "transferBasis": p.get("transferBasis") is True, "impactAssessment": p.get("impactAssessment") is True}
        if config["targetRegion"] not in REGIONS:
            raise ValueError("目的地区无效")
        config["currency"] = next(iter(currencies))
        config["evidenceVersion"] = 1
        business_id=p.get('businessConfigId') or ''
        if not isinstance(business_id,str) or len(business_id)>48:raise ValueError('业务方案编号无效')
        if business_id:
            from ..models import BusinessConfiguration
            from ..crypto import vault
            business=BusinessConfiguration.query.filter_by(id=business_id,owner=current_user().username,state='saved').first()
            if not business:raise ValueError('业务方案不存在或尚未保存规则')
            business_plan=vault.decrypt(business.payload)['plan']
            if business_plan['region']!=config['targetRegion']:raise ValueError('业务方案与处理目的地区域不一致')
            config['businessConfigId']=business_id
            config['businessSummary']=business_plan['summary']
        if public_dataset.available() and all(mapping[k].get('datasetId')=='uci-online-retail-352' for k in keys):
            config['sourceDataset']=public_dataset.manifest()
        if financial:
            src=financial_warehouse.source_detail('CTU-BERKA')
            config['financialSource']={k:src[k] for k in ('id','title','source_url','citation','limitations','files','lineage')}
        release([mapping[k]["amount"] for k in keys], config["lower"], config["upper"], config["epsilon"], "mean")
    except (ValueError, TypeError, OverflowError) as exc:
        raise ApiError(str(exc)) from exc
    row = WorkbenchRun(id="WF-"+uuid.uuid4().hex[:16], actor=identity(), config=config,
        source=seal([mapping[k] for k in keys]), stages=[], protected=[], decisions=[], reviews={})
    db.session.add(row)
    db.session.commit()
    return ok(serialize(row))


def compliance_result(run):
    cfg = run.config
    regions = sorted({r["region"] for r in unseal(run.source)})
    target = cfg["targetRegion"]
    relevant = [r for r in regulation_lib.all_regulations() if r.get("verified") and r["region"] in regions+[target]]
    # These are declared prototype gates, not a legal determination inferred from summaries.
    cross_border = any(r != target for r in regions)
    checks = [{"key": "authorization", "name": "处理授权", "passed": cfg["authorized"],
               "actual": "已登记" if cfg["authorized"] else "缺少授权", "required": "数据处理授权凭证"}]
    if cross_border:
        checks.append({"key": "basis", "name": "跨境传输依据", "passed": cfg["transferBasis"],
            "actual": "已登记" if cfg["transferBasis"] else "缺少传输依据", "required": "有效的出境机制或合同凭证"})
    if cross_border and any(r in ("CN", "EU") for r in regions+[target]):
        checks.append({"key": "assessment", "name": "影响评估", "passed": cfg["impactAssessment"],
            "actual": "已登记" if cfg["impactAssessment"] else "缺少评估", "required": "按适用场景登记影响评估"})
    if not relevant:
        checks.append({"key": "coverage", "name": "规则覆盖", "passed": False,
            "actual": "仅有地区模板", "required": "补充经核验的适用规则"})
    evidence = material_rows(run)
    if cfg.get("evidenceVersion") == 1 or not any(s["key"] == "compliance" for s in run.stages or []):
        for check in list(checks):
            if check["key"] in MATERIAL_KINDS:
                present = any(m.kind == check["key"] for m in evidence)
                checks.append({"key": check["key"]+"_material", "name": MATERIAL_KINDS[check["key"]]+"材料",
                    "passed": present, "actual": "已上传，内容待人工审查" if present else "未上传",
                    "required": "上传"+MATERIAL_KINDS[check["key"]]+"文件"})
    rule_results = []
    source_rows=unseal(run.source)
    from .compliance import _owns_business_rule
    rules = [r.to_dict() for r in ComplianceRule.query.filter_by(enabled=True, scene="data_transfer").all() if _owns_business_rule(r)]
    for region in regions:
        evaluated=[]
        for row in source_rows:
            if row['region']!=region:continue
            context = {"event": "data.transfer", "dataLevel": "P1", "sourceRegion": region,
                "targetRegion": target, "crossBorder": region != target, "authorized": cfg["authorized"],
                "hasScc": cfg["transferBasis"], "hasDpia": cfg["impactAssessment"],
                "purpose": "交易风控", "fieldCount": len(source_rows), "amount":row['amount'],
                "currency":row['currency'],'businessConfigId':cfg.get('businessConfigId',''),'lineCount':row.get('lineCount'), 'quantity':row.get('quantity'),
                'customerCountry':row.get('customerCountry'), 'customerIdPresent':bool(row.get('customerId'))}
            result=rule_engine.evaluate(rules,context)
            for item in result['checkedRules']:item['recordCode']=row['code']
            evaluated.append(result)
        result={'passed':all(e['passed'] for e in evaluated),'checkedRules':[r for e in evaluated for r in e['checkedRules']],
                'rectificationList':[r for e in evaluated for r in e['rectificationList']]}
        rule_results.append({"sourceRegion": region, **result,
            "versions": [{"code": r["code"], "version": r.get("version", 1)} for r in rules]})
    return {"passed": all(c["passed"] for c in checks) and all(r["passed"] for r in rule_results), "sourceRegions": regions, "targetRegion": target,
        "checks": checks, "policies": [{"code": r["code"], "name": r["name"], "regionName": r["regionName"]} for r in relevant],
        "rules": rule_results, "materials": [material_meta(m) for m in evidence],
        "scope": "项目演示门禁；勾选表示演示凭证，不代表已审查合同或取得监管许可。地区模板不作为阻断依据。"}


@bp.post("/runs/<run_id>/advance")
@auth_required
@require_permission("engine:task:manage")
def advance(run_id):
    run = owned_run(run_id)
    p = body()
    if not isinstance(p, dict) or not isinstance(p.get("stage"), str):
        raise ApiError("请指定阶段")
    key = p["stage"]
    if key in [s["key"] for s in run.stages or []]:
        return ok(serialize(run))  # Retrying a completed stage never spends twice.
    index = len(run.stages or [])
    if index >= len(core.STAGES) or key != core.STAGES[index][0]:
        raise ApiError("阶段顺序不正确", code=409)
    claimed = db.session.execute(update(WorkbenchRun).where(WorkbenchRun.id == run.id,
        WorkbenchRun.version == run.version).values(version=run.version+1))
    if claimed.rowcount != 1:
        db.session.rollback()
        raise ApiError("流程已更新，请刷新后继续", code=409)
    started = time.perf_counter()
    source_rows = unseal(run.source)
    if isinstance(run.source, list):
        run.source = seal(source_rows)
    detail = {}
    if key == "classify":
        fields = sorted({k for r in source_rows for k in r if k in core.FIELDS})
        detail = {"fields": [{"key": k, "name": core.FIELDS[k][0], "level": core.FIELDS[k][1],
                              "method": "字段字典规则"} for k in fields], "count": len(source_rows)}
    elif key == "protect":
        cfg = run.config
        if not compliance_result(run)["passed"]:
            raise ApiError("申报预检未通过，请补齐材料及凭证或检查规则；本次未扣减隐私预算", code=409)
        changed = db.session.execute(update(BudgetItem).where(BudgetItem.id == cfg["budgetId"],
            BudgetItem.used + cfg["epsilon"] <= BudgetItem.total).values(used=BudgetItem.used+cfg["epsilon"]))
        if changed.rowcount != 1:
            db.session.rollback()
            raise ApiError("隐私预算不存在或 ε 不足，未执行发布", code=409)
        stat = release([r["amount"] for r in source_rows], cfg["lower"], cfg["upper"], cfg["epsilon"], "mean")
        protected = []
        for row in source_rows:
            envelopes = []
            for level in ("P1", "P2", "P3"):
                fields = {k: v for k, v in row.items() if k in core.FIELDS and core.FIELDS[k][1] == level}
                if not fields:
                    continue
                # Exact transaction values remain encrypted for local risk analysis.
                # DP is applied only to the aggregate publication above.
                env = core.encrypt_record(level, fields)
                envelopes.append(env)
            protected.append({"code": row["code"], "envelopes": envelopes})
        run.protected = protected
        budget = db.session.get(BudgetItem, cfg["budgetId"])
        db.session.add(BudgetTrend(month=now().strftime("%Y-%m"), used=budget.used,
            remaining=max(0, budget.total-budget.used), usedRatio=budget.used/budget.total, scene="工作台统计发布"))
        detail = {"count": len(protected), "publication": stat, "remaining": round(budget.total-budget.used, 4),
            "proofs": [{"level": e["level"], "length": e["length"], "cipher": e["cipher"], "digest": e["digest"],
                        "keyProtection": "随机 SM4 数据密钥经 Paillier 封装" if e["level"] == "P1" else "本地主密钥 · 随机 nonce · 认证标签"}
                       for e in protected[0]["envelopes"]],
            "policy": "P1：SM4 + Paillier 密钥封装；P2/P3：AES-GCM；仅统计出口消耗 ε 并加噪"}
    elif key == "compliance":
        detail = compliance_result(run)
    elif key == "risk":
        compliant = next(s["detail"]["passed"] for s in run.stages if s["key"] == "compliance")
        # Authenticate/decrypt the actual saved envelopes locally, not the browser's input.
        restored = []
        for encrypted in run.protected:
            row = {}
            for env in encrypted["envelopes"]:
                row.update(core.decrypt_record(env))
            restored.append(row)
        decisions = [core.score(r, compliant) for r in restored]
        run.decisions = decisions
        counts = {k: sum(r["decision"] == k for r in decisions) for k in DECISIONS}
        detail = {"counts": counts, "model": current_model(restored), "automationRate":
            (counts["approve"]+counts["reject"]+counts["blocked"])/len(decisions),
            "scope": "本地授权解密后分析，不是密文推理；真实公开订单按异常分位初筛，无欺诈标签，不生成欺诈概率。" if restored and restored[0].get('datasetId') else "本地授权解密后推理；低置信度记录进入人工队列。"}
    else:
        log = audit_logger.record_from_request("workflow.finish", target=run.id, operation="创建",
            detail=f"流程完成，{len(source_rows)} 笔；仅存证流程标识和操作摘要", on_chain=True, commit=False)
        detail = {"auditId": log.id, "chainTxId": log.chainTxId, "hash": log.hash,
                  "scope": "本地链式哈希存证，不是生产 Fabric 网络"}
        run.status = "completed"
    run.stages = [*(run.stages or []), {"key": key, "title": core.STAGES[index][1], "detail": detail,
        "durationMs": round((time.perf_counter()-started)*1000, 2), "finishedAt": iso(now())}]
    if key != "audit":
        run.status = "running"
    db.session.commit()
    return ok(serialize(run))


@bp.get("/runs/<run_id>/precheck")
@auth_required
@require_permission("engine:task:manage")
def precheck(run_id):
    return ok(compliance_result(owned_run(run_id)))


@bp.get("/runs/<run_id>/report")
@auth_required
@require_permission("engine:task:manage")
def workflow_report(run_id):
    run = owned_run(run_id)
    from ..engine.workflow_report import build_report
    saved = next((s["detail"] for s in run.stages or [] if s["key"] == "compliance"), None)
    report = build_report(run, unseal(run.source), saved if saved is not None else compliance_result(run), saved is not None)
    return ok(report)


@bp.get("/runs/<run_id>")
@auth_required
@require_permission("engine:task:manage")
def get_run(run_id):
    return ok(serialize(owned_run(run_id)))


@bp.post("/runs/<run_id>/review")
@auth_required
@require_permission("engine:task:manage")
def review_record(run_id):
    run = owned_run(run_id)
    p = body()
    if not isinstance(p, dict):
        raise ApiError("请求必须是 JSON 对象")
    matches = [r for r in (run.decisions or []) if r["code"] == p.get("code")]
    if len(matches) != 1:
        raise ApiError("交易编号不存在或不唯一，不能登记复核")
    record = matches[0]
    if not record or record["decision"] != "manual" or p.get("decision") not in ("approve", "reject"):
        raise ApiError("仅可复核待人工记录，合规阻断不可人工绕过")
    note = p.get("note")
    if not isinstance(note, str) or not 4 <= len(note.strip()) <= 300:
        raise ApiError("请填写 4–300 字的复核依据")
    if record["code"] in (run.reviews or {}):
        raise ApiError("该记录已完成复核", code=409)
    claimed = db.session.execute(update(WorkbenchRun).where(WorkbenchRun.id == run.id,
        WorkbenchRun.version == run.version).values(version=run.version+1))
    if claimed.rowcount != 1:
        db.session.rollback()
        raise ApiError("复核记录已更新，请刷新后重试", code=409)
    run.reviews = {**(run.reviews or {}), record["code"]: {"decision": p["decision"], "note": note.strip(),
        "actor": identity(), "at": iso(now())}}
    audit_logger.record_from_request("workflow.review", target=run.id, operation="修改", detail=f"人工复核 {record['code']}：{p['decision']}", on_chain=True, commit=False)
    db.session.commit()
    return ok(serialize(run))


@bp.post("/experiments")
@auth_required
@require_permission("engine:task:manage")
def experiment():
    p = body()
    if not isinstance(p, dict):
        raise ApiError("请求必须是 JSON 对象")
    run = owned_run(p.get("runId"))
    if not run.protected:
        raise ApiError("请先完成流程的加密阶段")
    kind = p.get("kind")
    if kind == "tamper":
        env = next(e for e in run.protected[0]["envelopes"] if e["cipher"] == "AES-256-GCM")
        result = core.tamper_experiment(env)
    elif kind == "poisoning":
        result = core.poisoning_experiment()
    else:
        raise ApiError("不支持的实验类型")
    item = WorkbenchExperiment(id="EXP-"+uuid.uuid4().hex[:12], actor=identity(), runId=run.id, kind=kind, result=result)
    db.session.add(item)
    audit_logger.record_from_request("security.experiment", target=item.id, operation="创建", detail=f"隔离实验：{kind}；未更改密文库", on_chain=True)
    return ok({"id": item.id, "createdAt": iso(item.createdAt), **result})


@bp.post("/ask")
@auth_required
@require_permission("engine:task:manage")
def ask():
    p = body()
    if not isinstance(p, dict) or not isinstance(p.get("question"), str) or not 1 <= len(p["question"].strip()) <= 500:
        raise ApiError("问题长度应为 1–500 字")
    run = owned_run(p.get("runId")) if p.get("runId") else WorkbenchRun.query.filter_by(actor=identity()).order_by(WorkbenchRun.createdAt.desc()).first()
    if run is None:
        return ok({"answer": "还没有处理流程。请在业务工作台选取交易并运行，我可以解释分级、加噪、合规门禁和初筛结果。", "mode": "本地检索", "tools": []})
    import json
    q = p["question"].strip()
    tools = [{"name": "读取流程记录", "result": run.id}]
    stages = {s["key"]: s["detail"] for s in run.stages or []}
    counts = {k: sum(r["finalDecision"] == k for r in serialize(run)["decisions"]) for k in DECISIONS}
    lines = [f"流程 {run.id}，{len(unseal(run.source))} 笔，已完成 {len(run.stages)}/5 阶段。",
             "当前结论："+"、".join(f"{DECISIONS[k]} {v} 笔" for k, v in counts.items())+"。"]
    compliance = stages.get("compliance")
    if compliance:
        tools.append({"name": "核对合规门禁", "result": "通过" if compliance["passed"] else "需补充凭证"})
        failed = [c["required"] for c in compliance["checks"] if not c["passed"]]
        lines.append("合规门禁："+("已满足本次演示门禁。" if not failed else "缺少 "+"、".join(failed)+"，当前流程不会放行。"))
        lines.append("适用条目："+"、".join(r["code"] for r in compliance["policies"])+"；演示策略不能替代法务审查。")
    if "protect" in stages:
        pub = stages["protect"]["publication"]
        tools.append({"name": "核对隐私发布", "result": f"ε={pub['epsilon']}"})
        lines.append(f"统计发布消耗 ε={pub['epsilon']}，裁剪范围 [{pub['lower']}, {pub['upper']}]，敏感度={pub['sensitivity']:.4f}，噪声尺度={pub['noiseScale']:.4f}。逐笔金额仅本地加密保存；授权解密后推理。")
    manual = [r for r in serialize(run)["decisions"] if r["finalDecision"] == "manual"]
    if manual:
        lines.append("待复核编号："+"、".join(r["code"] for r in manual[:8])+"；只对低置信度记录复核，无需逐条校准全部交易。")
    lines.append("本批为真实公开交易；异常分位不是欺诈概率，数据无欺诈标签，助手不执行放行或修改凭证。" if run.config.get('sourceDataset') else "该历史或导入流程须按原数据和模型口径核查；助手不执行交易放行或修改凭证。")
    answer, mode, notice = "\n".join(lines), "本地证据检索", ""
    if not current_app.testing:
        from ..engine.llm_assistant import explain
        try:
            generated = explain(q, answer)
            if generated:
                answer, mode = generated, "DeepSeek · 流程解释"
        except Exception:
            notice = "模型服务暂不可用，已返回本地证据。"
    return ok({"answer": answer, "mode": mode, "notice": notice, "tools": tools, "runId": run.id,
        "actions": [{"label": "查看该流程", "path": "/workbench?run="+run.id}], "asOf": iso(now())})
