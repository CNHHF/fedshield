"""Sourced financial warehouse APIs, distinct from user-private operational data."""
from flask import Blueprint,request
from ..utils.deps import auth_required
from ..utils.response import ok,ApiError,body
from ..engine import financial_warehouse as warehouse
import datetime,decimal
bp=Blueprint('finance',__name__,url_prefix='/api/finance')
@bp.before_request
def require_warehouse():
    if not warehouse.available():raise ApiError('金融数据仓尚未建成，请先运行下载和建库脚本；不回退模拟数据',code=503)
def paging():
    try:
        page=int(request.args.get('page',1));size=int(request.args.get('size',20))
        if not 1<=page<=1000000 or not 1<=size<=100:raise ValueError()
        return page,size
    except ValueError as e:raise ApiError('分页参数无效') from e
@bp.get('/overview')
@auth_required
def overview():return ok(warehouse.metadata())
@bp.get('/sources/<source_id>')
@auth_required
def source_detail(source_id):
    r=warehouse.source_detail(source_id)
    if not r:raise ApiError('来源不存在',code=404)
    return ok(r)
@bp.get('/transactions')
@auth_required
def transactions():
    page,size=paging();q=request.args.get('q','')
    if len(q)>100:raise ApiError('搜索内容过长')
    return ok(warehouse.transactions(request.args.get('source',''),q,page,size,request.args.get('label','')))
@bp.get('/transactions/<id>')
@auth_required
def transaction(id):
    r=warehouse.transaction_detail(id)
    if not r:raise ApiError('交易不存在',code=404)
    return ok(r)
@bp.get('/accounts/<id>')
@auth_required
def account(id):
    r=warehouse.account_detail(id)
    if not r:raise ApiError('账户不存在',code=404)
    return ok(r)
@bp.get('/model')
@auth_required
def model():return ok(warehouse.model_metrics())
@bp.get('/macro')
@auth_required
def macro():
    try:year=int(request.args.get('year',2024))
    except ValueError as exc:raise ApiError('年份无效') from exc
    indicator=request.args.get('indicator','BX.TRF.PWKR.CD.DT')
    if not 2000<=year<=2025 or indicator not in ('BX.TRF.PWKR.CD.DT','BM.TRF.PWKR.CD.DT'):raise ApiError('年份或指标无效')
    return ok({'items':warehouse.macro(indicator,year),'year':year,'indicator':indicator,'unit':'USD','grain':'国家/经济体年度汇总，不是逐笔或双边资金流'})
@bp.get('/fx')
@auth_required
def latest_fx():return ok(warehouse.latest_fx())
@bp.post('/fx/convert')
@auth_required
def convert():
    p=body()
    try:
        if not isinstance(p,dict):raise ValueError()
        date=p.get('date');datetime.date.fromisoformat(date);amount=decimal.Decimal(str(p.get('amount')))
        source=p.get('from');target=p.get('to')
        if not amount.is_finite() or abs(amount)>decimal.Decimal('1e12') or any(not isinstance(v,str) or len(v)!=3 or not v.isascii() or not v.isupper() for v in (source,target)):raise ValueError()
        r=warehouse.fx(date,source,target,amount)
    except (ValueError,TypeError,decimal.InvalidOperation) as exc:raise ApiError('请填写有效日期、三位币种及有限金额') from exc
    if r is None:raise ApiError('该历史日期及此前7天没有同日可用的币种对，不采用未来汇率',code=422)
    return ok(r)
@bp.post('/screen')
@auth_required
def screen():
    p=body();name=p.get('name') if isinstance(p,dict) else None
    if not isinstance(name,str) or not 2<=len(name.strip())<=160:raise ApiError('请填写2–160字的主体名称')
    return ok(warehouse.screen(name.strip()))
@bp.get('/schema')
@auth_required
def schema():return ok(warehouse.schema())
