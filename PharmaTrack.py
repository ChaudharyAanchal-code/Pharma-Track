"""SQLite implementation of PharmaTrack inventory operations."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS pharma_supplier (
    supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_name TEXT NOT NULL,
    phone TEXT,
    email TEXT
);

CREATE TABLE IF NOT EXISTS pharma_medicine (
    medicine_id INTEGER PRIMARY KEY AUTOINCREMENT,
    medicine_name TEXT NOT NULL,
    generic_name TEXT,
    category TEXT,
    unit TEXT NOT NULL DEFAULT 'unit',
    reorder_level REAL NOT NULL DEFAULT 0 CHECK (reorder_level >= 0)
);

CREATE TABLE IF NOT EXISTS pharma_batch (
    batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    medicine_id INTEGER NOT NULL REFERENCES pharma_medicine (medicine_id),
    supplier_id INTEGER REFERENCES pharma_supplier (supplier_id),
    batch_number TEXT NOT NULL UNIQUE,
    received_date TEXT NOT NULL DEFAULT (date('now')),
    expiry_date TEXT NOT NULL,
    quantity_on_hand REAL NOT NULL CHECK (quantity_on_hand >= 0),
    unit_cost REAL NOT NULL DEFAULT 0 CHECK (unit_cost >= 0)
);

CREATE INDEX IF NOT EXISTS pharma_batch_fefo_ix
    ON pharma_batch (medicine_id, expiry_date, batch_id);

CREATE TABLE IF NOT EXISTS pharma_stock_transaction (
    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES pharma_batch (batch_id),
    transaction_type TEXT NOT NULL
        CHECK (transaction_type IN ('RECEIVE', 'DISPENSE', 'ADJUST')),
    quantity REAL NOT NULL CHECK (quantity > 0),
    reference TEXT,
    transaction_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pharma_inventory_alert (
    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
    medicine_id INTEGER NOT NULL REFERENCES pharma_medicine (medicine_id),
    batch_id INTEGER REFERENCES pharma_batch (batch_id),
    alert_type TEXT NOT NULL
        CHECK (alert_type IN ('EXPIRED', 'EXPIRES_SOON', 'LOW_STOCK')),
    alert_message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'RESOLVED')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS pharma_alert_status_ix
    ON pharma_inventory_alert (status, alert_type);
"""


def connect(database: str | Path = "pharmatrack.db") -> sqlite3.Connection:
    """Open a PharmaTrack database with foreign-key enforcement enabled."""
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    """Create the PharmaTrack tables and indexes if they do not exist."""
    connection.executescript(SCHEMA)


@contextmanager
def _atomic(connection: sqlite3.Connection) -> Iterator[None]:
    """Make an operation atomic without committing a caller's outer transaction."""
    connection.execute("SAVEPOINT pharmatrack_operation")
    try:
        yield
    except Exception:
        connection.execute("ROLLBACK TO pharmatrack_operation")
        connection.execute("RELEASE pharmatrack_operation")
        raise
    else:
        connection.execute("RELEASE pharmatrack_operation")


def _as_date(value: date | str | None) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    return date.fromisoformat(value)


