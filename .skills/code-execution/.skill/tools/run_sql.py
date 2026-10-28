"""run_sql — execute SQL against SQLite/Postgres."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def run_sql(query: str, database_url: str = None, timeout: int = 30) -> dict:
    """
    Execute SQL.

    Args:
        query: the SQL statement
        database_url: sqlite:///path.db or postgresql://... (default: in-memory sqlite)
        timeout: seconds

    Returns:
        {"ok": bool, "rows": [...], "rowcount": int}
    """
    lowered = query.strip().lower()
    if not (lowered.startswith("select") or lowered.startswith("with")
            or lowered.startswith("pragma") or lowered.startswith("explain")):
        if database_url and database_url.startswith("postgresql"):
            raise ValueError("writes allowed only on explicit postgres target")

    if not database_url or database_url.startswith("sqlite"):
        import sqlite3
        path = ":memory:"
        if database_url and "sqlite:///" in database_url:
            path = database_url.replace("sqlite:///", "")
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            rows, rowcount = [], 0
            # executescript handles multi-statement DDL/DML; select last result
            statements = [s.strip() for s in query.split(";") if s.strip()]
            for stmt in statements:
                cur.execute(stmt)
                if cur.description:
                    rows = [dict(r) for r in cur.fetchall()]
                    rowcount = len(rows)
                else:
                    rowcount = cur.rowcount
            conn.commit()
            return {"ok": True, "rows": rows, "rowcount": rowcount,
                    "statements": len(statements), "backend": "sqlite"}
        finally:
            conn.close()

    if database_url.startswith("postgresql"):
        import asyncio as _a
        try:
            import asyncpg
        except ImportError:
            raise RuntimeError("asyncpg not installed. Run: pip install asyncpg")
        conn = await asyncpg.connect(database_url, timeout=timeout)
        try:
            rows = await conn.fetch(query)
            return {"ok": True, "rows": [dict(r) for r in rows],
                    "rowcount": len(rows), "backend": "postgres"}
        finally:
            await conn.close()

    raise ValueError(f"unsupported database_url scheme: {database_url[:20]}")
