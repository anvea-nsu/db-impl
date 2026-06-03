"""
Admin router — generic raw-table CRUD + user management.
All endpoints protected by require_admin.
"""
import logging
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text, func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import require_admin, hash_password
from app.models import AppUser
from app.schemas import UserOut

log = logging.getLogger("pubapp.admin")
router = APIRouter(prefix="/api/admin", tags=["admin"])

# ── Whitelisted tables ────────────────────────────────────────────────────────
ALLOWED_TABLES: dict[str, str] = {
    "languages":             "lang_id",
    "countries":             "country_id",
    "cities":                "city_id",
    "databases":             "db_id",
    "organizations":         "org_id",
    "organization_names":    "id",
    "organizations_databases": "id",
    "journals":              "journal_id",
    "journal_titles":        "title_id",
    "journals_databases":    "id",
    "journal_database_ids":  "id",
    "issues":                "issue_id",
    "articles":              "article_id",
    "article_titles":        "title_id",
    "articles_databases":    "id",
    "authors":               "author_id",
    "author_names":          "id",
    "articles_authors":      "id",
    "author_affiliations":   "id",
    "authors_databases":     "id",
    "app_users":             "id",
}

# Columns to hide from the UI (sensitive data)
HIDDEN_COLUMNS: dict[str, set[str]] = {
    "app_users": {"hashed_password"},
}

# Auto-generated (SERIAL) columns — excluded from INSERT form
SERIAL_COLUMNS: dict[str, set[str]] = {
    "cities":                    {"city_id"},
    "databases":                 {"db_id"},
    "organizations":             {"org_id"},
    "organization_names":        {"id"},
    "organizations_databases":   {"id"},
    "journals":                  {"journal_id"},
    "journal_titles":            {"title_id"},
    "journals_databases":        {"id"},
    "journal_database_ids":      {"id"},
    "issues":                    {"issue_id"},
    "articles":                  {"article_id"},
    "article_titles":            {"title_id"},
    "articles_databases":        {"id"},
    "authors":                   {"author_id"},
    "author_names":              {"id"},
    "articles_authors":          {"id"},
    "author_affiliations":       {"id"},
    "authors_databases":         {"id"},
    "app_users":                 {"id"},
}


def _check_table(name: str) -> str:
    if name not in ALLOWED_TABLES:
        raise HTTPException(404, f"Таблица '{name}' не найдена")
    return ALLOWED_TABLES[name]


def _serialize(val: Any) -> Any:
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return val


# ── Table list ────────────────────────────────────────────────────────────────

