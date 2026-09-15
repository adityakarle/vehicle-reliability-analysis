-- schema.sql
-- Table definition for the vehicle service / repair fact table.
-- Written for SQLite (used by scripts/load_to_sql.py) but is plain
-- ANSI SQL and will run on Postgres/MySQL with trivial type tweaks
-- (e.g. TEXT -> VARCHAR, REAL -> NUMERIC).

DROP TABLE IF EXISTS vehicle_service_records;

CREATE TABLE vehicle_service_records (
    service_id              INTEGER PRIMARY KEY,
    vehicle_id              TEXT    NOT NULL,
    make                    TEXT    NOT NULL,
    model                   TEXT    NOT NULL,
    model_year              INTEGER NOT NULL,
    service_date            TEXT    NOT NULL,   -- ISO date (YYYY-MM-DD)
    service_month           TEXT    NOT NULL,   -- YYYY-MM
    mileage_at_service      INTEGER NOT NULL,
    mileage_band            TEXT    NOT NULL,
    failure_category        TEXT    NOT NULL,
    repair_cost             REAL    NOT NULL,
    days_in_shop            INTEGER NOT NULL,
    technician_id           TEXT    NOT NULL,
    service_center_region   TEXT    NOT NULL,
    warranty_flag           TEXT    NOT NULL
);

CREATE INDEX idx_vsr_vehicle_category ON vehicle_service_records (vehicle_id, failure_category, service_date);
CREATE INDEX idx_vsr_month ON vehicle_service_records (service_month);
CREATE INDEX idx_vsr_category ON vehicle_service_records (failure_category);