def receive_stock(
    connection: sqlite3.Connection,
    medicine_id: int,
    batch_number: str,
    expiry_date: date | str,
    quantity: float,
    unit_cost: float = 0,
    supplier_id: int | None = None,
) -> int:
    """Create a batch and its RECEIVE transaction; return the new batch ID."""
    expiry = _as_date(expiry_date)
    if quantity is None or quantity <= 0:
        raise ValueError("Received quantity must be greater than zero.")
    if unit_cost is None or unit_cost < 0:
        raise ValueError("Unit cost cannot be negative.")
    if expiry is None or expiry < date.today():
        raise ValueError("Expiry date cannot be in the past.")

    with _atomic(connection):
        cursor = connection.execute(
            """
            INSERT INTO pharma_batch (
                medicine_id, supplier_id, batch_number, expiry_date,
                quantity_on_hand, unit_cost
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                medicine_id,
                supplier_id,
                batch_number,
                expiry.isoformat(),
                quantity,
                unit_cost,
            ),
        )
        batch_id = cursor.lastrowid
        connection.execute(
            """
            INSERT INTO pharma_stock_transaction (
                batch_id, transaction_type, quantity, reference
            ) VALUES (?, 'RECEIVE', ?, 'Stock received')
            """,
            (batch_id, quantity),
        )
    return batch_id


def dispense_stock(
    connection: sqlite3.Connection,
    medicine_id: int,
    quantity: float,
    reference: str | None = None,
) -> None:
    """Dispense earliest-expiring unexpired stock, rolling back if insufficient."""
    if quantity is None or quantity <= 0:
        raise ValueError("Dispense quantity must be greater than zero.")

    remaining = quantity
    today = date.today().isoformat()
    with _atomic(connection):
        batches = connection.execute(
            """
            SELECT batch_id, quantity_on_hand
            FROM pharma_batch
            WHERE medicine_id = ?
              AND expiry_date >= ?
              AND quantity_on_hand > 0
            ORDER BY expiry_date, batch_id
            """,
            (medicine_id, today),
        ).fetchall()

        for batch in batches:
            if remaining <= 0:
                break
            available = batch["quantity_on_hand"]
            taken = min(available, remaining)
            connection.execute(
                "UPDATE pharma_batch SET quantity_on_hand = ? WHERE batch_id = ?",
                (available - taken, batch["batch_id"]),
            )
            connection.execute(
                """
                INSERT INTO pharma_stock_transaction (
                    batch_id, transaction_type, quantity, reference
                ) VALUES (?, 'DISPENSE', ?, ?)
                """,
                (batch["batch_id"], taken, reference),
            )
            remaining -= taken

        if remaining > 0:
            raise ValueError(
                f"Insufficient unexpired stock. Unfilled quantity: {remaining:g}"
            )


def refresh_alerts(
    connection: sqlite3.Connection, expiry_window_days: int = 90
) -> None:
    """Create/update current alerts and resolve alerts that are no longer relevant."""
    if expiry_window_days is None or expiry_window_days < 0:
        raise ValueError("Expiry window cannot be negative.")

    today = date.today()
    expiry_limit = (today + timedelta(days=expiry_window_days)).isoformat()
    today_text = today.isoformat()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    desired: dict[tuple[int, int | None, str], str] = {}

    expiring_batches = connection.execute(
        """
        SELECT medicine_id, batch_id, batch_number, expiry_date
        FROM pharma_batch
        WHERE quantity_on_hand > 0 AND expiry_date <= ?
        """,
        (expiry_limit,),
    ).fetchall()
    for batch in expiring_batches:
        expiry = date.fromisoformat(batch["expiry_date"])
        alert_type = "EXPIRED" if expiry < today else "EXPIRES_SOON"
        key = (batch["medicine_id"], batch["batch_id"], alert_type)
        desired[key] = (
            f"Batch {batch['batch_number']} expires on {batch['expiry_date']}"
        )

    medicines = connection.execute(
        """
        SELECT m.medicine_id, m.medicine_name, m.reorder_level,
               COALESCE(SUM(b.quantity_on_hand), 0) AS current_stock
        FROM pharma_medicine AS m
        LEFT JOIN pharma_batch AS b
          ON b.medicine_id = m.medicine_id AND b.expiry_date >= ?
        GROUP BY m.medicine_id, m.medicine_name, m.reorder_level
        """,
        (today_text,),
    ).fetchall()
    for medicine in medicines:
        if medicine["current_stock"] <= medicine["reorder_level"]:
            key = (medicine["medicine_id"], None, "LOW_STOCK")
            desired[key] = (
                "Stock is at or below reorder level for "
                f"{medicine['medicine_name']}"
            )

    with _atomic(connection):
        for (medicine_id, batch_id, alert_type), message in desired.items():
            existing = connection.execute(
                """
                SELECT alert_id FROM pharma_inventory_alert
                WHERE medicine_id = ? AND batch_id IS ? AND alert_type = ?
                ORDER BY alert_id LIMIT 1
                """,
                (medicine_id, batch_id, alert_type),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO pharma_inventory_alert (
                        medicine_id, batch_id, alert_type, alert_message, status
                    ) VALUES (?, ?, ?, ?, 'ACTIVE')
                    """,
                    (medicine_id, batch_id, alert_type, message),
                )
            else:
                connection.execute(
                    """
                    UPDATE pharma_inventory_alert
                    SET alert_message = ?, status = 'ACTIVE', resolved_at = NULL
                    WHERE alert_id = ?
                    """,
                    (message, existing["alert_id"]),
                )

        active_alerts = connection.execute(
            """
            SELECT alert_id, medicine_id, batch_id, alert_type
            FROM pharma_inventory_alert
            WHERE status = 'ACTIVE'
            """
        ).fetchall()
        for alert in active_alerts:
            key = (alert["medicine_id"], alert["batch_id"], alert["alert_type"])
            if key not in desired:
                connection.execute(
                    """
                    UPDATE pharma_inventory_alert
                    SET status = 'RESOLVED', resolved_at = ?
                    WHERE alert_id = ?
                    """,
                    (now, alert["alert_id"]),
                )


