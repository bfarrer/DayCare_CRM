"""Database backup and restore.

Neon's free plan does not include managed backups, so the daycare owns them.
This writes every row to a single timestamped JSON file, which works anywhere
Python runs -- no PostgreSQL client tools needed on the machine taking the
backup, which matters on Windows.

`pg_dump` remains the authoritative tool if it is available; this exists so a
backup is always possible, and so the contents can be read without a database.
"""

import json
from datetime import date, datetime
from pathlib import Path

from .extensions import db
from .models import Child, Family, Guardian, Interaction, StageEvent, User

# Order matters on restore: parents before the rows that reference them.
TABLES = [
    ("users", User),
    ("families", Family),
    ("guardians", Guardian),
    ("children", Child),
    ("stage_events", StageEvent),
    ("interactions", Interaction),
]

FORMAT_VERSION = 1


def _serialize(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _row_to_dict(row):
    return {c.name: _serialize(getattr(row, c.name)) for c in row.__table__.columns}


def export_backup(output_dir="backups"):
    """Write every table to a timestamped JSON file. Returns (path, counts).

    Password hashes are included: without them a restore would lock every
    member of staff out. The file is therefore as sensitive as the database --
    keep it off the repository and somewhere access-controlled.
    """
    payload = {
        "format_version": FORMAT_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "tables": {},
    }
    counts = {}
    for name, model in TABLES:
        rows = [_row_to_dict(r) for r in db.session.query(model).all()]
        payload["tables"][name] = rows
        counts[name] = len(rows)

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"daycare-crm-backup-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path, counts


def _deserialize(model, column, value):
    """Turn ISO strings back into the date/datetime types the columns expect."""
    if value is None:
        return None
    python_type = getattr(model.__table__.columns[column].type, "python_type", None)
    if python_type is datetime:
        return datetime.fromisoformat(value)
    if python_type is date:
        return date.fromisoformat(value)
    return value


def import_backup(path, allow_non_empty=False):
    """Restore a backup file into the current database.

    Refuses to run against a database that already holds records unless
    explicitly allowed, so a restore cannot silently collide with live data.
    """
    existing = db.session.query(Family).count() + db.session.query(User).count()
    if existing and not allow_non_empty:
        raise RuntimeError(
            f"The database already holds {existing} users/families. "
            "Restoring would collide with them. Re-run with --force only if "
            "you intend to merge into this database."
        )

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("format_version") != FORMAT_VERSION:
        raise RuntimeError(
            f"Backup format version {payload.get('format_version')} is not "
            f"supported by this version of the app (expects {FORMAT_VERSION})."
        )

    counts = {}
    for name, model in TABLES:
        rows = payload["tables"].get(name, [])
        for row in rows:
            db.session.add(model(**{k: _deserialize(model, k, v) for k, v in row.items()}))
        counts[name] = len(rows)
    db.session.flush()

    # Restored rows carry their original ids, so the sequences that generate
    # new ids must be moved past them or the next insert collides.
    _resync_sequences()
    db.session.commit()
    return counts


def _resync_sequences():
    """Advance PostgreSQL identity sequences past the restored ids."""
    if db.engine.dialect.name != "postgresql":
        return
    from sqlalchemy import text

    for name, model in TABLES:
        db.session.execute(
            text(
                "SELECT setval(pg_get_serial_sequence(:table, 'id'), "
                "COALESCE((SELECT MAX(id) FROM " + model.__tablename__ + "), 1))"
            ),
            {"table": model.__tablename__},
        )
