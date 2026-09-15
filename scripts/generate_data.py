"""
generate_data.py
-----------------
Generates a synthetic vehicle-service dataset for the Vehicle Reliability &
Failure Analysis project.

Design goals (so the dataset actually supports the resume bullets):
  - 1,000+ service records
  - 5+ distinct failure categories
  - 12 monthly service periods (Jan-Dec of a single year)
  - Mileage that plausibly accumulates over time per vehicle
  - Real repeat-repair chains (same vehicle + same failure category coming
    back within a short window), so "repeat-repair rate" is a genuine,
    non-hardcoded signal you can (re)detect analytically in pandas/SQL.

Run:
    python scripts/generate_data.py
Output:
    data/raw/vehicle_service_data.csv
"""

import numpy as np
import pandas as pd
from datetime import date, timedelta

# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
SEED = 42
YEAR = 2025
N_VEHICLES = 320
N_BASE_SERVICES = 950      # base (non-repeat) service events
N_REPEAT_CHAINS = 160      # explicit repeat-repair follow-up visits
OUT_PATH = "data/raw/vehicle_service_data.csv"

rng = np.random.default_rng(SEED)

MAKES_MODELS = {
    "Toyota":    ["Camry", "Corolla", "RAV4"],
    "Honda":     ["Civic", "Accord", "CR-V"],
    "Ford":      ["F-150", "Escape", "Explorer"],
    "Chevrolet": ["Malibu", "Equinox", "Silverado"],
    "Nissan":    ["Altima", "Sentra", "Rogue"],
}

FAILURE_CATEGORIES = [
    "Engine", "Transmission", "Brakes", "Electrical",
    "Suspension", "HVAC", "Cooling System",
]

# base likelihood weights (before mileage adjustment)
BASE_WEIGHTS = {
    "Engine": 0.14, "Transmission": 0.10, "Brakes": 0.22,
    "Electrical": 0.16, "Suspension": 0.14, "HVAC": 0.13,
    "Cooling System": 0.11,
}

# categories that become disproportionately more likely at high mileage
HIGH_MILEAGE_CATEGORIES = {"Engine", "Transmission", "Suspension", "Cooling System"}

COST_RANGES = {
    "Engine": (700, 3200), "Transmission": (900, 3500), "Brakes": (150, 650),
    "Electrical": (100, 900), "Suspension": (200, 950), "HVAC": (150, 750),
    "Cooling System": (150, 700),
}

REGIONS = ["Northeast", "Southeast", "Midwest", "West", "Southwest"]
TECHNICIANS = [f"T-{i:02d}" for i in range(1, 21)]

# ----------------------------------------------------------------------
# 1. Build a vehicle pool (each vehicle has its own mileage trajectory)
# ----------------------------------------------------------------------
vehicles = []
for i in range(1, N_VEHICLES + 1):
    make = rng.choice(list(MAKES_MODELS.keys()))
    model = rng.choice(MAKES_MODELS[make])
    model_year = int(rng.integers(2015, 2024))
    age_at_start_of_year = YEAR - model_year
    annual_mileage_rate = rng.integers(8000, 15500)
    # rough mileage already on the odometer by Jan 1 of YEAR
    starting_mileage = max(500, int(age_at_start_of_year * annual_mileage_rate * rng.uniform(0.85, 1.1)))
    vehicles.append({
        "vehicle_id": f"V-{i:04d}",
        "make": make,
        "model": model,
        "model_year": model_year,
        "annual_mileage_rate": annual_mileage_rate,
        "starting_mileage": starting_mileage,
    })
vehicles_df = pd.DataFrame(vehicles)


def random_date_in_year(n=1):
    start = date(YEAR, 1, 1)
    days_in_year = 365
    offsets = rng.integers(0, days_in_year, size=n)
    return [start + timedelta(days=int(o)) for o in offsets]


def mileage_at(vehicle_row, service_date):
    """Estimate odometer reading on a given date for a given vehicle."""
    day_of_year = (service_date - date(YEAR, 1, 1)).days
    fraction_of_year = day_of_year / 365
    noise = rng.uniform(-400, 400)
    return max(0, int(
        vehicle_row["starting_mileage"]
        + vehicle_row["annual_mileage_rate"] * fraction_of_year
        + noise
    ))


def mileage_band(m):
    if m < 25000:
        return "0-25k"
    elif m < 50000:
        return "25k-50k"
    elif m < 75000:
        return "50k-75k"
    elif m < 100000:
        return "75k-100k"
    elif m < 150000:
        return "100k-150k"
    else:
        return "150k+"


def choose_failure_category(mileage):
    weights = BASE_WEIGHTS.copy()
    if mileage > 90000:
        for cat in HIGH_MILEAGE_CATEGORIES:
            weights[cat] *= 1.9
    elif mileage > 60000:
        for cat in HIGH_MILEAGE_CATEGORIES:
            weights[cat] *= 1.4
    cats = list(weights.keys())
    w = np.array([weights[c] for c in cats])
    w = w / w.sum()
    return rng.choice(cats, p=w)