def _show_medicines(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT m.medicine_id, m.medicine_name, m.generic_name, m.category,
               m.unit, m.reorder_level,
               COALESCE(SUM(b.quantity_on_hand), 0) AS stock
        FROM pharma_medicine AS m
        LEFT JOIN pharma_batch AS b ON b.medicine_id = m.medicine_id
        GROUP BY m.medicine_id
        ORDER BY m.medicine_name
        """
    ).fetchall()
    if not rows:
        print("No medicines found.")
        return
    print("\nID | Medicine | Generic | Category | Stock | Reorder level | Unit")
    for row in rows:
        print(
            f"{row['medicine_id']} | {row['medicine_name']} | "
            f"{row['generic_name'] or '-'} | {row['category'] or '-'} | "
            f"{row['stock']:g} | {row['reorder_level']:g} | {row['unit']}"
        )


def _show_batches(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT b.batch_id, m.medicine_name, b.batch_number, b.expiry_date,
               b.quantity_on_hand, b.unit_cost, s.supplier_name
        FROM pharma_batch AS b
        JOIN pharma_medicine AS m ON m.medicine_id = b.medicine_id
        LEFT JOIN pharma_supplier AS s ON s.supplier_id = b.supplier_id
        ORDER BY b.expiry_date, b.batch_id
        """
    ).fetchall()
    if not rows:
        print("No batches found.")
        return
    print("\nBatch ID | Medicine | Batch | Expires | Quantity | Unit cost | Supplier")
    for row in rows:
        print(
            f"{row['batch_id']} | {row['medicine_name']} | {row['batch_number']} | "
            f"{row['expiry_date']} | {row['quantity_on_hand']:g} | "
            f"{row['unit_cost']:g} | {row['supplier_name'] or '-'}"
        )


