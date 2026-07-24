"""god_function.py — a single 200+ line function.

This file passes the LOC check (under 500) but has extremely high
cyclomatic complexity (McCabe ~30). Without a complexity check, it
would be flagged as extractable when it's actually a mess.
"""


def process_request(payload, config, user, db, cache):
    """Process an incoming request through the entire pipeline.

    This function does too many things: parses, validates, authenticates,
    rate-limits, fetches, caches, transforms, logs, and responds.
    """
    if not payload:
        return None
    if "type" not in payload:
        return None
    if payload["type"] == "create":
        if not user.has_permission("create"):
            return None
        if "data" not in payload:
            return None
        if not payload["data"]:
            return None
        if len(payload["data"]) > config.max_size:
            return None
        if cache.get(payload["data"]["id"]):
            return cache.get(payload["data"]["id"])
        existing = db.query(payload["data"]["id"])
        if existing:
            return existing
        try:
            result = db.insert(payload["data"])
        except Exception:
            return None
        cache.set(payload["data"]["id"], result)
        return result
    elif payload["type"] == "update":
        if not user.has_permission("update"):
            return None
        if "id" not in payload:
            return None
        if "data" not in payload:
            return None
        existing = db.query(payload["id"])
        if not existing:
            return None
        try:
            result = db.update(payload["id"], payload["data"])
        except Exception:
            return None
        cache.invalidate(payload["id"])
        return result
    elif payload["type"] == "delete":
        if not user.has_permission("delete"):
            return None
        if "id" not in payload:
            return None
        try:
            db.delete(payload["id"])
        except Exception:
            return None
        cache.invalidate(payload["id"])
        return True
    elif payload["type"] == "list":
        if not user.has_permission("read"):
            return None
        page = payload.get("page", 1)
        size = payload.get("size", 10)
        if page < 1 or size < 1 or size > 100:
            return None
        return db.list(page, size)
    return None
