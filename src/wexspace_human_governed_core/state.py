from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import NodeState, WorkState


NODE_ORDER = ("inspect_request", "reconcile_evidence", "prepare_review_package")


class WorkRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def _init(self) -> None:
        with self._connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS work (
                id TEXT PRIMARY KEY,
                objective TEXT NOT NULL,
                inputs_json TEXT NOT NULL,
                state TEXT NOT NULL,
                cursor INTEGER NOT NULL DEFAULT 0,
                revision INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS nodes (
                work_id TEXT NOT NULL,
                name TEXT NOT NULL,
                state TEXT NOT NULL,
                output_json TEXT,
                PRIMARY KEY(work_id, name)
            );
            CREATE TABLE IF NOT EXISTS side_effects (
                work_id TEXT NOT NULL,
                effect_key TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY(work_id, effect_key)
            );
            CREATE TABLE IF NOT EXISTS decisions (
                work_id TEXT PRIMARY KEY,
                reviewer TEXT NOT NULL,
                decision TEXT NOT NULL,
                note TEXT
            );
            CREATE TABLE IF NOT EXISTS failures (
                work_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                route TEXT NOT NULL,
                state_token TEXT NOT NULL,
                PRIMARY KEY(work_id, fingerprint, route, state_token)
            );
            """)

    def create(self, work_id: str, objective: str, inputs: dict[str, Any]) -> None:
        with self._connect() as c:
            c.execute(
                "INSERT INTO work(id,objective,inputs_json,state,cursor,revision) VALUES(?,?,?,?,0,0)",
                (work_id, objective, json.dumps(inputs, sort_keys=True), WorkState.OPEN.value),
            )
            c.executemany(
                "INSERT INTO nodes(work_id,name,state) VALUES(?,?,?)",
                [(work_id, name, NodeState.PENDING.value) for name in NODE_ORDER],
            )

    def work(self, work_id: str) -> dict[str, Any]:
        with self._connect() as c:
            r = c.execute("SELECT * FROM work WHERE id=?", (work_id,)).fetchone()
            if r is None:
                raise KeyError(work_id)
            d = dict(r)
            d["inputs"] = json.loads(d.pop("inputs_json"))
            return d

    def node(self, work_id: str, name: str) -> dict[str, Any]:
        with self._connect() as c:
            r = c.execute("SELECT * FROM nodes WHERE work_id=? AND name=?", (work_id, name)).fetchone()
            if r is None:
                raise KeyError((work_id, name))
            d = dict(r)
            d["output"] = json.loads(d["output_json"]) if d["output_json"] else None
            return d

    def set_node_pass(self, work_id: str, name: str, output: dict[str, Any]) -> None:
        with self._connect() as c:
            row = c.execute("SELECT cursor FROM work WHERE id=?", (work_id,)).fetchone()
            cursor = int(row["cursor"])
            expected = NODE_ORDER[cursor] if cursor < len(NODE_ORDER) else None
            if name != expected:
                existing = c.execute("SELECT state FROM nodes WHERE work_id=? AND name=?", (work_id, name)).fetchone()
                if existing and existing["state"] == NodeState.PASS.value:
                    return
                raise RuntimeError(f"cursor mismatch: expected {expected}, got {name}")
            c.execute(
                "UPDATE nodes SET state=?, output_json=? WHERE work_id=? AND name=?",
                (NodeState.PASS.value, json.dumps(output, sort_keys=True), work_id, name),
            )
            next_cursor = cursor + 1
            next_state = WorkState.HUMAN_REVIEW.value if next_cursor == len(NODE_ORDER) else WorkState.OPEN.value
            c.execute(
                "UPDATE work SET cursor=?, state=?, revision=revision+1 WHERE id=?",
                (next_cursor, next_state, work_id),
            )

    def record_effect_once(self, work_id: str, effect_key: str, payload: dict[str, Any]) -> bool:
        with self._connect() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO side_effects(work_id,effect_key,payload_json) VALUES(?,?,?)",
                (work_id, effect_key, json.dumps(payload, sort_keys=True)),
            )
            return cur.rowcount == 1

    def effect_count(self, work_id: str, effect_key: str) -> int:
        with self._connect() as c:
            r = c.execute("SELECT COUNT(*) AS n FROM side_effects WHERE work_id=? AND effect_key=?", (work_id, effect_key)).fetchone()
            return int(r["n"])

    def review(self, work_id: str, reviewer: str, approve: bool, note: str = "") -> None:
        with self._connect() as c:
            work = c.execute("SELECT state FROM work WHERE id=?", (work_id,)).fetchone()
            if work is None:
                raise KeyError(work_id)
            if work["state"] != WorkState.HUMAN_REVIEW.value:
                raise RuntimeError("work is not at HUMAN_REVIEW")
            decision = "APPROVE" if approve else "REJECT"
            c.execute(
                "INSERT OR REPLACE INTO decisions(work_id,reviewer,decision,note) VALUES(?,?,?,?)",
                (work_id, reviewer, decision, note),
            )
            c.execute("UPDATE work SET state=?, revision=revision+1 WHERE id=?", ((WorkState.APPROVED if approve else WorkState.REJECTED).value, work_id))

    def register_failure_attempt(self, work_id: str, fingerprint: str, route: str, state_token: str) -> None:
        try:
            with self._connect() as c:
                c.execute(
                    "INSERT INTO failures(work_id,fingerprint,route,state_token) VALUES(?,?,?,?)",
                    (work_id, fingerprint, route, state_token),
                )
        except sqlite3.IntegrityError as e:
            raise RuntimeError("identical failed route under unchanged state is forbidden") from e