def _add_medicine(connection: sqlite3.Connection) -> None:
    name = input("Medicine name: ").strip()
    if not name:
        raise ValueError("Medicine name cannot be empty.")
    generic_name = input("Generic name (optional): ").strip() or None
    category = input("Category (optional): ").strip() or None
    unit = input("Unit [unit]: ").strip() or "unit"
    reorder_level = float(input("Reorder level [0]: ").strip() or "0")
    if reorder_level < 0:
        raise ValueError("Reorder level cannot be negative.")
    cursor = connection.execute(
        """
        INSERT INTO pharma_medicine (
            medicine_name, generic_name, category, unit, reorder_level
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (name, generic_name, category, unit, reorder_level),
    )
    print(f"Medicine added with ID {cursor.lastrowid}.")


def _add_supplier(connection: sqlite3.Connection) -> None:
    name = input("Supplier name: ").strip()
    if not name:
        raise ValueError("Supplier name cannot be empty.")
    phone = input("Phone (optional): ").strip() or None
    email = input("Email (optional): ").strip() or None
    cursor = connection.execute(
        "INSERT INTO pharma_supplier (supplier_name, phone, email) VALUES (?, ?, ?)",
        (name, phone, email),
    )
    print(f"Supplier added with ID {cursor.lastrowid}.")


def _receive_stock_menu(connection: sqlite3.Connection) -> None:
    _show_medicines(connection)
    medicine_id = int(input("Medicine ID: "))
    batch_number = input("Batch number: ").strip()
    expiry_date = input("Expiry date (YYYY-MM-DD): ").strip()
    quantity = float(input("Quantity received: "))
    unit_cost = float(input("Unit cost [0]: ").strip() or "0")
    supplier_text = input("Supplier ID (optional, blank for none): ").strip()
    supplier_id = int(supplier_text) if supplier_text else None
    batch_id = receive_stock(
        connection, medicine_id, batch_number, expiry_date,
        quantity, unit_cost, supplier_id,
    )
    print(f"Stock received. New batch ID: {batch_id}.")


def _dispense_stock_menu(connection: sqlite3.Connection) -> None:
    _show_medicines(connection)
    medicine_id = int(input("Medicine ID: "))
    quantity = float(input("Quantity to dispense: "))
    reference = input("Reference (optional): ").strip() or None
    dispense_stock(connection, medicine_id, quantity, reference)
    print("Stock dispensed using earliest-expiry batches first.")


def _show_alerts(connection: sqlite3.Connection) -> None:
    window = int(input("Expiry alert window in days [90]: ").strip() or "90")
    refresh_alerts(connection, window)
    rows = connection.execute(
        """
        SELECT alert_id, alert_type, alert_message, status, created_at
        FROM pharma_inventory_alert
        ORDER BY CASE status WHEN 'ACTIVE' THEN 0 ELSE 1 END, alert_id DESC
        """
    ).fetchall()
    if not rows:
        print("No alerts found.")
        return
    print("\nID | Type | Status | Message | Created")
    for row in rows:
        print(
            f"{row['alert_id']} | {row['alert_type']} | {row['status']} | "
            f"{row['alert_message']} | {row['created_at']}"
        )


def _show_transactions(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT t.transaction_id, m.medicine_name, b.batch_number,
               t.transaction_type, t.quantity, t.reference, t.transaction_date
        FROM pharma_stock_transaction AS t
        JOIN pharma_batch AS b ON b.batch_id = t.batch_id
        JOIN pharma_medicine AS m ON m.medicine_id = b.medicine_id
        ORDER BY t.transaction_id DESC
        LIMIT 20
        """
    ).fetchall()
    if not rows:
        print("No stock transactions found.")
        return
    print("\nID | Medicine | Batch | Type | Quantity | Reference | Date")
    for row in rows:
        print(
            f"{row['transaction_id']} | {row['medicine_name']} | "
            f"{row['batch_number']} | {row['transaction_type']} | "
            f"{row['quantity']:g} | {row['reference'] or '-'} | "
            f"{row['transaction_date']}"
        )


def main() -> None:
    """Initialize the default database and run the interactive terminal menu."""
    connection = connect()
    initialize_database(connection)
    print("PharmaTrack database ready: pharmatrack.db")
    actions = {
        "1": ("Show medicines and stock", _show_medicines),
        "2": ("Show batches", _show_batches),
        "3": ("Add medicine", _add_medicine),
        "4": ("Add supplier", _add_supplier),
        "5": ("Receive stock", _receive_stock_menu),
        "6": ("Dispense stock", _dispense_stock_menu),
        "7": ("Refresh and show alerts", _show_alerts),
        "8": ("Show latest transactions", _show_transactions),
    }
    try:
        while True:
            print("\nPharmaTrack")
            for key, (label, _) in actions.items():
                print(f"{key}. {label}")
            print("0. Exit")
            choice = input("Choose an option: ").strip()
            if choice == "0":
                print("Goodbye.")
                break
            action = actions.get(choice)
            if action is None:
                print("Choose a listed option.")
                continue
            try:
                action[1](connection)
                connection.commit()
            except (ValueError, sqlite3.Error) as error:
                connection.rollback()
                print(f"Error: {error}")
    except KeyboardInterrupt:
        print("\nGoodbye.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
