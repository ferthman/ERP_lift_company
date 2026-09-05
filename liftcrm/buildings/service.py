"""Building identity and additive migration; ticket addresses remain snapshots."""
import math
import sqlite3
from datetime import datetime, timezone

from ..db import Building, Customer, Contract
from ..assets.service import normalize_text


def coordinates(lat, lon):
    values = []
    for value, bound, label in [(lat, 90, 'Широта'), (lon, 180, 'Долгота')]:
        if value in (None, ''):
            values.append(None)
            continue
        try:
            number = float(value)
        except (ValueError, TypeError):
            raise ValueError(f'{label}: укажите число')
        if not math.isfinite(number) or abs(number) > bound:
            raise ValueError(f'{label}: значение вне допустимого диапазона')
        values.append(number)
    return tuple(values)


def migrate_buildings(path):
    # One transaction: an interrupted backfill may be safely repeated.
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('''CREATE TABLE IF NOT EXISTS buildings (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, address TEXT NOT NULL,
            address_norm TEXT NOT NULL, lat REAL, lon REAL, customer_id INTEGER,
            contract_id INTEGER, contact_person TEXT, phone TEXT, email TEXT, notes TEXT,
            is_active INTEGER DEFAULT 1, created_at DATETIME, updated_at DATETIME)''')
        for table in ('assets', 'tickets'):
            cols = {r['name'] for r in conn.execute(f'PRAGMA table_info({table})')}
            if 'building_id' not in cols:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN building_id INTEGER REFERENCES buildings(id)')
            conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{table}_building_id ON {table}(building_id)')
        for column in ('address_norm', 'customer_id', 'contract_id'):
            conn.execute(f'CREATE INDEX IF NOT EXISTS idx_buildings_{column} ON buildings({column})')
        def identity(address, name, lat, lon, customer=None, contract=None):
            norm = normalize_text(address)
            if not norm:
                return None
            found = conn.execute('SELECT id FROM buildings WHERE address_norm=? AND customer_id IS ? AND contract_id IS ? ORDER BY id LIMIT 1', (norm, customer, contract)).fetchone()
            if found:
                return found['id']
            now = datetime.now(timezone.utc).isoformat()
            return conn.execute('INSERT INTO buildings(name,address,address_norm,lat,lon,customer_id,contract_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)', (name or address,address,norm,lat,lon,customer,contract,now,now)).lastrowid
        for a in conn.execute('SELECT * FROM assets WHERE building_id IS NULL ORDER BY id').fetchall():
            bid = identity(a['address'], a['address'], a['lat'], a['lon'], a['customer_id'], a['contract_id'])
            conn.execute('UPDATE assets SET building_id=? WHERE id=?', (bid, a['id']))
        conn.execute('UPDATE tickets SET building_id=(SELECT building_id FROM assets WHERE assets.id=tickets.asset_id) WHERE building_id IS NULL AND asset_id IS NOT NULL')
        for t in conn.execute('SELECT * FROM tickets WHERE building_id IS NULL AND asset_id IS NULL').fetchall():
            bid = identity(t['address'],t['object_name'],t['lat'],t['lon'])
            conn.execute('UPDATE tickets SET building_id=? WHERE id=?',(bid,t['id']))
        conn.execute('CREATE INDEX IF NOT EXISTS idx_ticket_comments_ticket ON ticket_comments(ticket_id)')
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='attachments'").fetchone():
            conn.execute('CREATE INDEX IF NOT EXISTS idx_attachments_ticket ON attachments(ticket_id)')


def ensure_building(db, address, lat=None, lon=None, customer_id=None, contract_id=None, name=None):
    norm = normalize_text(address)
    if not norm:
        raise ValueError('Укажите адрес объекта')
    building = db.query(Building).filter_by(address_norm=norm, customer_id=customer_id, contract_id=contract_id).order_by(Building.id).first()
    if not building:
        building = Building(name=name or address, address=address, address_norm=norm, lat=lat, lon=lon, customer_id=customer_id, contract_id=contract_id)
        db.add(building)
        db.flush()
    return building


def link_asset(db, asset, building_id=None, regroup=False):
    if building_id not in (None, ''):
        try:
            building = db.get(Building, int(building_id))
        except (ValueError, TypeError):
            raise ValueError('Некорректный объект')
        if not building or not building.is_active:
            raise ValueError('Объект не найден или отключён')
        asset.address, asset.address_norm = building.address, building.address_norm
        asset.customer_id, asset.contract_id = building.customer_id, building.contract_id
        if asset.lat is None: asset.lat = building.lat
        if asset.lon is None: asset.lon = building.lon
    elif asset.building_id and not regroup:
        return asset.building
    else:
        building = ensure_building(db, asset.address, asset.lat, asset.lon, asset.customer_id, asset.contract_id)
    asset.building_id = building.id
    asset.building = building
    return building


def serialize_building(b):
    return {**{field:getattr(b,field) for field in ('id','name','address','lat','lon','customer_id','contract_id','contact_person','phone','email','notes','is_active')},
        'customer_name': b.customer.name if b.customer else None,
        'contract_number': b.contract.contract_number if b.contract else None,
        'contract_title': b.contract.title if b.contract else None,
        'lift_count': len(b.assets),
        'active_ticket_count': sum(t.archived_at is None and t.status not in ('COMPLETED','CANCELLED') for t in b.tickets)}


def building_values(db, data, existing=None):
    def val(key, default=None): return data.get(key, getattr(existing,key,default))
    values = {k: str(val(k) or '').strip() or None for k in ('name','address','contact_person','phone','email','notes')}
    if not values['name'] or not values['address']:
        raise ValueError('Укажите название и адрес объекта')
    values['address_norm'] = normalize_text(values['address'])
    values['lat'], values['lon'] = coordinates(val('lat'),val('lon'))
    for key, model in [('customer_id',Customer),('contract_id',Contract)]:
        raw = val(key)
        try: parsed = int(raw) if raw not in (None,'') else None
        except (ValueError,TypeError): raise ValueError('Некорректный клиент или договор')
        if parsed and not db.get(model,parsed): raise ValueError('Клиент или договор не найден')
        values[key] = parsed
    if values['contract_id']:
        contract = db.get(Contract,values['contract_id'])
        if values['customer_id'] and contract.customer_id != values['customer_id']:
            raise ValueError('Договор принадлежит другому клиенту')
        values['customer_id'] = contract.customer_id
    raw_active = val('is_active',1)
    if raw_active not in (0,1,False,True): raise ValueError('Некорректное состояние объекта')
    values['is_active'] = int(raw_active)
    return values
