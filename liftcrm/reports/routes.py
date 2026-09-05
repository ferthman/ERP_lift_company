"""Operational reports and scoped lookup; no financial or inferred metrics."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone, time, date
from zoneinfo import ZoneInfo
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy.orm import selectinload
from ..db import SessionLocal, Ticket, Asset, Building, Master, Customer, Contract, MaintenancePlan
from ..assets.routes import serialize_asset, serialize_maintenance_plan
from ..assets.service import normalize_text
from ..tickets.repository import serialize_ticket, compute_sla_fields
from ..utils.time import to_utc
from ..utils.security import role_required

bp = Blueprint('reports',__name__)
ACTIVE = {'NEW','ASSIGNED','ACCEPTED','IN_PROGRESS','WAITING'}
LOCAL_TZ = ZoneInfo('Asia/Almaty')


def ticket_query(db):
    return db.query(Ticket).options(selectinload(Ticket.asset).selectinload(Asset.customer),selectinload(Ticket.asset).selectinload(Asset.contract),selectinload(Ticket.building),selectinload(Ticket.assigned_master),selectinload(Ticket.attachments))


def period():
    today = datetime.now(LOCAL_TZ).date()
    try:
        start = date.fromisoformat(request.args.get('date_from') or (today-timedelta(days=29)).isoformat())
        end = date.fromisoformat(request.args.get('date_to') or today.isoformat())
    except ValueError: raise ValueError('Укажите корректные даты')
    if start > end: raise ValueError('Начало периода должно быть раньше окончания')
    return datetime.combine(start,time.min,LOCAL_TZ).astimezone(timezone.utc),datetime.combine(end+timedelta(days=1),time.min,LOCAL_TZ).astimezone(timezone.utc)


def seconds_between(start,end):
    return max(0,(to_utc(end)-to_utc(start)).total_seconds()) if start and end else None


def aggregate(tickets):
    reactions = [d for t in tickets if (d:=seconds_between(t.created_at,t.arrived_at)) is not None]
    completions = [d for t in tickets if t.status=='COMPLETED' and (d:=seconds_between(t.created_at,t.completed_at)) is not None]
    return dict(total=len(tickets),active=sum(t.status in ACTIVE and t.archived_at is None for t in tickets),completed=sum(t.status=='COMPLETED' for t in tickets),cancelled=sum(t.status=='CANCELLED' for t in tickets),
        avg_response_sec=sum(reactions)/len(reactions) if reactions else None,avg_completion_sec=sum(completions)/len(completions) if completions else None,
        sla_breaches=sum(any(compute_sla_fields(t)[key] for key in ('sla_response_breached','sla_completion_breached')) for t in tickets if t.status!='CANCELLED'),
        problem_types=dict(Counter(t.problem_type or 'UNSPECIFIED' for t in tickets)),priorities=dict(Counter(t.priority or 'MEDIUM' for t in tickets)),statuses=dict(Counter(t.status for t in tickets)))


def problem_signal(tickets,now=None):
    cutoff = (now or datetime.now(timezone.utc))-timedelta(days=30)
    recent = [t for t in tickets if t.status!='CANCELLED' and to_utc(t.created_at) and to_utc(t.created_at)>=cutoff]
    urgent = sum(t.priority in ('HIGH','EMERGENCY') for t in recent)
    return dict(flagged=len(recent)>=3 or urgent>=2,tickets_30d=len(recent),urgent_30d=urgent,rule='3 заявки или 2 срочные за 30 дней')


@bp.get('/api/dashboard')
@login_required
@role_required('admin','dispatcher')
def dashboard():
    with SessionLocal() as db:
        tickets = ticket_query(db).all()
        active = [t for t in tickets if t.archived_at is None and t.status in ACTIVE]
        overdue = [t for t in active if any(compute_sla_fields(t)[k] for k in ('sla_response_breached','sla_completion_breached'))]
        today = datetime.now(LOCAL_TZ).date()
        daily = []
        for offset in range(6,-1,-1):
            day = today-timedelta(days=offset)
            daily.append(dict(date=day.isoformat(),created=sum(bool(t.created_at) and to_utc(t.created_at).astimezone(LOCAL_TZ).date()==day for t in tickets),completed=sum(t.status=='COMPLETED' and bool(t.completed_at) and to_utc(t.completed_at).astimezone(LOCAL_TZ).date()==day for t in tickets)))
        masters = db.query(Master).order_by(Master.name).all()
        queue = sorted(active,key=lambda t:(0 if t.priority=='EMERGENCY' else 1 if t in overdue else 2, to_utc(t.created_at) or datetime.now(timezone.utc)))
        return jsonify(active=len(active),unassigned=sum(not t.assigned_master_id for t in active),overdue=len(overdue),emergency=sum(t.priority=='EMERGENCY' for t in active),completed_today=daily[-1]['completed'],
            buildings=db.query(Building).filter_by(is_active=1).count(),lifts=db.query(Asset).filter_by(status='ACTIVE').count(),
            due_maintenance=db.query(MaintenancePlan).filter(MaintenancePlan.status=='active',MaintenancePlan.next_due_date<=today).count(),
            statuses=dict(Counter(t.status for t in active)),daily=daily,attention=[serialize_ticket(t) for t in queue[:7]],
            masters=[dict(id=m.id,name=m.name,active=bool(m.is_active),backlog=sum(t.assigned_master_id==m.id for t in active)) for m in masters],updated_at=datetime.now(timezone.utc).isoformat())


@bp.get('/api/reports/overview')
@login_required
@role_required('admin','dispatcher')
def reports_overview():
    try: start,end = period()
    except ValueError as e: return jsonify(error=str(e)),400
    with SessionLocal() as db:
        query = ticket_query(db).filter(Ticket.created_at>=start,Ticket.created_at<end)
        for key in ('building_id','asset_id','assigned_master_id'):
            raw = request.args.get(key)
            if raw:
                try: value=int(raw)
                except ValueError: return jsonify(error='Некорректный фильтр'),400
                query=query.filter(getattr(Ticket,key)==value)
        tickets=query.all()
        masters=db.query(Master).order_by(Master.name).all()
        types=defaultdict(list); lifts=defaultdict(list); buildings=defaultdict(list)
        for t in tickets:
            types[t.problem_type or 'UNSPECIFIED'].append(t)
            if t.asset_id and t.status!='CANCELLED': lifts[t.asset_id].append(t)
            if t.building_id and t.status!='CANCELLED': buildings[t.building_id].append(t)
        now=datetime.now(timezone.utc)
        sla=[]
        for t in tickets:
            if t.status not in ACTIVE or t.archived_at: continue
            hours=seconds_between(t.updated_at or t.created_at,now)/3600
            threshold={'NEW':.5,'ASSIGNED':1,'ACCEPTED':2,'WAITING':24,'IN_PROGRESS':4}[t.status]
            fields=compute_sla_fields(t)
            reasons=[]
            if fields['sla_response_breached']: reasons.append('Просрочен выезд')
            if fields['sla_completion_breached']: reasons.append('Просрочено завершение')
            if hours>=threshold: reasons.append('Долго без изменений')
            if reasons: sla.append({**serialize_ticket(t),'attention_reasons':reasons,'stale_hours':round(hours,1)})
        def rank(groups,model):
            rows=[]
            for item_id,items in groups.items():
                obj=db.get(model,item_id)
                if not obj: continue
                row=dict(id=item_id,name=(obj.name if model is Building else obj.lift_label or obj.serial_no or f'Лифт #{obj.id}'),address=obj.address,**aggregate(items),last_activity=max(to_utc(t.created_at) for t in items).isoformat())
                if model is Asset: row.update(building_id=obj.building_id,customer_name=obj.customer.name if obj.customer else None)
                else: row['lift_count']=len(obj.assets)
                rows.append(row)
            return sorted(rows,key=lambda r:(-r['total'],-r['sla_breaches'],r['id']))[:20]
        return jsonify(period={'from':start.isoformat(),'to_exclusive':end.isoformat(),'basis':'Дата создания заявки, время Алматы'},overall=aggregate(tickets),
            masters=[dict(id=m.id,name=m.name,**aggregate([t for t in tickets if t.assigned_master_id==m.id])) for m in masters],
            problem_types=[dict(type=key,**aggregate(items)) for key,items in sorted(types.items(),key=lambda pair:-len(pair[1]))],
            lifts=rank(lifts,Asset),buildings=rank(buildings,Building),sla=sorted(sla,key=lambda t:-t['stale_hours']))


@bp.get('/api/lifts/<int:asset_id>/summary')
@login_required
@role_required('admin','dispatcher')
def lift_summary(asset_id):
    with SessionLocal() as db:
        a=db.get(Asset,asset_id)
        if not a: return jsonify(error='Лифт не найден'),404
        tickets=ticket_query(db).filter_by(asset_id=a.id).order_by(Ticket.created_at.desc()).all()
        return jsonify(lift=serialize_asset(a),signal=problem_signal(tickets),
            active_tickets=[serialize_ticket(t) for t in tickets if t.status in ACTIVE and t.archived_at is None],latest_tickets=[serialize_ticket(t) for t in tickets[:10]],
            maintenance=[serialize_maintenance_plan(p) for p in a.maintenance_plans])


@bp.get('/api/me/lifts/<int:asset_id>/history')
@login_required
@role_required('technician')
def technician_lift_history(asset_id):
    with SessionLocal() as db:
        permitted=db.query(Ticket.id).filter_by(asset_id=asset_id,assigned_master_id=current_user.master_id).filter(Ticket.status.in_(ACTIVE),Ticket.archived_at.is_(None)).first() if current_user.master_id else None
        if not permitted: return jsonify(error='Нет назначенной активной заявки по этому лифту'),403
        tickets=db.query(Ticket).filter_by(asset_id=asset_id).order_by(Ticket.created_at.desc()).limit(10).all()
        return jsonify(items=[dict(id=t.id,status=t.status,problem_type=t.problem_type,description=t.description,close_reason=t.close_reason,close_comment=t.close_comment,created_at=to_utc(t.created_at).isoformat() if t.created_at else None) for t in tickets])


@bp.get('/api/search')
@login_required
@role_required('admin','dispatcher','technician')
def search():
    term=normalize_text(request.args.get('q',''))
    if len(term)<2: return jsonify(items=[])
    term=term[:150]
    with SessionLocal() as db:
        tech=current_user.role=='technician'
        tq=ticket_query(db)
        if tech:
            if not current_user.master_id: return jsonify(items=[])
            tq=tq.filter_by(assigned_master_id=current_user.master_id)
        tickets=tq.order_by(Ticket.id.desc()).all()
        items=[]
        def add(kind,obj,label,detail,url):
            if sum(i['type']==kind for i in items)>=8: return
            if term in normalize_text(f'{obj.id} {label} {detail}'):
                items.append(dict(type=kind,id=obj.id,label=label,detail=detail or '',url=url))
        for t in tickets: add('ticket',t,f'Заявка #{t.id} · {t.object_name}',f'{t.address or ""} {t.description or ""}',f'/mobile?ticket={t.id}' if tech else f'/admin?ticket_id={t.id}')
        aq=db.query(Asset)
        if tech: aq=aq.filter(Asset.id.in_({t.asset_id for t in tickets if t.asset_id}))
        for a in aq.all(): add('lift',a,a.lift_label or a.serial_no or f'Лифт #{a.id}',f'{a.address} {a.serial_no or ""}',f'/mobile?ticket={next((t.id for t in tickets if t.asset_id==a.id),0)}' if tech else f'/lifts/{a.id}')
        if not tech:
            for b in db.query(Building).all(): add('building',b,b.name,b.address,f'/buildings/{b.id}')
            for c in db.query(Customer).all(): add('customer',c,c.name,c.phone,f'/admin?tab=customers&customer_id={c.id}')
            for c in db.query(Contract).all(): add('contract',c,c.title,c.contract_number,f'/admin?tab=customers&contract_id={c.id}')
            for m in db.query(Master).all(): add('master',m,m.name,m.phone,f'/admin?tab=masters&master_id={m.id}')
        return jsonify(items=items)
