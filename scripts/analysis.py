"""
analysis.py
-----------
Core pandas analysis for the Vehicle Reliability & Failure Analysis project.

Produces:
  - data/processed/fact_table_enriched.csv   (raw records + is_repeat_repair flag)
  - data/processed/summary_category.csv
  - data/processed/summary_monthly_trend.csv
  - data/processed/summary_monthly_by_category.csv
  - data/processed/summary_mileage_band.csv
  - data/processed/summary_model_reliability.csv
  - outputs/charts/*.png

These CSVs are what get loaded into Power BI (Get Data > Text/CSV), and the
enriched fact table is also what a Power BI star schema would use as the
central fact table.

Run:
    python scripts/analysis.py
"""

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

RAW_PATH = Path("data/raw/vehicle_service_data.csv")
PROCESSED_DIR = Path("data/processed")
CHARTS_DIR = Path("outputs/charts")
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

MILEAGE_BAND_ORDER = ["0-25k", "25k-50k", "50k-75k", "75k-100k", "100k-150k", "150k+"]

# ----------------------------------------------------------------------
# Load
# ----------------------------------------------------------------------
df = pd.read_csv(RAW_PATH, parse_dates=["service_date"])
df = df.sort_values(["vehicle_id", "failure_category", "service_date"]).reset_index(drop=True)

# ----------------------------------------------------------------------
# 1. Repeat-repair detection
#    Same vehicle + same failure category, prior visit within 90 days.
# ----------------------------------------------------------------------
df["prev_service_date"] = df.groupby(["vehicle_id", "failure_category"])["service_date"].shift(1)
df["days_since_prev_same_category"] = (df["service_date"] - df["prev_service_date"]).dt.days
df["is_repeat_repair"] = (
    df["days_since_prev_same_category"].notna() & (df["days_since_prev_same_category"] <= 90)
).astype(int)

overall_repeat_rate = 100 * df["is_repeat_repair"].mean()
print(f"Overall repeat-repair rate: {overall_repeat_rate:.2f}%")

df.drop(columns=["prev_service_date"]).to_csv(PROCESSED_DIR / "fact_table_enriched.csv", index=False)

# ----------------------------------------------------------------------
# 2. Failure category summary
# ----------------------------------------------------------------------
category_summary = (
    df.groupby("failure_category")
    .agg(
        failure_count=("service_id", "count"),
        avg_repair_cost=("repair_cost", "mean"),
        avg_days_in_shop=("days_in_shop", "mean"),
        repeat_repair_count=("is_repeat_repair", "sum"),
    )
    .reset_index()
)
category_summary["pct_of_total"] = 100 * category_summary["failure_count"] / len(df)
category_summary["repeat_rate_pct"] = 100 * category_summary["repeat_repair_count"] / category_summary["failure_count"]
category_summary = category_summary.sort_values("failure_count", ascending=False)
category_summary.to_csv(PROCESSED_DIR / "summary_category.csv", index=False)

# ----------------------------------------------------------------------
# 3. Mileage-band patterns
# ----------------------------------------------------------------------
mileage_band_summary = (
    df.groupby(["mileage_band", "failure_category"])
    .size()
    .reset_index(name="failure_count")
)
mileage_band_summary["mileage_band"] = pd.Categorical(
    mileage_band_summary["mileage_band"], categories=MILEAGE_BAND_ORDER, ordered=True
)
mileage_band_summary = mileage_band_summary.sort_values(["mileage_band", "failure_count"], ascending=[True, False])
mileage_band_summary.to_csv(PROCESSED_DIR / "summary_mileage_band.csv", index=False)

avg_mileage_at_failure = (
    df.groupby("failure_category")["mileage_at_service"]
    .agg(avg_mileage="mean", min_mileage="min", max_mileage="max")
    .reset_index()
    .sort_values("avg_mileage", ascending=False)
)

# ----------------------------------------------------------------------
# 4. Monthly trend / time-series analysis (12 monthly periods)
# ----------------------------------------------------------------------
monthly_trend = df.groupby("service_month").size().reset_index(name="total_services")
monthly_trend = monthly_trend.sort_values("service_month")
monthly_trend["prev_month"] = monthly_trend["total_services"].shift(1)
monthly_trend["mom_pct_change"] = 100 * (monthly_trend["total_services"] - monthly_trend["prev_month"]) / monthly_trend["prev_month"]
monthly_trend["rolling_3mo_avg"] = monthly_trend["total_services"].rolling(3, min_periods=1).mean().round(1)
monthly_trend.drop(columns=["prev_month"]).to_csv(PROCESSED_DIR / "summary_monthly_trend.csv", index=False)

