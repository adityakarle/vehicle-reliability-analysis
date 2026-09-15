-- analysis_queries.sql
-- Core analytical queries against vehicle_service_records.
-- Run with: sqlite3 data/processed/vehicle_reliability.db < sql/analysis_queries.sql
-- (or paste individual blocks into any SQL client / DB Browser for SQLite)

-- ============================================================
-- 1. FAILURE COUNTS BY CATEGORY
-- ============================================================
SELECT
    failure_category,
    COUNT(*)                                            AS failure_count,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM vehicle_service_records), 2) AS pct_of_total,
    ROUND(AVG(repair_cost), 2)                          AS avg_repair_cost,
    ROUND(AVG(days_in_shop), 2)                         AS avg_days_in_shop
FROM vehicle_service_records
GROUP BY failure_category
ORDER BY failure_count DESC;


-- ============================================================
-- 2. REPEAT-REPAIR DETECTION (window function: LAG)
--    A "repeat repair" = same vehicle + same failure category
--    returning within 90 days of a prior visit for that same issue.
-- ============================================================
DROP VIEW IF EXISTS v_repeat_flagged;
CREATE VIEW v_repeat_flagged AS
WITH ordered AS (
    SELECT
        *,
        LAG(service_date) OVER (
            PARTITION BY vehicle_id, failure_category
            ORDER BY service_date
        ) AS prev_service_date
    FROM vehicle_service_records
)
SELECT
    *,
    CASE
        WHEN prev_service_date IS NOT NULL
             AND julianday(service_date) - julianday(prev_service_date) <= 90
        THEN 1 ELSE 0
    END AS is_repeat_repair
FROM ordered;

-- Overall repeat-repair rate (record-level)
SELECT
    ROUND(100.0 * SUM(is_repeat_repair) / COUNT(*), 2) AS repeat_repair_rate_pct,
    SUM(is_repeat_repair)                              AS repeat_repair_count,
    COUNT(*)                                           AS total_records
FROM v_repeat_flagged;

-- Repeat-repair rate by failure category
SELECT
    failure_category,
    COUNT(*)                                            AS total_records,
    SUM(is_repeat_repair)                               AS repeat_records,
    ROUND(100.0 * SUM(is_repeat_repair) / COUNT(*), 2)  AS repeat_rate_pct
FROM v_repeat_flagged
GROUP BY failure_category
ORDER BY repeat_rate_pct DESC;


-- ============================================================
-- 3. MILEAGE-BAND RELIABILITY PATTERNS
-- ============================================================
SELECT
    mileage_band,
    failure_category,
    COUNT(*) AS failure_count
FROM vehicle_service_records
GROUP BY mileage_band, failure_category
ORDER BY
    CASE mileage_band
        WHEN '0-25k' THEN 1 WHEN '25k-50k' THEN 2 WHEN '50k-75k' THEN 3
        WHEN '75k-100k' THEN 4 WHEN '100k-150k' THEN 5 ELSE 6
    END,
    failure_count DESC;

-- Average mileage at failure, per category (which failures show up "early" vs "late")
SELECT
    failure_category,
    ROUND(AVG(mileage_at_service), 0) AS avg_mileage_at_failure,
    MIN(mileage_at_service)           AS min_mileage,
    MAX(mileage_at_service)           AS max_mileage
FROM vehicle_service_records
GROUP BY failure_category
ORDER BY avg_mileage_at_failure DESC;


-- ============================================================
-- 4. MONTHLY TREND / TIME-SERIES ANALYSIS
--    Includes month-over-month % change via window function (LAG)
-- ============================================================
WITH monthly AS (
    SELECT
        service_month,
        COUNT(*) AS total_services
    FROM vehicle_service_records
    GROUP BY service_month
)
SELECT
    service_month,
    total_services,
    LAG(total_services) OVER (ORDER BY service_month)                    AS prev_month_services,
    ROUND(
        100.0 * (total_services - LAG(total_services) OVER (ORDER BY service_month))
        / LAG(total_services) OVER (ORDER BY service_month), 2
    ) AS mom_pct_change,
    ROUND(AVG(total_services) OVER (
        ORDER BY service_month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ), 1) AS rolling_3mo_avg
FROM monthly
ORDER BY service_month;

-- Monthly trend broken out by failure category (for the Power BI line chart)
SELECT
    service_month,
    failure_category,
    COUNT(*) AS failure_count
FROM vehicle_service_records
GROUP BY service_month, failure_category
ORDER BY service_month, failure_category;


-- ============================================================
-- 5. MODEL-LEVEL RELIABILITY RANKING
--    Failures per vehicle, to compare models fairly (some models
--    have more vehicles in the fleet than others).
-- ============================================================
WITH vehicle_counts AS (
    SELECT make, model, COUNT(DISTINCT vehicle_id) AS n_vehicles
    FROM vehicle_service_records
    GROUP BY make, model
),
failure_counts AS (
    SELECT make, model, COUNT(*) AS n_failures
    FROM vehicle_service_records
    GROUP BY make, model
)
SELECT
    f.make,
    f.model,
    v.n_vehicles,
    f.n_failures,
    ROUND(1.0 * f.n_failures / v.n_vehicles, 2) AS failures_per_vehicle
FROM failure_counts f
JOIN vehicle_counts v ON f.make = v.make AND f.model = v.model
ORDER BY failures_per_vehicle DESC;


-- ============================================================
-- 6. WARRANTY VS. OUT-OF-WARRANTY COST EXPOSURE
-- ============================================================
SELECT
    warranty_flag,
    COUNT(*)                    AS record_count,
    ROUND(SUM(repair_cost), 2)  AS total_repair_cost,
    ROUND(AVG(repair_cost), 2)  AS avg_repair_cost
FROM vehicle_service_records
GROUP BY warranty_flag;
