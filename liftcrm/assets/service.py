from datetime import timezone

def normalize_status(value: str) -> str:
    if value is None:
        return "ACTIVE"
    return str(value).strip().upper()


def asset_display_label(asset) -> str:
    parts = [part for part in [asset.serial_no, asset.lift_label, asset.entrance] if part]
    if parts:
        return " / ".join(parts)
    if asset.address:
        return asset.address
    return f"Asset #{asset.id}"


def build_asset_summary(asset):
    if not asset:
        return None
    return {
        "id": asset.id,
        "serial_no": asset.serial_no,
        "lift_label": asset.lift_label,
        "entrance": asset.entrance,
        "address": asset.address,
        "lat": asset.lat,
        "lon": asset.lon,
        "status": asset.status,
    }


def serialize_asset(asset):
    return {
        "id": asset.id,
        "address": asset.address,
        "entrance": asset.entrance,
        "lift_label": asset.lift_label,
        "serial_no": asset.serial_no,
        "customer_id": asset.customer_id,
        "lat": asset.lat,
        "lon": asset.lon,
        "status": asset.status,
        "created_at": asset.created_at.replace(tzinfo=timezone.utc).isoformat() if asset.created_at else None,
        "updated_at": asset.updated_at.replace(tzinfo=timezone.utc).isoformat() if asset.updated_at else None,
    }