@router.get("/tables")
async def list_tables(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Return all tables with row counts and PK info."""
    result = []
    for tbl, pk in ALLOWED_TABLES.items():
        try:
            cnt = (await db.execute(text(f'SELECT COUNT(*) FROM "{tbl}"'))).scalar()
        except Exception:
            cnt = 0
        result.append({"table": tbl, "pk": pk, "count": cnt})
    return result


# ── Schema (column definitions) ───────────────────────────────────────────────

@router.get("/schema/{table_name}")
async def table_schema(
    table_name: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Return column names, types, nullable flags for a table."""
    _check_table(table_name)
    hidden = HIDDEN_COLUMNS.get(table_name, set())
    serial = SERIAL_COLUMNS.get(table_name, set())

    rows = (await db.execute(text("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :t
        ORDER BY ordinal_position
    """), {"t": table_name})).fetchall()

    columns = []
    for col_name, data_type, nullable, default in rows:
        if col_name in hidden:
            continue
        columns.append({
            "name":      col_name,
            "type":      data_type,
            "nullable":  nullable == "YES",
            "serial":    col_name in serial,
            "pk":        col_name == ALLOWED_TABLES[table_name],
        })
    return columns


# ── Row list (paginated + optional search) ────────────────────────────────────

@router.get("/raw/{table_name}")
async def raw_list(
    table_name: str,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    _check_table(table_name)
    hidden = HIDDEN_COLUMNS.get(table_name, set())

    # Build column list excluding hidden
    schema_rows = (await db.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :t
        ORDER BY ordinal_position
    """), {"t": table_name})).fetchall()
    all_cols = [r[0] for r in schema_rows]
    visible_cols = [c for c in all_cols if c not in hidden]
    col_sql = ", ".join(f'"{c}"' for c in visible_cols)

    # Optional full-text search across all text columns
    where = ""
    params: dict = {"lim": limit, "off": skip}
    if search:
        text_cols = (await db.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:t
              AND data_type IN ('character varying','text','char','character')
            ORDER BY ordinal_position
        """), {"t": table_name})).fetchall()
        if text_cols:
            conds = " OR ".join(
                f'"{r[0]}"::text ILIKE :q' for r in text_cols
            )
            where = f"WHERE {conds}"
            params["q"] = f"%{search}%"

    pk = ALLOWED_TABLES[table_name]
    order = f'ORDER BY "{pk}"'

    total = (await db.execute(
        text(f'SELECT COUNT(*) FROM "{table_name}" {where}'), params
    )).scalar()

    rows = (await db.execute(
        text(f'SELECT {col_sql} FROM "{table_name}" {where} {order} LIMIT :lim OFFSET :off'),
        params,
    )).fetchall()

    return {
        "total": total,
        "columns": visible_cols,
        "rows": [{c: _serialize(v) for c, v in zip(visible_cols, r)} for r in rows],
    }


# ── Insert ────────────────────────────────────────────────────────────────────

@router.post("/raw/{table_name}", status_code=201)
async def raw_insert(
    table_name: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    _check_table(table_name)
    serial = SERIAL_COLUMNS.get(table_name, set())
    # Strip serial/PK fields and None values (let DB default handle them)
    payload = {k: v for k, v in data.items() if k not in serial and v is not None and v != ""}

    if table_name == "app_users" and "password" in payload:
        payload["hashed_password"] = hash_password(payload.pop("password"))

    if not payload:
        raise HTTPException(400, "Нет данных для вставки")

    cols = ", ".join(f'"{k}"' for k in payload)
    placeholders = ", ".join(f":{k}" for k in payload)
    pk = ALLOWED_TABLES[table_name]

    try:
        result = await db.execute(
            text(f'INSERT INTO "{table_name}" ({cols}) VALUES ({placeholders}) RETURNING "{pk}"'),
            payload,
        )
        new_id = result.scalar()
        await db.commit()
        return {"ok": True, "id": new_id}
    except Exception as e:
        await db.rollback()
        log.error(f"INSERT {table_name}: {e}")
        raise HTTPException(400, str(e))


# ── Update ────────────────────────────────────────────────────────────────────

@router.put("/raw/{table_name}/{pk_value}")
async def raw_update(
    table_name: str,
    pk_value: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    pk = _check_table(table_name)
    hidden = HIDDEN_COLUMNS.get(table_name, set())
    serial = SERIAL_COLUMNS.get(table_name, set())
    excluded = hidden | serial | {pk}
    payload = {k: (None if v == "" else v) for k, v in data.items() if k not in excluded}

    if table_name == "app_users" and "password" in payload:
        payload["hashed_password"] = hash_password(payload.pop("password"))
        payload = {k: v for k, v in payload.items() if k not in hidden}

    if not payload:
        raise HTTPException(400, "Нет изменяемых полей")

    set_clause = ", ".join(f'"{k}" = :{k}' for k in payload)
    payload["__pk__"] = pk_value
    try:
        await db.execute(
            text(f'UPDATE "{table_name}" SET {set_clause} WHERE "{pk}" = :__pk__'),
            payload,
        )
        await db.commit()
        return {"ok": True}
    except Exception as e:
        await db.rollback()
        log.error(f"UPDATE {table_name}/{pk_value}: {e}")
        raise HTTPException(400, str(e))


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/raw/{table_name}/{pk_value}")
async def raw_delete(
    table_name: str,
    pk_value: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    pk = _check_table(table_name)
    try:
        await db.execute(
            text(f'DELETE FROM "{table_name}" WHERE "{pk}" = :v'),
            {"v": pk_value},
        )
        await db.commit()
        return {"ok": True}
    except Exception as e:
        await db.rollback()
        log.error(f"DELETE {table_name}/{pk_value}: {e}")
        raise HTTPException(400, str(e))


# ── Users shortcut ────────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    skip: int = 0, limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    total = (await db.execute(select(func.count(AppUser.id)))).scalar()
    users = (await db.execute(select(AppUser).offset(skip).limit(limit))).scalars().all()
    return {"total": total, "items": [UserOut.model_validate(u) for u in users]}
