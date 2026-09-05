from datetime import datetime, timedelta, timezone
import sqlite3
import pytest
from liftcrm import create_app, config
from liftcrm.db import SessionLocal, User, Master, Asset, Building, Ticket, init_db, ensure_migrations
from liftcrm.buildings.service import migrate_buildings
from liftcrm.tickets.repository import compute_sla_fields

@pytest.fixture
def crm():
    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    client.get('/login')
    with SessionLocal() as db:
        admin = db.query(User).filter_by(role='admin').first()
        uid = admin.id
    with client.session_transaction() as session: session['_user_id'] = str(uid); session['_fresh'] = True
    return client

def test_building_lift_ticket_and_snapshot(crm):
    import uuid
    addr = 'Алматы, тест ' + uuid.uuid4().hex[:8]
    res = crm.post('/api/buildings',json={'name':'Объект A','address':addr,'lat':43.24,'lon':76.92})
    assert res.status_code == 201, res.json
    bid = res.json['id']
    lift = crm.post('/api/assets',json={'address':addr,'building_id':bid,'lift_label':'Лифт 1'})
    assert lift.status_code == 201, lift.json
    tid = crm.post('/api/tickets',json={'asset_id':lift.json['id'],'problem_type':'DOORS'}).json['id']
    assert crm.get(f'/api/tickets/{tid}').json['building_id'] == bid
    summary = crm.get(f'/api/buildings/{bid}/summary').json
    assert len(summary['lifts']) == 1
    assert summary['active_tickets'][0]['id'] == tid
    assert crm.patch(f'/api/buildings/{bid}',json={'address':addr+' новый'}).status_code == 200
    assert crm.get(f'/api/tickets/{tid}').json['address'] == addr
    # Creating a building-level ticket must not invent a lift.
    res = crm.post('/api/tickets',json={'building_id':bid})
    assert res.status_code == 201, res.json
    assert crm.get(f'/api/tickets/{res.json["id"]}').json['asset_id'] is None

def test_building_migration_is_idempotent(crm, tmp_path):
    source = sqlite3.connect(config.DB_PATH)
    target = tmp_path/'migration.db'
    with sqlite3.connect(target) as dest: source.backup(dest)
    source.close()
    with sqlite3.connect(target) as db:
        db.execute("INSERT INTO assets(address,address_norm,status) VALUES ('Migration only 501', 'migration only 501', 'ACTIVE')")
    migrate_buildings(target)
    with sqlite3.connect(target) as db:
        count = db.execute('SELECT COUNT(*) FROM buildings').fetchone()[0]
        assert db.execute("SELECT building_id FROM assets WHERE address='Migration only 501'").fetchone()[0]
    migrate_buildings(target)
    with sqlite3.connect(target) as db: assert db.execute('SELECT COUNT(*) FROM buildings').fetchone()[0] == count

def test_coordinate_and_building_validation(crm):
    for lat in ['wrong',91,float('inf')]:
        assert crm.post('/api/buildings',json={'name':'A','address':'B','lat':lat,'lon':76}).status_code == 400
        assert crm.post('/api/tickets',json={'object_name':'A','lat':lat,'lon':76}).status_code == 400
    assert crm.post('/api/assets',json={'address':'A','building_id':999999}).status_code == 400

def test_closed_sla_does_not_keep_running():
    now = datetime.now(timezone.utc)
    t = Ticket(created_at=now-timedelta(days=30),cancelled_at=now-timedelta(days=30)+timedelta(minutes=2),status='CANCELLED')
    assert compute_sla_fields(t)['sla_completion_breached'] is False
