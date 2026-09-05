"""Postgres admin router.

Exposes table metadata and basic CRUD for any table in the database.
Intended for development and debugging -- not for production traffic.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import inspect, text

from app.api.deps import DbSession
from app.db.session import get_engine

router = APIRouter(prefix="/admin/postgres", tags=["admin-postgres"])


class RowPayload(BaseModel):
    """Generic key-value row for inserts and updates."""
    data: dict[str, Any]


# ------------------------------------------------------------------ schema
@router.get("/tables")
async def list_tables(session: DbSession) -> dict:
    """List all user tables with row counts."""
    result = await session.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
    ))
    tables = [row[0] for row in result.fetchall()]

    counts: dict[str, int] = {}
    for t in tables:
        count_row = await session.execute(text(f'SELECT count(*) FROM "{t}"'))  # noqa: S608
        counts[t] = count_row.scalar_one()

    return {"tables": tables, "row_counts": counts, "total_tables": len(tables)}


@router.get("/tables/{table}/columns")
async def table_columns(table: str, session: DbSession) -> dict:
    """Column names, types, and nullable info for a table."""
    result = await session.execute(text(
        "SELECT column_name, data_type, is_nullable, column_default "
        "FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :table "
        "ORDER BY ordinal_position"
    ), {"table": table})
    rows = result.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"Table '{table}' not found")
    return {
        "table": table,
        "columns": [
            {"name": r[0], "type": r[1], "nullable": r[2] == "YES", "default": r[3]}
            for r in rows
        ],
    }


@router.get("/tables/{table}/indexes")
async def table_indexes(table: str, session: DbSession) -> dict:
    """List indexes on a table."""
    result = await session.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes "
        "WHERE schemaname = 'public' AND tablename = :table "
        "ORDER BY indexname"
    ), {"table": table})
    return {
        "table": table,
        "indexes": [{"name": r[0], "definition": r[1]} for r in result.fetchall()],
    }


# ------------------------------------------------------------------ read
@router.get("/tables/{table}/rows")
async def list_rows(
    table: str,
    session: DbSession,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    order_by: str = Query("created_at", description="Column to sort by"),
    order: str = Query("desc", regex="^(asc|desc)$"),
) -> dict:
    """Paginated rows from any table."""
    # Validate table exists
    check = await session.execute(text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = :table"
    ), {"table": table})
    if not check.fetchone():
        raise HTTPException(status_code=404, detail=f"Table '{table}' not found")

    # Validate order_by column exists
    col_check = await session.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :table AND column_name = :col"
    ), {"table": table, "col": order_by})
    if not col_check.fetchone():
        order_by = "ctid"  # fallback to physical row order

    count_result = await session.execute(text(f'SELECT count(*) FROM "{table}"'))  # noqa: S608
    total = count_result.scalar_one()

    result = await session.execute(text(
        f'SELECT * FROM "{table}" ORDER BY "{order_by}" {order} LIMIT :limit OFFSET :offset'  # noqa: S608
    ), {"limit": limit, "offset": offset})

    columns = list(result.keys())
    rows = [dict(zip(columns, [_serialize(v) for v in row])) for row in result.fetchall()]

    return {"table": table, "rows": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/tables/{table}/rows/{row_id}")
async def get_row(table: str, row_id: str, session: DbSession) -> dict:
    """Get a single row by its id column."""
    result = await session.execute(
        text(f'SELECT * FROM "{table}" WHERE id = :id'),  # noqa: S608
        {"id": row_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Row not found")
    columns = list(result.keys())
    return {"table": table, "row": dict(zip(columns, [_serialize(v) for v in row]))}


# ------------------------------------------------------------------ write
@router.post("/tables/{table}/rows", status_code=status.HTTP_201_CREATED)
async def insert_row(table: str, body: RowPayload, session: DbSession) -> dict:
    """Insert a row from arbitrary key-value pairs."""
    cols = ", ".join(f'"{k}"' for k in body.data)
    placeholders = ", ".join(f":{k}" for k in body.data)
    result = await session.execute(
        text(f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders}) RETURNING *'),  # noqa: S608
        body.data,
    )
    row = result.fetchone()
    columns = list(result.keys())
    return {"table": table, "row": dict(zip(columns, [_serialize(v) for v in row]))}


@router.put("/tables/{table}/rows/{row_id}")
async def update_row(table: str, row_id: str, body: RowPayload, session: DbSession) -> dict:
    """Update a row by id."""
    sets = ", ".join(f'"{k}" = :{k}' for k in body.data)
    params = {**body.data, "id": row_id}
    result = await session.execute(
        text(f'UPDATE "{table}" SET {sets} WHERE id = :id RETURNING *'),  # noqa: S608
        params,
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Row not found")
    columns = list(result.keys())
    return {"table": table, "row": dict(zip(columns, [_serialize(v) for v in row]))}


@router.delete("/tables/{table}/rows/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_row(table: str, row_id: str, session: DbSession) -> None:
    """Delete a row by id."""
    result = await session.execute(
        text(f'DELETE FROM "{table}" WHERE id = :id'),  # noqa: S608
        {"id": row_id},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Row not found")


# ------------------------------------------------------------------ raw SQL
@router.post("/query")
async def raw_query(
    session: DbSession,
    sql: str = Query(..., description="Read-only SQL query"),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    """Execute a read-only SQL query. Only SELECT statements allowed."""
    stripped = sql.strip().rstrip(";").upper()
    if not stripped.startswith("SELECT") and not stripped.startswith("WITH") and not stripped.startswith("EXPLAIN"):
        raise HTTPException(status_code=400, detail="Only SELECT / WITH / EXPLAIN queries allowed")

    result = await session.execute(text(sql))
    columns = list(result.keys())
    rows = [dict(zip(columns, [_serialize(v) for v in row])) for row in result.fetchmany(limit)]
    return {"columns": columns, "rows": rows, "count": len(rows)}


# ------------------------------------------------------------------ pool stats
@router.get("/pool")
async def pool_stats() -> dict:
    """SQLAlchemy connection pool statistics."""
    engine = get_engine()
    pool = engine.pool
    return {
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "total_connections": pool.checkedin() + pool.checkedout(),
        "dsn": str(engine.url).replace(str(engine.url.password or ""), "***"),
    }


# ------------------------------------------------------------------ migrations
@router.get("/migrations")
async def migration_status(session: DbSession) -> dict:
    """Current Alembic migration version."""
    try:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
        versions = [row[0] for row in result.fetchall()]
        return {"current_versions": versions}
    except Exception as exc:
        return {"error": str(exc)[:200]}


def _serialize(v: Any) -> Any:
    """Make values JSON-friendly."""
    import uuid
    from datetime import date, datetime

    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, bytes):
        return v.hex()
    if isinstance(v, set):
        return list(v)
    return v
