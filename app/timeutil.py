from datetime import datetime, timezone


def utcnow() -> datetime:
    """Текущее время UTC без tzinfo (так хранится в SQLite)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
