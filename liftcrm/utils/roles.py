ROLE_ADMIN = "admin"
ROLE_DISPATCHER = "dispatcher"
ROLE_TECHNICIAN = "technician"

ALLOWED_ROLES = {ROLE_ADMIN, ROLE_DISPATCHER, ROLE_TECHNICIAN}


def normalize_role(value):
    if value is None:
        return None
    role = str(value).strip().lower()
    if role == "master":
        return ROLE_TECHNICIAN
    return role


def is_technician(role):
    return normalize_role(role) == ROLE_TECHNICIAN
