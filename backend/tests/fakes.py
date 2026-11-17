"""Fake DB yang merekam tulis untuk menguji layanan tanpa Supabase nyata."""
from __future__ import annotations

from app.db import SupabaseError


class RecordingDB:
    """Pengganti SupabaseClient: mengembalikan data uji dan merekam insert/update."""

    def __init__(self, *, sources=None, keywords=None, tables=None):
        self.sources = sources or []
        self.keywords = keywords or []
        self.tables = tables or {}
        self.inserted: list[dict] = []
        self.updates: list[dict] = []
        self._seq = 0

    def select(self, table, params=None):
        if table == "tender_keywords":
            return [{"keyword": k} for k in self.keywords]
        if table == "tender_sources":
            return self.sources
        return list(self.tables.get(table, []))

    def insert(self, table, rows, *, upsert=False, on_conflict=None, returning=True):
        payload = rows if isinstance(rows, list) else [rows]
        self.inserted.append({"table": table, "rows": payload, "upsert": upsert, "on_conflict": on_conflict})
        if returning:
            # Tiru PostgREST: kembalikan baris dengan `id` yang dihasilkan.
            out = []
            for r in payload:
                self._seq += 1
                out.append({**r, "id": r.get("id") or f"{table}-{self._seq}"})
            return out
        return []

    def update(self, table, filters, values, *, returning=True):
        self.updates.append({"table": table, "filters": filters, "values": values})
        return []

    def count(self, table, filters=None, select="id"):
        return 0

    # helper uji
    def inserted_in(self, table):
        return [i for i in self.inserted if i["table"] == table]

    def updates_in(self, table):
        return [u for u in self.updates if u["table"] == table]


class AutomationDB:
    """Fake DB lebih lengkap untuk Fase 4: filter PostgREST, conflict unik, update.

    Meniru perilaku yang dipakai runner/scheduler:
    * filter `eq.`, `in.(...)`, `is.null`, `order`, `limit`, `offset`.
    * konflik unik: satu job aktif per config, `idempotency_key`, `dedupe_key`,
      `automation_type` (memunculkan SupabaseError 409 seperti PostgREST).
    """

    def __init__(self, tables: dict | None = None):
        self.data = {k: [dict(r) for r in v] for k, v in (tables or {}).items()}
        self.inserted: list[dict] = []
        self.updates: list[dict] = []
        self._seq = 0

    # --- baca ---

    def _match(self, row: dict, filters: dict) -> bool:
        for key, raw in (filters or {}).items():
            if key == "or":
                if not any(self._match_one(row, e) for e in self._split_expr(raw)):
                    return False
                continue
            if key == "and":
                if not all(self._match_one(row, e) for e in self._split_expr(raw)):
                    return False
                continue
            if key in ("select", "order", "limit", "offset"):
                continue
            if not self._match_one(row, f"{key}.{raw}"):
                return False
        return True

    @staticmethod
    def _split_expr(raw) -> list[str]:
        text = str(raw).strip()
        if text.startswith("(") and text.endswith(")"):
            text = text[1:-1]
        return [p for p in text.split(",") if p]

    def _match_one(self, row: dict, expr: str) -> bool:
        col, _, rest = expr.partition(".")
        actual = row.get(col)
        if rest.startswith("is."):
            val = rest[3:]
            if val == "null":
                return actual is None
            return str(actual).lower() == val.lower()
        op, _, val = rest.partition(".")
        if isinstance(actual, bool):
            actual = "true" if actual else "false"
        if op == "eq":
            return str(actual) == val
        if op == "in":
            return str(actual) in val.strip("()").split(",")
        if op == "gte":
            return actual is not None and str(actual) >= val
        if op == "lte":
            return actual is not None and str(actual) <= val
        if op == "lt":
            return actual is not None and str(actual) < val
        return True


    def select(self, table, params=None):
        rows = [r for r in self.data.get(table, []) if self._match(r, params or {})]
        order = (params or {}).get("order")
        if order:
            col, _, direction = order.partition(".")
            col = col.split(".")[0]
            rows = sorted(rows, key=lambda r: (r.get(col) is None, str(r.get(col))),
                          reverse=direction.startswith("desc"))
        offset = (params or {}).get("offset")
        limit = (params or {}).get("limit")
        if offset:
            rows = rows[int(offset):]
        if limit:
            rows = rows[: int(limit)]
        return rows

    def count(self, table, filters=None, select="id"):
        return len([r for r in self.data.get(table, []) if self._match(r, filters or {})])

    # --- tulis ---

    def _conflict(self, table: str, row: dict) -> bool:
        existing = self.data.get(table, [])
        if table == "automation_jobs":
            active = [j for j in existing if j.get("status") in ("queued", "running")]
            if row.get("automation_config_id") and any(
                j.get("automation_config_id") == row["automation_config_id"] for j in active
            ):
                return True
            if row.get("idempotency_key") and any(
                j.get("idempotency_key") == row["idempotency_key"] for j in existing
            ):
                return True
        if table == "notifications" and row.get("dedupe_key"):
            return any(n.get("dedupe_key") == row["dedupe_key"] for n in existing)
        if table == "automation_configs" and row.get("automation_type"):
            return any(c.get("automation_type") == row["automation_type"] for c in existing)
        return False

    def insert(self, table, rows, *, upsert=False, on_conflict=None, returning=True):
        payload = rows if isinstance(rows, list) else [rows]
        self.inserted.append({"table": table, "rows": payload, "upsert": upsert, "on_conflict": on_conflict})
        out = []
        for r in payload:
            row = dict(r)
            if self._conflict(table, row):
                raise SupabaseError(f"insert {table} gagal (409): duplicate key value violates unique constraint")
            if "id" not in row:
                self._seq += 1
                row["id"] = f"{table}-{self._seq}"
            self.data.setdefault(table, []).append(row)
            out.append(row)
        return out if returning else []

    def update(self, table, filters, values, *, returning=True):
        self.updates.append({"table": table, "filters": filters, "values": values})
        matched = []
        for row in self.data.get(table, []):
            if self._match(row, filters):
                row.update(values)
                matched.append(row)
        return matched if returning else []

    def delete(self, table, filters):
        self.data[table] = [r for r in self.data.get(table, []) if not self._match(r, filters)]

    # helper uji
    def inserted_in(self, table):
        return [i for i in self.inserted if i["table"] == table]

    def updates_in(self, table):
        return [u for u in self.updates if u["table"] == table]

    def rows(self, table):
        return self.data.get(table, [])
