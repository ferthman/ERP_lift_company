ROLE_ADMIN = "admin"
ROLE_DISPATCHER = "dispatcher"
ROLE_TECHNICIAN = "technician"
ROLE_MANAGER = "manager"

ALLOWED_ROLES = {ROLE_ADMIN, ROLE_DISPATCHER, ROLE_TECHNICIAN, ROLE_MANAGER}

LEGACY_ROLE_MAP = {
    "master": ROLE_TECHNICIAN,
}


def normalize_role(role):
    if role is None:
        return ""
    role_value = str(role).strip().lower()
    return LEGACY_ROLE_MAP.get(role_value, role_value)


def validate_role_master_id(role, master_id):
    if role not in ALLOWED_ROLES:
        return "Invalid role"
    if role == ROLE_TECHNICIAN and master_id is None:
        return "master_id is required for technician"
    if role != ROLE_TECHNICIAN and master_id is not None:
        return "master_id must be null for non-technician users"
    return None