monthly_by_category = (
    df.groupby(["service_month", "failure_category"])
    .size()
    .reset_index(name="failure_count")
    .sort_values(["service_month", "failure_category"])
)
monthly_by_category.to_csv(PROCESSED_DIR / "summary_monthly_by_category.csv", index=False)

# ----------------------------------------------------------------------
# 5. Model-level reliability ranking (normalized by fleet size)
# ----------------------------------------------------------------------
n_vehicles_per_model = df.groupby(["make", "model"])["vehicle_id"].nunique().reset_index(name="n_vehicles")
n_failures_per_model = df.groupby(["make", "model"]).size().reset_index(name="n_failures")
model_reliability = n_failures_per_model.merge(n_vehicles_per_model, on=["make", "model"])
model_reliability["failures_per_vehicle"] = (model_reliability["n_failures"] / model_reliability["n_vehicles"]).round(2)
model_reliability = model_reliability.sort_values("failures_per_vehicle", ascending=False)
model_reliability.to_csv(PROCESSED_DIR / "summary_model_reliability.csv", index=False)

# ----------------------------------------------------------------------
# 6. Charts
# ----------------------------------------------------------------------
plt.figure(figsize=(8, 5))
plt.bar(category_summary["failure_category"], category_summary["failure_count"], color="#2E5B88")
plt.title("Failure Count by Category")
plt.ylabel("Number of Service Events")
plt.xticks(rotation=30, ha="right")
plt.tight_layout()
plt.savefig(CHARTS_DIR / "failure_count_by_category.png", dpi=150)
plt.close()

plt.figure(figsize=(9, 5))
plt.plot(monthly_trend["service_month"], monthly_trend["total_services"], marker="o", label="Monthly Services")
plt.plot(monthly_trend["service_month"], monthly_trend["rolling_3mo_avg"], linestyle="--", label="3-mo Rolling Avg")
plt.title("Monthly Service Volume Trend (12 Months)")
plt.ylabel("Total Service Events")
plt.xticks(rotation=45, ha="right")
plt.legend()
plt.tight_layout()
plt.savefig(CHARTS_DIR / "monthly_trend.png", dpi=150)
plt.close()

pivot = mileage_band_summary.pivot_table(
    index="mileage_band", columns="failure_category", values="failure_count", fill_value=0, observed=True
).reindex(MILEAGE_BAND_ORDER)
pivot.plot(kind="bar", stacked=True, figsize=(9, 5), colormap="tab20")
plt.title("Failure Category by Mileage Band")
plt.ylabel("Number of Service Events")
plt.xticks(rotation=0)
plt.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
plt.tight_layout()
plt.savefig(CHARTS_DIR / "mileage_band_by_category.png", dpi=150)
plt.close()

# ----------------------------------------------------------------------
# 7. Console summary (the "story" of the analysis)
# ----------------------------------------------------------------------
print("\n=== KEY FINDINGS ===")
print(f"Total service records: {len(df)}")
print(f"Unique vehicles: {df['vehicle_id'].nunique()}")
print(f"Failure categories: {df['failure_category'].nunique()}")
print(f"Overall repeat-repair rate: {overall_repeat_rate:.2f}%")
print(f"Top failure category: {category_summary.iloc[0]['failure_category']} "
      f"({category_summary.iloc[0]['failure_count']} events, "
      f"{category_summary.iloc[0]['pct_of_total']:.1f}% of total)")
print(f"Category with highest repeat rate: "
      f"{category_summary.sort_values('repeat_rate_pct', ascending=False).iloc[0]['failure_category']}")
print(f"Least reliable model (failures/vehicle): "
      f"{model_reliability.iloc[0]['make']} {model_reliability.iloc[0]['model']} "
      f"({model_reliability.iloc[0]['failures_per_vehicle']} failures/vehicle)")
print("\nAll summary CSVs written to data/processed/, charts to outputs/charts/")
