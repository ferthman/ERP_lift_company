from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required, current_user
from ..db import SessionLocal, Building, Ticket
from ..utils.security import role_required
from ..utils.audit import log_audit
from ..assets.service import normalize_text
from ..assets.routes import serialize_asset
from ..tickets.repository import serialize_ticket
from .service import serialize_building, building_values

bp = Blueprint('buildings', __name__)

@bp.get('/api/buildings')
@login_required
@role_required('admin','dispatcher')
def list_buildings():
    q = normalize_text(request.args.get('q'))
    with SessionLocal() as db:
        buildings = db.query(Building).order_by(Building.name).all()
        return jsonify([serialize_building(b) for b in buildings if not q or q in normalize_text(f'{b.name} {b.address} {b.contact_person or ""}')])

@bp.post('/api/buildings')
@login_required
@role_required('admin','dispatcher')
def create_building():
    with SessionLocal() as db:
        try: values = building_values(db, request.get_json() or {})
        except ValueError as e: return jsonify(error=str(e)),400
        duplicate = db.query(Building).filter_by(address_norm=values['address_norm'], customer_id=values['customer_id'], contract_id=values['contract_id']).first()
        if duplicate: return jsonify(error='Объект с этим адресом и договором уже существует'),409
        b = Building(**values)
        db.add(b); db.flush()
        log_audit(db,entity_type='building',entity_id=b.id,action='CREATE',actor_user_id=current_user.id,old={},new=values)
        db.commit()
        return jsonify(serialize_building(b)),201

@bp.patch('/api/buildings/<int:building_id>')
@login_required
@role_required('admin','dispatcher')
def update_building(building_id):
    with SessionLocal() as db:
        b = db.get(Building,building_id)
        if not b: return jsonify(error='Объект не найден'),404
        try: values = building_values(db,request.get_json() or {},b)
        except ValueError as e: return jsonify(error=str(e)),400
        duplicate = db.query(Building).filter_by(address_norm=values['address_norm'],customer_id=values['customer_id'],contract_id=values['contract_id']).filter(Building.id != b.id).first()
        if duplicate: return jsonify(error='Объект с этим адресом и договором уже существует'),409
        old = {k:getattr(b,k) for k in values}
        for k,v in values.items(): setattr(b,k,v)
        # Current lift context follows the building. Ticket snapshots stay intact.
        for asset in b.assets:
            for key in ('address','address_norm','customer_id','contract_id'): setattr(asset,key,getattr(b,key))
        log_audit(db,entity_type='building',entity_id=b.id,action='UPDATE',actor_user_id=current_user.id,old=old,new=values)
        db.commit()
        return jsonify(serialize_building(b))

@bp.get('/api/buildings/<int:building_id>/summary')
@login_required
@role_required('admin','dispatcher')
def building_summary(building_id):
    with SessionLocal() as db:
        b = db.get(Building,building_id)
        if not b: return jsonify(error='Объект не найден'),404
        tickets = db.query(Ticket).filter_by(building_id=b.id).order_by(Ticket.created_at.desc()).all()
        return jsonify(building=serialize_building(b), lifts=[serialize_asset(a) for a in b.assets],
            active_tickets=[serialize_ticket(t) for t in tickets if t.archived_at is None and t.status not in ('COMPLETED','CANCELLED')],
            latest_tickets=[serialize_ticket(t) for t in tickets[:20]])

@bp.get('/buildings/<int:building_id>')
@login_required
@role_required('admin','dispatcher')
def building_page(building_id):
    return render_template('building_detail.html',building_id=building_id)
