"""Estados declarativos da aula 15, aplicados somente pelo pipeline IaC."""

STAGES = ("baseline", "updated", "revoked", "deleted", "reingested")


def stage(value):
    if value not in STAGES:
        raise ValueError("UNKNOWN_LIFECYCLE_STAGE")
    return value


def revision(value):
    stage(value)
    return {"baseline": 1, "updated": 2, "revoked": 2, "deleted": 2, "reingested": 3}[value]
