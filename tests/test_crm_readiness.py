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

def test_reports_counts_period_search_and_access(crm):
    import uuid
    marker='Сводка '+uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        b=Building(name=marker,address=marker,address_norm=marker.lower())
        db.add(b);db.flush()
        a=Asset(address=marker,building_id=b.id,lift_label=marker)
        m=Master(name=marker,is_active=1)
        db.add_all([a,m]);db.flush()
        u=User(username='tech_'+uuid.uuid4().hex,password_hash='unused',role='technician',master_id=m.id,is_active=1)
        db.add(u);db.flush()
        now=datetime.now(timezone.utc)
        for status in ['ASSIGNED','COMPLETED','CANCELLED']:
            db.add(Ticket(object_name=marker,address=marker,lat=43.2,lon=76.9,asset_id=a.id,building_id=b.id,assigned_master_id=m.id,status=status,problem_type='DOORS',priority='HIGH',created_at=now-timedelta(hours=2),updated_at=now-timedelta(hours=2),completed_at=now-timedelta(hours=1) if status=='COMPLETED' else None))
        db.commit();bid,aid,mid,uid=b.id,a.id,m.id,u.id
    report=crm.get(f'/api/reports/overview?building_id={bid}').json
    assert report['overall']['total']==3
    assert report['overall']['active']==1
    assert report['overall']['completed']==1
    assert report['overall']['cancelled']==1
    assert report['lifts'][0]['total']==2
    assert next(m for m in report['masters'] if m['id']==mid)['avg_completion_sec']==3600
    assert report['problem_types'][0]['type']=='DOORS'
    assert report['sla'][0]['attention_reasons']
    assert crm.get('/api/reports/overview?date_from=bad').status_code==400
    assert crm.get('/api/reports/overview?date_from=2026-12-31&date_to=2026-01-01').status_code==400
    assert crm.get(f'/api/lifts/{aid}/summary').json['signal']['flagged']
    found=crm.get('/api/search',query_string={'q':marker}).json['items']
    assert {'ticket','lift','building','master'} <= {i['type'] for i in found}
    assert crm.get('/api/dashboard').status_code==200
    with crm.session_transaction() as s: s['_user_id']=str(uid)
    for path in ['/api/buildings','/api/dashboard','/api/reports/overview',f'/api/lifts/{aid}/summary']:
        assert crm.get(path).status_code==403
    assert crm.get(f'/api/me/lifts/{aid}/history').status_code==200
    assert crm.get('/api/me/lifts/999999/history').status_code==403
    found=crm.get('/api/search',query_string={'q':marker}).json['items']
    assert {i['type'] for i in found} <= {'ticket','lift'}
    assert all(i['url'].startswith('/mobile?ticket=') for i in found)
    with crm.session_transaction() as s:s.clear()
    assert crm.get('/api/dashboard').status_code==401

def test_public_offline_shell_and_cross_identity_guard(crm):
    with crm.session_transaction() as session: owner=session['_user_id']
    shell=crm.get('/mobile-shell')
    assert shell.status_code==200
    assert 'userId: null' in shell.text
    assert 'offlineShell: true' in shell.text
    assert 'username: ""' in shell.text
    worker=crm.get('/sw.js')
    assert worker.status_code==200
    assert worker.headers['Service-Worker-Allowed']=='/'
    assert worker.headers['Cache-Control']=='no-cache'
    assert crm.get('/api/dashboard',headers={'X-Mobile-User':owner}).status_code==200
    assert crm.get('/api/dashboard',headers={'X-Mobile-User':'999999'}).status_code==409
    assert crm.post('/api/tickets',headers={'X-Mobile-User':'999999'},json={'object_name':'Denied','lat':43.2,'lon':76.9}).status_code==409
    with crm.session_transaction() as session: session.clear()
    assert crm.get('/mobile-shell').status_code==200
    assert crm.get('/api/me',headers={'X-Mobile-User':owner}).status_code==401

def test_upload_names_do_not_collide_and_retry_is_idempotent(crm):
    import io,uuid
    tid=crm.post('/api/tickets',json={'object_name':'Фото проверка','lat':43.2,'lon':76.9}).json['id']
    key=str(uuid.uuid4())
    def upload(body, upload_id=None):
        data={'file':(io.BytesIO(body),'photo.png')}
        if upload_id: data['upload_id']=upload_id
        return crm.post(f'/api/tickets/{tid}/upload',data=data,content_type='multipart/form-data')
    first=upload(b'photo-one',key)
    assert first.status_code==200
    retry=upload(b'photo-one',key)
    assert retry.json['url']==first.json['url']
    second=upload(b'photo-two')
    assert second.json['url']!=first.json['url']
    assert crm.get(first.json['url']).data==b'photo-one'
    assert crm.get(second.json['url']).data==b'photo-two'
    assert len(crm.get(f'/api/tickets/{tid}').json['attachments'])==2


def test_ticket_search_handles_cyrillic_id_and_literal_wildcards(crm):
    import uuid
    name='Проверка Кириллицы '+uuid.uuid4().hex[:8]
    tid=crm.post('/api/tickets',json={'object_name':name,'description':'код 70%_Х','lat':43.2,'lon':76.9}).json['id']
    assert tid in [row['id'] for row in crm.get('/api/tickets',query_string={'q':name.swapcase()}).json]
    assert [row['id'] for row in crm.get('/api/tickets',query_string={'q':f'#{tid}'}).json]==[tid]
    assert tid in [row['id'] for row in crm.get('/api/tickets',query_string={'q':'70%_х'}).json]
    assert tid not in [row['id'] for row in crm.get('/api/tickets',query_string={'q':'70%_другое'}).json]
    assert crm.get('/api/tickets?date_from=2026-12-31&date_to=2026-01-01').status_code==400
