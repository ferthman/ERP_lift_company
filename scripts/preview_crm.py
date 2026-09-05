"""Isolated synthetic preview. Never opens the real CRM database."""
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from liftcrm import config, create_app
preview_dir=Path(tempfile.mkdtemp(prefix='lift-crm-preview-'))
config.DB_PATH=str(preview_dir/'preview.db')
config.ARCHIVE_PATH=str(preview_dir/'archive.xlsx')
config.UPLOAD_FOLDER=str(preview_dir/'uploads')
from liftcrm.db import init_db, ensure_migrations, SessionLocal, Master, Asset, Ticket, Customer
from liftcrm.buildings.service import ensure_building
init_db();ensure_migrations()
with SessionLocal() as db:
    names=['Алексей Смирнов','Данияр Касымов','Сергей Волков','Руслан Ахметов','Андрей Петров']
    masters=db.query(Master).order_by(Master.id).all()
    for m,name in zip(masters,names):m.name=name
    c=Customer(name='Демо · Управляющая компания',contact_person='Демонстрационный контакт');db.add(c);db.flush()
    buildings=[('ЖК Центральный','Алматы, ул. Кабанбай батыра, 152'),('Бизнес-центр «Алатау»','Алматы, пр. Достык, 105'),('ЖК Солнечный','Алматы, ул. Розыбакиева, 247'),('ТЦ «Город»','Алматы, пр. Абая, 109')]
    assets=[]
    for i,(name,addr) in enumerate(buildings):
        b=ensure_building(db,addr,43.24,76.92,customer_id=c.id,name=name)
        a=Asset(address=addr,lift_label='Пассажирский лифт',serial_no=f'DEMO-{i+1:03}',entrance='1',lat=43.24,lon=76.92,building_id=b.id,customer_id=c.id,status='ACTIVE');db.add(a);db.flush();assets.append(a)
    now=datetime.now(timezone.utc)
    for i in range(24):
        a=assets[i%4];age=(i%7)*24+ (i%3)
        created=now-timedelta(hours=age)
        status=['ASSIGNED','IN_PROGRESS','WAITING','COMPLETED','COMPLETED','ACCEPTED'][i%6]
        if i==0:status='ASSIGNED'
        t=Ticket(object_name=buildings[i%4][0],address=a.address,asset_id=a.id,building_id=a.building_id,lat=43.24,lon=76.92,description=['Не закрываются двери кабины','Шум при движении между этажами','Не работает кнопка вызова','Лифт остановился на третьем этаже'][i%4],problem_type=['DOORS','NOISE','BUTTONS','STOPPED'][i%4],priority='EMERGENCY' if i==0 else 'HIGH' if i%7==0 else 'MEDIUM',status=status,assigned_master_id=masters[i%5].id,created_at=created,updated_at=created,assigned_at=created,completed_at=created+timedelta(minutes=45) if status=='COMPLETED' else None)
        db.add(t)
    db.commit()
print(f'Isolated preview directory: {preview_dir}',flush=True)
app=create_app()
app.run(host='127.0.0.1',port=5055,debug=False)
