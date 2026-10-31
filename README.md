# PharmaTrack

PharmaTrack is a desktop pharmacy inventory and expiry management system designed to help small pharmacies track medicines, suppliers, stock batches, inventory movements, and low-stock/expiry alerts. The project combines a Python-based backend, a Tkinter desktop interface, and a SQLite database to provide a lightweight, local, database-driven solution without requiring external services or third-party packages.

The application follows FEFO (First Expiry, First Out) dispensing logic so medicines are issued from the earliest-expiring valid batches first. It also monitors expired stock, items nearing expiry, and medicines reaching or falling below reorder levels.

## Project Overview

PharmaTrack is intended for local desktop use and demonstrates practical database-backed application design. It handles core pharmacy operations such as:

- Recording medicines and suppliers
- Receiving inventory batches with expiry dates and costs
- Dispensing stock while preserving valid inventory rules
- Tracking stock history in transaction logs
- Raising alerts for expired, soon-to-expire, and low-stock items
- Displaying data through a graphical Tkinter interface

## Why This Project Exists

A pharmacy often manages dozens or hundreds of medicines across multiple suppliers and batches. Without a structured system, it becomes difficult to:

- know which batches are nearing expiry
- avoid dispensing stock from expired items
- monitor reorder thresholds
- maintain accurate stock quantities and movement history
- identify which supplier provided a specific batch

PharmaTrack addresses these issues with a simple but robust inventory system built on relational database principles.

## Features

### Medicine Management
- Add medicine records including name, generic name, category, unit, and reorder level
- Maintain a central catalog of products used in the pharmacy
- View stock totals associated with each medicine

### Supplier Management
- Register suppliers with name, phone number, and email address
- Link batches to the supplier that provides them

### Batch Receipt
- Receive medicine stock into a batch with:
  - medicine
  - batch number
  - supplier (optional)
  - received date
  - expiry date
  - quantity
  - unit cost
- Validate entries before insertion
- Record a stock receipt transaction in the transaction history

### FEFO Dispensing
- Dispense stock from the earliest-expiring unexpired batch first
- Prevent partial dispensing when sufficient stock is unavailable
- Roll back the operation if the request cannot be fulfilled entirely
- Keep inventory and transaction data consistent

### Inventory Alerts
The system can create and refresh alerts for:

- expired stock
- stock expiring soon within a selected window
- medicines at or below their reorder level

Alerts are stored with status values such as ACTIVE and RESOLVED, and can be recalculated based on current inventory conditions.

### Transaction History
- Record all stock movements as RECEIVE, DISPENSE, or ADJUST transactions
- Track quantity, batch reference, and timestamp
- Keep a searchable audit trail of inventory operations

### User Interface
The desktop app includes tabs and forms for:

- Medicines
- Suppliers
- Batches
- Receiving and dispensing stock
- Alerts
- Transaction history

## Tech Stack

| Component | Technology |
|---|---|
| Programming Language | Python 3 |
| Desktop UI | Tkinter / ttk |
| Database | SQLite |
| Query Language | SQL |
| Platform | Windows desktop; also works in similar local Python environments |

The project uses Python standard-library modules only. No external dependencies are required to run the app.

## Project Structure

The repository contains the following key files:

- `PharmaTrack.py` — main backend/database logic and transactional rules
- `PharmaTrackUI.py` — graphical desktop interface
- `PharmaTrack.sql` — SQL schema for the pharmacy database
- `pharmatrack.db` — SQLite database file created and used by the application
- `Project_Summary.md` — project overview and feature summary

## Database Design

The application stores inventory information in a SQLite database with the following core tables:

### `pharma_supplier`
Stores supplier records, including:
- supplier ID
- supplier name
- phone
- email

### `pharma_medicine`
Stores medicine catalog information, including:
- medicine ID
- medicine name
- generic name
- category
- unit
- reorder level

### `pharma_batch`
Stores stock batches, including:
- batch ID
- medicine ID
- supplier ID
- batch number
- received date
- expiry date
- quantity on hand
- unit cost

### `pharma_stock_transaction`
Stores stock movement logs, including:
- transaction ID
- batch ID
- transaction type
- quantity
- reference text
- transaction timestamp

### `pharma_inventory_alert`
Stores inventory alerts such as:
- expired batches
- expiring-soon stock
- low-stock medicines
- status and timestamps

## Business Rules and Validation

The application enforces several data integrity rules:

- Non-positive receipt quantities are rejected
- Negative unit costs are rejected
- Expiry dates cannot be in the past when receiving stock
- Dispense quantity must be greater than zero
- Quantities on hand cannot be negative
- Batch numbers are unique
- Transaction types are restricted to `RECEIVE`, `DISPENSE`, and `ADJUST`
- Alert types are restricted to `EXPIRED`, `EXPIRES_SOON`, and `LOW_STOCK`
- Alert statuses are limited to `ACTIVE` and `RESOLVED`

