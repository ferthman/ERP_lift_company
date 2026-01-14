import os
from datetime import datetime, timezone

from sqlalchemy import func

from liftcrm import config
from liftcrm.db import SessionLocal, Asset, Ticket
from liftcrm.assets.service import normalize_text, rounded_coords


def load_objects_rows(xlsx_path):
    try:
        from openpyxl import load_workbook
    except Exception as exc:
        raise RuntimeError("openpyxl is required to read objects.xlsx") from exc
    wb = load_workbook(xlsx_path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
    data_rows = []
    for row in rows[1:]:
        obj = {header[i]: row[i] for i in range(len(header))}
        data_rows.append(obj)
    return data_rows


def find_asset_by_coords(db, lat, lon):
    lat_key, lon_key = rounded_coords(lat, lon)
    if lat_key is None or lon_key is None:
        return None
    return (
        db.query(Asset)
        .filter(Asset.lat.isnot(None), Asset.lon.isnot(None))
        .filter(func.round(Asset.lat, 5) == lat_key, func.round(Asset.lon, 5) == lon_key)
        .first()
    )


def find_asset_by_address(db, address):
    normalized = normalize_text(address)
    if not normalized:
        return None
    return db.query(Asset).filter(func.lower(Asset.address) == normalized).first()


def seed_assets():
    xlsx_path = os.path.join(config.OBJECTS_DIR, "objects.xlsx")
    if not os.path.exists(xlsx_path):
        print("objects.xlsx not found, skipping seed.")
        return
    rows = load_objects_rows(xlsx_path)
    created = 0
    updated = 0
    skipped = 0
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        for row in rows:
            address = (row.get("address") or "").strip()
            try:
                lat = float(row.get("lat")) if row.get("lat") is not None else None
                lon = float(row.get("lon")) if row.get("lon") is not None else None
            except Exception:
                lat = None
                lon = None
            if not address or lat is None or lon is None:
                skipped += 1
                continue
            asset = find_asset_by_coords(db, lat, lon) or find_asset_by_address(db, address)
            if asset:
                changed = False
                if asset.lat is None:
                    asset.lat = lat
                    changed = True
                if asset.lon is None:
                    asset.lon = lon
                    changed = True
                if not asset.address:
                    asset.address = address
                    changed = True
                if asset.address and not asset.address_norm:
                    asset.address_norm = normalize_text(asset.address)
                    changed = True
                if not asset.lift_label and row.get("object_name"):
                    asset.lift_label = str(row.get("object_name")).strip()
                    changed = True
                if changed:
                    asset.updated_at = now
                    updated += 1
                else:
                    skipped += 1
                continue
            asset = Asset(
                address=address,
                address_norm=normalize_text(address),
                entrance=None,
                lift_label=str(row.get("object_name")).strip() if row.get("object_name") else None,
                serial_no=None,
                lat=lat,
                lon=lon,
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            )
            db.add(asset)
            created += 1
        db.commit()

        linked = 0
        tickets = db.query(Ticket).filter(Ticket.asset_id.is_(None)).all()
        for ticket in tickets:
            asset = find_asset_by_coords(db, ticket.lat, ticket.lon)
            if not asset and ticket.address:
                asset = find_asset_by_address(db, ticket.address)
            if asset:
                ticket.asset_id = asset.id
                linked += 1
        if linked:
            db.commit()
    print(f"Assets seed completed: created={created}, updated={updated}, skipped={skipped}, linked_tickets={linked}")


if __name__ == "__main__":
    seed_assets()