def make_cost(category):
    lo, hi = COST_RANGES[category]
    return round(float(rng.uniform(lo, hi)), 2)


# ----------------------------------------------------------------------
# 2. Generate base (independent) service events
# ----------------------------------------------------------------------
records = []
service_id_counter = 1

vehicle_choice_idx = rng.integers(0, N_VEHICLES, size=N_BASE_SERVICES)
service_dates = random_date_in_year(N_BASE_SERVICES)

for i in range(N_BASE_SERVICES):
    v = vehicles_df.iloc[vehicle_choice_idx[i]]
    sdate = service_dates[i]
    mileage = mileage_at(v, sdate)
    category = choose_failure_category(mileage)
    cost = make_cost(category)
    days_in_shop = int(np.clip(rng.normal(loc=cost / 400, scale=1.2), 1, 10))
    records.append({
        "service_id": service_id_counter,
        "vehicle_id": v["vehicle_id"],
        "make": v["make"],
        "model": v["model"],
        "model_year": int(v["model_year"]),
        "service_date": sdate,
        "mileage_at_service": mileage,
        "failure_category": category,
        "repair_cost": cost,
        "days_in_shop": days_in_shop,
        "technician_id": rng.choice(TECHNICIANS),
        "service_center_region": rng.choice(REGIONS),
        "warranty_flag": "Y" if (YEAR - int(v["model_year"]) <= 3 and rng.random() < 0.55) else "N",
    })
    service_id_counter += 1

# ----------------------------------------------------------------------
# 3. Inject explicit repeat-repair chains
#    (same vehicle + same failure category returns 10-75 days later)
# ----------------------------------------------------------------------
base_df = pd.DataFrame(records)

# pick source events to spawn a repeat visit from (favor costly categories,
# which are more likely to be an incomplete fix in real shops)
candidate_pool = base_df[base_df["failure_category"].isin(
    ["Engine", "Transmission", "Electrical", "Suspension"]
)].sample(n=min(N_REPEAT_CHAINS, len(base_df)), random_state=SEED, replace=False)

for _, src in candidate_pool.iterrows():
    gap_days = int(rng.integers(10, 76))
    new_date = src["service_date"] + timedelta(days=gap_days)
    if new_date.year != YEAR:
        continue
    v = vehicles_df.loc[vehicles_df["vehicle_id"] == src["vehicle_id"]].iloc[0]
    mileage = mileage_at(v, new_date) + int(rng.integers(0, 300))
    category = src["failure_category"]  # same category = genuine repeat
    cost = make_cost(category) * rng.uniform(0.5, 1.0)  # follow-up work often cheaper
    days_in_shop = int(np.clip(rng.normal(loc=cost / 400, scale=1.0), 1, 8))
    records.append({
        "service_id": service_id_counter,
        "vehicle_id": src["vehicle_id"],
        "make": src["make"],
        "model": src["model"],
        "model_year": src["model_year"],
        "service_date": new_date,
        "mileage_at_service": mileage,
        "failure_category": category,
        "repair_cost": round(float(cost), 2),
        "days_in_shop": days_in_shop,
        "technician_id": rng.choice(TECHNICIANS),
        "service_center_region": rng.choice(REGIONS),
        "warranty_flag": "Y" if (YEAR - int(src["model_year"]) <= 3 and rng.random() < 0.55) else "N",
    })
    service_id_counter += 1

# ----------------------------------------------------------------------
# 4. Finalize
# ----------------------------------------------------------------------
df = pd.DataFrame(records)
df["service_date"] = pd.to_datetime(df["service_date"])
df = df.sort_values(["vehicle_id", "service_date"]).reset_index(drop=True)
df["service_id"] = range(1, len(df) + 1)  # re-number cleanly after sort
df["mileage_band"] = df["mileage_at_service"].apply(mileage_band)
df["service_month"] = df["service_date"].dt.to_period("M").astype(str)

# Column order
cols = [
    "service_id", "vehicle_id", "make", "model", "model_year",
    "service_date", "service_month", "mileage_at_service", "mileage_band",
    "failure_category", "repair_cost", "days_in_shop",
    "technician_id", "service_center_region", "warranty_flag",
]
df = df[cols]

df.to_csv(OUT_PATH, index=False)
print(f"Generated {len(df)} records -> {OUT_PATH}")
print(f"Unique vehicles: {df['vehicle_id'].nunique()}")
print(f"Failure categories: {df['failure_category'].nunique()} -> {sorted(df['failure_category'].unique())}")
print(f"Date range: {df['service_date'].min().date()} to {df['service_date'].max().date()}")
print(df["failure_category"].value_counts())
