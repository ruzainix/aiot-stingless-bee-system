"""
NESTR Hive Weight Forecasting Module

Purpose:
- Demonstrates a lightweight Linear Regression model.
- Forecasts hive weight trend using day-based prototype readings.
- Estimates when the hive may reach a prototype harvest threshold.

Important:
- This is a prototype-level model for academic demonstration.
- Real agricultural decisions require longer real-world data collection.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Tuple

import pandas as pd
from sklearn.linear_model import LinearRegression

HARVEST_THRESHOLD_KG = 8.0
DEFAULT_CSV = Path(__file__).with_name("sample_hive_readings.csv")


def load_data(csv_path: Path = DEFAULT_CSV) -> pd.DataFrame:
    """Load hive weight readings from CSV or create fallback data."""
    if csv_path.exists():
        try:
            data = pd.read_csv(csv_path)
        except (pd.errors.EmptyDataError, pd.errors.ParserError, OSError) as exc:
            raise ValueError(f"Could not read readings from {csv_path}: {exc}") from exc
    else:
        data = pd.DataFrame({
            "day": list(range(1, 15)),
            "weight_kg": [5.20, 5.35, 5.48, 5.62, 5.77, 5.94, 6.08, 6.24, 6.41, 6.55, 6.73, 6.91, 7.06, 7.20],
        })

    required = {"day", "weight_kg"}
    if not required.issubset(data.columns):
        raise ValueError("CSV must contain 'day' and 'weight_kg' columns")

    if data.empty:
        raise ValueError("No hive readings available to train the model")

    return data


def train_model(data: pd.DataFrame) -> LinearRegression:
    """Train Linear Regression model using day as input and hive weight as output."""
    x = data[["day"]]
    y = data["weight_kg"]
    model = LinearRegression()
    model.fit(x, y)
    return model


def forecast_next_days(model: LinearRegression, start_day: int, days: int = 7) -> pd.DataFrame:
    """Forecast hive weight for the next selected number of days."""
    future_days = pd.DataFrame({"day": list(range(start_day, start_day + days))})
    predictions = model.predict(future_days[["day"]])
    future_days["predicted_weight_kg"] = predictions.round(2)
    future_days["harvest_ready"] = future_days["predicted_weight_kg"] >= HARVEST_THRESHOLD_KG
    return future_days


def estimate_harvest_day(model: LinearRegression, latest_day: int, max_future_days: int = 60) -> Tuple[int | None, float | None]:
    """Estimate the day when predicted weight reaches the harvest threshold."""
    for day in range(latest_day + 1, latest_day + max_future_days + 1):
        predicted_weight = float(model.predict(pd.DataFrame({"day": [day]}))[0])
        if predicted_weight >= HARVEST_THRESHOLD_KG:
            return day, round(predicted_weight, 2)
    return None, None


def main() -> None:
    try:
        data = load_data()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)

    model = train_model(data)

    latest_day = int(data["day"].max())
    next_day = latest_day + 1

    forecast = forecast_next_days(model, start_day=next_day, days=7)
    harvest_day, predicted_weight = estimate_harvest_day(model, latest_day=latest_day)

    print("===== NESTR Hive Weight Forecast =====")
    print(forecast.to_string(index=False))
    print()

    if harvest_day is not None:
        print(f"Estimated harvest threshold day: Day {harvest_day}")
        print(f"Predicted weight on that day: {predicted_weight} kg")
    else:
        print("Harvest threshold was not reached within the forecast window.")

    print("\nPrototype note: Prediction must be validated with real hive data before field decision-making.")


if __name__ == "__main__":
    main()
