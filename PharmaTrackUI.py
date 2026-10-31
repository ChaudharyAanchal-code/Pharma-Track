"""Tkinter desktop interface for the PharmaTrack SQLite database."""

from __future__ import annotations

import ctypes
import sqlite3
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from PharmaTrack import connect, dispense_stock, initialize_database, receive_stock, refresh_alerts


DATABASE_PATH = Path(__file__).resolve().with_name("pharmatrack.db")


def enable_dpi_awareness() -> None:
    """Enable native per-monitor DPI rendering on Windows before creating Tk."""
    if sys.platform != "win32":
        return

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    try:
        set_context = user32.SetProcessDpiAwarenessContext
    except AttributeError:
        set_context = None
    if set_context is not None:
        set_context.argtypes = (ctypes.c_void_p,)
        set_context.restype = ctypes.c_bool
        if set_context(ctypes.c_void_p(-4)):
            return

    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
    except OSError:
        shcore = None
    if shcore is not None:
        try:
            set_awareness = shcore.SetProcessDpiAwareness
        except AttributeError:
            set_awareness = None
        if set_awareness is not None:
            set_awareness.argtypes = (ctypes.c_int,)
            set_awareness.restype = ctypes.c_long
            if set_awareness(2) == 0:
                return

    try:
        set_legacy_awareness = user32.SetProcessDPIAware
    except AttributeError:
        return
    set_legacy_awareness.argtypes = ()
    set_legacy_awareness.restype = ctypes.c_bool
    set_legacy_awareness()


class PharmaTrackApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PharmaTrack | Pharmacy Inventory")
        self.geometry("1120x720")
        self.minsize(900, 600)
        self.configure(bg="#f3f6fa")

        self.connection = connect(DATABASE_PATH)
        initialize_database(self.connection)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self._configure_style()
        self._build_header()
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self._build_medicines_tab()
        self._build_batches_tab()
        self._build_suppliers_tab()
        self._build_stock_tab()
        self._build_alerts_tab()
        self._build_transactions_tab()
        self.refresh_all()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#ffffff")
        style.configure("TLabel", background="#ffffff", foreground="#243247")
        style.configure("TButton", padding=(10, 7))
        style.configure("Accent.TButton", background="#176b87", foreground="white")
        style.map("Accent.TButton", background=[("active", "#10546b")])
        style.configure(
            "Treeview",
            rowheight=29,
            background="white",
            fieldbackground="white",
            foreground="#243247",
        )
        style.configure(
            "Treeview.Heading",
            background="#e8eff5",
            foreground="#243247",
            padding=7,
            font=("", 9, "bold"),
        )
        style.configure("TNotebook", background="#f3f6fa", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 9))

    def _build_header(self) -> None:
        header = tk.Frame(self, bg="#123b56", padx=22, pady=15)
        header.pack(fill="x")
        tk.Label(
            header,
            text="PharmaTrack",
            bg="#123b56",
            fg="white",
            font=("Segoe UI", 19, "bold"),
        ).pack(side="left")
        tk.Label(
            header,
            text=f"Pharmacy inventory  •  {DATABASE_PATH.name}",
            bg="#123b56",
            fg="#d4e5ee",
            font=("Segoe UI", 10),
        ).pack(side="left", padx=16, pady=(5, 0))
        ttk.Button(header, text="Refresh", command=self.refresh_all).pack(side="right")

    @staticmethod
    def _tab(notebook: ttk.Notebook, title: str) -> ttk.Frame:
        frame = ttk.Frame(notebook, padding=14)
        notebook.add(frame, text=title)
        return frame

    @staticmethod
    def _make_tree(
        parent: ttk.Frame, columns: tuple[tuple[str, str, int], ...]
    ) -> ttk.Treeview:
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True, pady=(12, 0))
        names = [column[0] for column in columns]
        tree = ttk.Treeview(container, columns=names, show="headings")
        for name, heading, width in columns:
            tree.heading(name, text=heading)
            tree.column(name, width=width, minwidth=70, anchor="w")
        vertical = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        return tree

    @staticmethod
    def _clear_tree(tree: ttk.Treeview) -> None:
        tree.delete(*tree.get_children())

    def _build_medicines_tab(self) -> None:
        tab = self._tab(self.tabs, "Medicines")
        form = ttk.LabelFrame(tab, text="Add medicine", padding=10)
        form.pack(fill="x")
        self.medicine_fields = {
            "name": tk.StringVar(),
            "generic": tk.StringVar(),
            "category": tk.StringVar(),
            "unit": tk.StringVar(value="unit"),
            "reorder": tk.StringVar(value="0"),
        }
        fields = (
            ("Medicine name *", "name"),
            ("Generic name", "generic"),
            ("Category", "category"),
            ("Unit", "unit"),
            ("Reorder level", "reorder"),
        )
        for index, (label, key) in enumerate(fields):
            column = index * 2
            ttk.Label(form, text=label).grid(row=0, column=column, sticky="w", padx=4)
            ttk.Entry(form, textvariable=self.medicine_fields[key], width=19).grid(
                row=1, column=column, columnspan=2, sticky="ew", padx=4, pady=(4, 0)
            )
            form.columnconfigure(column, weight=1)
        ttk.Button(
            form, text="Add medicine", style="Accent.TButton",
            command=self.add_medicine,
        ).grid(row=1, column=10, padx=(8, 2))
        ttk.Label(tab, text="Current inventory", font=("", 11, "bold")).pack(
            anchor="w", pady=(16, 0)
        )
        self.medicines_tree = self._make_tree(
            tab,
            (
                ("id", "ID", 60),
                ("name", "Medicine", 190),
                ("generic", "Generic name", 170),
                ("category", "Category", 130),
                ("stock", "Stock", 100),
                ("reorder", "Reorder level", 115),
                ("unit", "Unit", 90),
            ),
        )

    def _build_batches_tab(self) -> None:
        tab = self._tab(self.tabs, "Batches")
        ttk.Label(
            tab, text="Batches are listed by earliest expiry date.", foreground="#526477"
        ).pack(anchor="w")
        self.batches_tree = self._make_tree(
            tab,
            (
                ("id", "Batch ID", 75),
                ("medicine", "Medicine", 180),
                ("batch", "Batch number", 150),
                ("expiry", "Expiry date", 110),
                ("quantity", "Quantity", 100),
                ("cost", "Unit cost", 100),
                ("supplier", "Supplier", 180),
            ),
        )

    def _build_suppliers_tab(self) -> None:
        tab = self._tab(self.tabs, "Suppliers")
        form = ttk.LabelFrame(tab, text="Add supplier", padding=10)
        form.pack(fill="x")
        self.supplier_fields = {
            "name": tk.StringVar(),
            "phone": tk.StringVar(),
            "email": tk.StringVar(),
        }
        for index, (label, key) in enumerate(
            (("Supplier name *", "name"), ("Phone", "phone"), ("Email", "email"))
        ):
            ttk.Label(form, text=label).grid(row=0, column=index, sticky="w", padx=4)
            ttk.Entry(form, textvariable=self.supplier_fields[key], width=30).grid(
                row=1, column=index, sticky="ew", padx=4, pady=(4, 0)
            )
            form.columnconfigure(index, weight=1)
        ttk.Button(
            form, text="Add supplier", style="Accent.TButton",
            command=self.add_supplier,
        ).grid(row=1, column=3, padx=(8, 2))
        self.suppliers_tree = self._make_tree(
            tab,
            (
                ("id", "ID", 70),
                ("name", "Supplier", 260),
                ("phone", "Phone", 180),
                ("email", "Email", 300),
            ),
        )

    def _build_stock_tab(self) -> None:
        tab = self._tab(self.tabs, "Receive / dispense")
        self.medicine_options: dict[str, int] = {}
        self.supplier_options: dict[str, int | None] = {}

        receive = ttk.LabelFrame(tab, text="Receive stock", padding=14)
        receive.pack(fill="x", pady=(0, 14))
        self.receive_medicine = tk.StringVar()
        self.receive_supplier = tk.StringVar()
        self.receive_batch = tk.StringVar()
        self.receive_expiry = tk.StringVar()
        self.receive_quantity = tk.StringVar()
        self.receive_cost = tk.StringVar(value="0")
        receive_fields = (
            ("Medicine *", self.receive_medicine, 24),
            ("Supplier", self.receive_supplier, 22),
            ("Batch number *", self.receive_batch, 18),
            ("Expiry (YYYY-MM-DD) *", self.receive_expiry, 18),
            ("Quantity *", self.receive_quantity, 12),
            ("Unit cost", self.receive_cost, 12),
        )
        for index, (label, variable, width) in enumerate(receive_fields):
            ttk.Label(receive, text=label).grid(
                row=0, column=index, sticky="w", padx=4
            )
            if label == "Medicine *":
                widget: tk.Widget = ttk.Combobox(
                    receive, textvariable=variable, width=width, state="readonly"
                )
                self.receive_medicine_combo = widget
            elif label == "Supplier":
                widget = ttk.Combobox(
                    receive, textvariable=variable, width=width, state="readonly"
                )
                self.receive_supplier_combo = widget
            else:
                widget = ttk.Entry(receive, textvariable=variable, width=width)
            widget.grid(row=1, column=index, sticky="ew", padx=4, pady=(4, 0))
        ttk.Button(
            receive, text="Receive", style="Accent.TButton",
            command=self.receive_from_form,
        ).grid(row=2, column=0, sticky="w", padx=4, pady=(12, 0))

        dispense = ttk.LabelFrame(tab, text="Dispense stock (earliest expiry first)", padding=14)
        dispense.pack(fill="x")
        self.dispense_medicine = tk.StringVar()
        self.dispense_quantity = tk.StringVar()
        self.dispense_reference = tk.StringVar()
        ttk.Label(dispense, text="Medicine *").grid(row=0, column=0, sticky="w", padx=4)
        self.dispense_medicine_combo = ttk.Combobox(
            dispense, textvariable=self.dispense_medicine, width=30, state="readonly"
        )
        self.dispense_medicine_combo.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        ttk.Label(dispense, text="Quantity *").grid(row=0, column=1, sticky="w", padx=4)
        ttk.Entry(dispense, textvariable=self.dispense_quantity, width=18).grid(
            row=1, column=1, sticky="ew", padx=4, pady=4
        )
        ttk.Label(dispense, text="Reference").grid(row=0, column=2, sticky="w", padx=4)
        ttk.Entry(dispense, textvariable=self.dispense_reference, width=28).grid(
            row=1, column=2, sticky="ew", padx=4, pady=4
        )
        ttk.Button(
            dispense, text="Dispense", style="Accent.TButton",
            command=self.dispense_from_form,
        ).grid(row=1, column=3, padx=8)
        for column in range(3):
            dispense.columnconfigure(column, weight=1)

    def _build_alerts_tab(self) -> None:
        tab = self._tab(self.tabs, "Alerts")
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Expiry window (days):").pack(side="left")
        self.alert_window = tk.StringVar(value="90")
        ttk.Entry(toolbar, textvariable=self.alert_window, width=8).pack(
            side="left", padx=8
        )
        ttk.Button(
            toolbar, text="Refresh alerts", command=self.refresh_alerts_view
        ).pack(side="left")
        self.alerts_tree = self._make_tree(
            tab,
            (
                ("id", "ID", 60),
                ("type", "Type", 130),
                ("status", "Status", 100),
                ("message", "Message", 520),
                ("created", "Created", 180),
            ),
        )

    def _build_transactions_tab(self) -> None:
        tab = self._tab(self.tabs, "Transactions")
        ttk.Label(tab, text="Latest stock movements", font=("", 11, "bold")).pack(
            anchor="w"
        )
        self.transactions_tree = self._make_tree(
            tab,
            (
                ("id", "ID", 65),
                ("medicine", "Medicine", 180),
                ("batch", "Batch", 140),
                ("type", "Type", 100),
                ("quantity", "Quantity", 100),
                ("reference", "Reference", 180),
                ("date", "Date", 180),
            ),
        )

    def _run_action(self, action: Callable[[], None]) -> None:
        try:
            action()
            self.connection.commit()
            self.refresh_all()
        except (ValueError, sqlite3.Error) as error:
            self.connection.rollback()
            messagebox.showerror("PharmaTrack error", str(error), parent=self)

    def add_medicine(self) -> None:
        def action() -> None:
            name = self.medicine_fields["name"].get().strip()
            if not name:
                raise ValueError("Medicine name is required.")
            reorder = float(self.medicine_fields["reorder"].get() or "0")
            if reorder < 0:
                raise ValueError("Reorder level cannot be negative.")
            self.connection.execute(
                """
                INSERT INTO pharma_medicine (
                    medicine_name, generic_name, category, unit, reorder_level
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    name,
                    self.medicine_fields["generic"].get().strip() or None,
                    self.medicine_fields["category"].get().strip() or None,
                    self.medicine_fields["unit"].get().strip() or "unit",
                    reorder,
                ),
            )
            for variable in self.medicine_fields.values():
                variable.set("unit" if variable is self.medicine_fields["unit"] else "")
            self.medicine_fields["reorder"].set("0")
            messagebox.showinfo("PharmaTrack", "Medicine added.", parent=self)

        self._run_action(action)

    def add_supplier(self) -> None:
        def action() -> None:
            name = self.supplier_fields["name"].get().strip()
            if not name:
                raise ValueError("Supplier name is required.")
            self.connection.execute(
                """
                INSERT INTO pharma_supplier (supplier_name, phone, email)
                VALUES (?, ?, ?)
                """,
                (
                    name,
                    self.supplier_fields["phone"].get().strip() or None,
                    self.supplier_fields["email"].get().strip() or None,
                ),
            )
            for variable in self.supplier_fields.values():
                variable.set("")
            messagebox.showinfo("PharmaTrack", "Supplier added.", parent=self)

        self._run_action(action)

    def receive_from_form(self) -> None:
        def action() -> None:
            medicine_id = self.medicine_options.get(self.receive_medicine.get())
            if medicine_id is None:
                raise ValueError("Select a medicine.")
            supplier_id = self.supplier_options.get(self.receive_supplier.get())
            batch_id = receive_stock(
                self.connection,
                medicine_id,
                self.receive_batch.get().strip(),
                self.receive_expiry.get().strip(),
                float(self.receive_quantity.get()),
                float(self.receive_cost.get() or "0"),
                supplier_id,
            )
            self.receive_batch.set("")
            self.receive_expiry.set("")
            self.receive_quantity.set("")
            self.receive_cost.set("0")
            messagebox.showinfo(
                "PharmaTrack", f"Stock received. Batch ID: {batch_id}.", parent=self
            )

        self._run_action(action)

    def dispense_from_form(self) -> None:
        def action() -> None:
            medicine_id = self.medicine_options.get(self.dispense_medicine.get())
            if medicine_id is None:
                raise ValueError("Select a medicine.")
            dispense_stock(
                self.connection,
                medicine_id,
                float(self.dispense_quantity.get()),
                self.dispense_reference.get().strip() or None,
            )
            self.dispense_quantity.set("")
            self.dispense_reference.set("")
            messagebox.showinfo("PharmaTrack", "Stock dispensed.", parent=self)

        self._run_action(action)

    def refresh_alerts_view(self) -> None:
        try:
            days = int(self.alert_window.get())
            refresh_alerts(self.connection, days)
            self.connection.commit()
            self.refresh_all(refresh_alerts_data=False)
        except (ValueError, sqlite3.Error) as error:
            self.connection.rollback()
            messagebox.showerror("PharmaTrack error", str(error), parent=self)

    def refresh_all(self, refresh_alerts_data: bool = True) -> None:
        if refresh_alerts_data:
            try:
                refresh_alerts(self.connection)
                self.connection.commit()
            except sqlite3.Error as error:
                self.connection.rollback()
                messagebox.showerror("Database error", str(error), parent=self)
                return

        self._refresh_medicines()
        self._refresh_batches()
        self._refresh_suppliers()
        self._refresh_selectors()
        self._refresh_alerts()
        self._refresh_transactions()

    def _refresh_medicines(self) -> None:
        self._clear_tree(self.medicines_tree)
        rows = self.connection.execute(
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
        for row in rows:
            self.medicines_tree.insert(
                "", "end",
                values=(
                    row["medicine_id"], row["medicine_name"],
                    row["generic_name"] or "", row["category"] or "",
                    f"{row['stock']:g}", f"{row['reorder_level']:g}", row["unit"],
                ),
            )

    def _refresh_batches(self) -> None:
        self._clear_tree(self.batches_tree)
        rows = self.connection.execute(
            """
            SELECT b.batch_id, m.medicine_name, b.batch_number, b.expiry_date,
                   b.quantity_on_hand, b.unit_cost, s.supplier_name
            FROM pharma_batch AS b
            JOIN pharma_medicine AS m ON m.medicine_id = b.medicine_id
            LEFT JOIN pharma_supplier AS s ON s.supplier_id = b.supplier_id
            ORDER BY b.expiry_date, b.batch_id
            """
        ).fetchall()
        for row in rows:
            self.batches_tree.insert(
                "", "end",
                values=(
                    row["batch_id"], row["medicine_name"], row["batch_number"],
                    row["expiry_date"], f"{row['quantity_on_hand']:g}",
                    f"{row['unit_cost']:g}", row["supplier_name"] or "",
                ),
            )

    def _refresh_suppliers(self) -> None:
        self._clear_tree(self.suppliers_tree)
        rows = self.connection.execute(
            """
            SELECT supplier_id, supplier_name, phone, email
            FROM pharma_supplier ORDER BY supplier_name
            """
        ).fetchall()
        for row in rows:
            self.suppliers_tree.insert(
                "", "end",
                values=(
                    row["supplier_id"], row["supplier_name"],
                    row["phone"] or "", row["email"] or "",
                ),
            )

    def _refresh_selectors(self) -> None:
        medicines = self.connection.execute(
            "SELECT medicine_id, medicine_name FROM pharma_medicine ORDER BY medicine_name"
        ).fetchall()
        self.medicine_options = {
            f"{row['medicine_name']} (ID {row['medicine_id']})": row["medicine_id"]
            for row in medicines
        }
        medicine_names = list(self.medicine_options)
        self.receive_medicine_combo.configure(values=medicine_names)
        self.dispense_medicine_combo.configure(values=medicine_names)
        suppliers = self.connection.execute(
            "SELECT supplier_id, supplier_name FROM pharma_supplier ORDER BY supplier_name"
        ).fetchall()
        self.supplier_options = {"": None}
        self.supplier_options.update(
            {
                f"{row['supplier_name']} (ID {row['supplier_id']})": row["supplier_id"]
                for row in suppliers
            }
        )
        self.receive_supplier_combo.configure(values=list(self.supplier_options))

    def _refresh_alerts(self) -> None:
        self._clear_tree(self.alerts_tree)
        rows = self.connection.execute(
            """
            SELECT alert_id, alert_type, status, alert_message, created_at
            FROM pharma_inventory_alert
            ORDER BY CASE status WHEN 'ACTIVE' THEN 0 ELSE 1 END, alert_id DESC
            """
        ).fetchall()
        for row in rows:
            self.alerts_tree.insert(
                "", "end",
                values=(
                    row["alert_id"], row["alert_type"], row["status"],
                    row["alert_message"], row["created_at"],
                ),
            )

    def _refresh_transactions(self) -> None:
        self._clear_tree(self.transactions_tree)
        rows = self.connection.execute(
            """
            SELECT t.transaction_id, m.medicine_name, b.batch_number,
                   t.transaction_type, t.quantity, t.reference, t.transaction_date
            FROM pharma_stock_transaction AS t
            JOIN pharma_batch AS b ON b.batch_id = t.batch_id
            JOIN pharma_medicine AS m ON m.medicine_id = b.medicine_id
            ORDER BY t.transaction_id DESC
            LIMIT 200
            """
        ).fetchall()
        for row in rows:
            self.transactions_tree.insert(
                "", "end",
                values=(
                    row["transaction_id"], row["medicine_name"], row["batch_number"],
                    row["transaction_type"], f"{row['quantity']:g}",
                    row["reference"] or "", row["transaction_date"],
                ),
            )

    def close(self) -> None:
        self.connection.close()
        self.destroy()


def main() -> None:
    enable_dpi_awareness()
    app = PharmaTrackApp()
    app.mainloop()


if __name__ == "__main__":
    main()
