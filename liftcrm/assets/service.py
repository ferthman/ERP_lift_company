from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import func

from ..db import Asset


def normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    text = str(value).lower()
    for ch in ".,;:()[]'\"-":
        text = text.replace(ch, " ")
    return " ".join(text.split())


def rounded_coords(lat: Optional[float], lon: Optional[float]) -> Tuple[Optional[float], Optional[float]]:
    try:
        lat_val = round(float(lat), 5) if lat is not None else None
        lon_val = round(float(lon), 5) if lon is not None else None
    except Exception:
        return None, None
    return lat_val, lon_val


def find_asset_by_coords(db, lat: Optional[float], lon: Optional[float]) -> Optional[Asset]:
    lat_key, lon_key = rounded_coords(lat, lon)
    if lat_key is None or lon_key is None:
        return None
    return (
        db.query(Asset)
        .filter(Asset.lat.isnot(None), Asset.lon.isnot(None))
        .filter(func.round(Asset.lat, 5) == lat_key, func.round(Asset.lon, 5) == lon_key)
        .first()
    )


def find_asset_by_address(db, address: Optional[str]) -> Optional[Asset]:
    normalized = normalize_text(address)
    if not normalized:
        return None
    return db.query(Asset).filter(Asset.address_norm == normalized).first()


def upsert_asset_from_ticket(db, object_name, address, lat, lon) -> Optional[Asset]:
    if not address:
        return None
    lat_key, lon_key = rounded_coords(lat, lon)
    asset = None
    if lat_key is not None and lon_key is not None:
        asset = find_asset_by_coords(db, lat, lon)
    if not asset:
        asset = find_asset_by_address(db, address)
    if asset:
        updated = False
        if asset.lat is None and lat_key is not None:
            asset.lat = float(lat)
            updated = True
        if asset.lon is None and lon_key is not None:
            asset.lon = float(lon)
            updated = True
        if not asset.address and address:
            asset.address = address
            updated = True
        if not asset.lift_label and object_name:
            asset.lift_label = object_name
            updated = True
        if asset.address and not asset.address_norm:
            asset.address_norm = normalize_text(asset.address)
            updated = True
        if updated:
            asset.updated_at = datetime.now(timezone.utc)
        return asset
    asset = Asset(
        address=address,
        address_norm=normalize_text(address),
        entrance=None,
        lift_label=(object_name or None),
        serial_no=None,
        lat=float(lat) if lat_key is not None else None,
        lon=float(lon) if lon_key is not None else None,
        status="ACTIVE",
    )
    db.add(asset)
    db.flush()
    return asset
