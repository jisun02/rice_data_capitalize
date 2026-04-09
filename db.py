from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def get_db_path() -> Path:
    return Path(__file__).resolve().parent / "rice_trade_intel.db"


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = str((db_path or get_db_path()).resolve())
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_date TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            valid_to TEXT NOT NULL,
            trader_name TEXT NOT NULL,
            origin TEXT NOT NULL,
            rice_type TEXT NOT NULL,
            packaging TEXT NOT NULL,
            incoterm TEXT NOT NULL,
            fob_price REAL NOT NULL,
            conditions TEXT
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS freight_offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_date TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            valid_to TEXT NOT NULL,
            trader_name TEXT NOT NULL,
            origin_port TEXT NOT NULL,
            destination_port TEXT NOT NULL,
            shipping_line TEXT NOT NULL,
            freight_cost REAL NOT NULL,
            conditions TEXT
        );
        """
    )
    conn.commit()


def insert_market_offer(conn: sqlite3.Connection, row: Dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO market_offers (
            offer_date, valid_from, valid_to, trader_name,
            origin, rice_type, packaging, incoterm,
            fob_price, conditions
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            row["offer_date"],
            row["valid_from"],
            row["valid_to"],
            row["trader_name"],
            row["origin"],
            row["rice_type"],
            row["packaging"],
            row["incoterm"],
            row["fob_price"],
            row.get("conditions", ""),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def insert_freight_offer(conn: sqlite3.Connection, row: Dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO freight_offers (
            offer_date, valid_from, valid_to, trader_name,
            origin_port, destination_port, shipping_line,
            freight_cost, conditions
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            row["offer_date"],
            row["valid_from"],
            row["valid_to"],
            row["trader_name"],
            row["origin_port"],
            row["destination_port"],
            row["shipping_line"],
            row["freight_cost"],
            row.get("conditions", ""),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def fetch_df(conn: sqlite3.Connection, query: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    cur = conn.execute(query, tuple(params))
    return list(cur.fetchall())