Transaction safety is handled using SQLite savepoints so that failed operations can be rolled back cleanly without leaving partial updates.

## FEFO Logic

The dispensing workflow does the following:

1. Selects all stock batches for the chosen medicine
2. Filters out expired or empty batches
3. Orders those batches by expiry date and batch ID
4. Allocates stock in that order
5. Records each dispense as a transaction
6. Rolls back the entire operation if the requested quantity cannot be fulfilled

This ensures that older stock is used first and the business rules remain consistent.

## Alert Logic

PharmaTrack recalculates alert states from the current stock records. Typical rules include:

- expired batches are flagged as `EXPIRED`
- batches within a configured expiry window are flagged as `EXPIRES_SOON`
- medicines with stock at or below reorder level are flagged as `LOW_STOCK`
- resolved alerts are updated when the triggering conditions no longer apply

The alerts screen allows users to set the expiry window in days and refresh the current alert list.

## Setup Instructions

### Prerequisites
- Python 3 installed on the system
- Access to a local terminal or PowerShell environment
- Standard Python library support (Tkinter is typically included with Python distributions)

### Running the Application

From PowerShell on Windows:

```powershell
cd "C:\Users\aanch\OneDrive\Desktop\PLSQL Project"
.\.venv\Scripts\python.exe PharmaTrackUI.py
```

This launches the desktop application. The system will initialize the SQLite database automatically if it does not already exist.

### Running the Terminal Version

The backend also contains a terminal-based menu interface. To run it:

```powershell
cd "C:\Users\aanch\OneDrive\Desktop\PLSQL Project"
.\.venv\Scripts\python.exe PharmaTrack.py
```

## Database Initialization

When the application starts, it creates the database schema automatically if missing. The database is located locally in the project directory as:

```text
pharmatrack.db
```

This makes the project portable and easy to test without installing a separate database server.

## Typical Workflow

### 1. Add Suppliers
Create supplier profiles so batches can be associated with the correct vendor.

### 2. Add Medicines
Add medicines to the catalog with reorder thresholds and units.

### 3. Receive Stock
Create a batch with a batch number, expiry date, quantity, and unit cost. This automatically creates a stock receive transaction.

### 4. Dispense Stock
Select a medicine and enter a quantity. PharmaTrack issues stock in FEFO order and records the dispense operation.

### 5. Review Alerts
Open the alert screen to review expired, expiring-soon, and low-stock situations.

### 6. Inspect Inventory History
Use the transaction and batch views to verify receipts, dispensations, and current stock levels.

## Example Use Case

A pharmacy receives 300 tablets of a medicine, then later receives another batch with a different expiry date. When dispensing 180 tablets, the system will use stock from the earliest-expiring valid batch first until the required volume is fulfilled or until all available batch stock is exhausted. If the total available quantity is insufficient, the app prevents a partial dispense and raises an error.

## Validation and Error Handling

The project includes multiple layers of validation:

- UI-side field checks
- Python function-level validation
- SQLite database constraints
- Transaction rollback for failed inventory operations
- Clear error reporting to the user

This approach reduces the risk of invalid stock data and protects the integrity of inventory counts.

## Limitations

This project is intentionally focused on local desktop pharmacy inventory management. It does not include:

- online or multi-user database access
- patient prescription workflows
- pharmacy billing and sales modules
- user authentication or role-based access control
- cloud synchronization
- advanced analytics dashboards

## Potential Enhancements

Future improvements could include:

- search and filter controls for medicines and batches
- dashboard summaries and charts
- CSV import/export
- reporting for expiry trends and stock usage
- REST API or web interface
- barcode scanner integration
- stronger audit logging and user permissions

## Project Status

PharmaTrack is a functional local inventory management application designed for educational and practical use. It demonstrates key database and inventory logic in a clean, maintainable structure and is suitable as a starting point for more advanced pharmacy management systems.

## License

This project does not currently declare a formal license. If you plan to share or extend the project publicly, it is recommended to add a license such as MIT or Apache 2.0.

## Contributing

Contributions are welcome if you want to extend the system with new inventory features, improve the UI, or strengthen validation and reporting. Recommended improvements include:

- code cleanup and refactoring
- user experience enhancements
- expanded testing
- additional inventory reports
- better data validation and edge-case handling

## Summary

PharmaTrack is a practical, database-backed pharmacy inventory application that emphasizes correctness, stock accuracy, and operational simplicity. It provides a complete local workflow for receiving inventory, dispensing stock using FEFO rules, tracking stock changes, and generating expiry and reorder alerts.

If you are learning Python, SQLite, or desktop application design, this project is a strong example of combining database logic with a user-friendly interface.

