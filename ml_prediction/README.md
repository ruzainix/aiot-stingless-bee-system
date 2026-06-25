# NESTR ML Prediction Module

This module demonstrates Linear Regression-based hive weight forecasting.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python hive_weight_forecast.py
```

## Input Data Format

The default script uses simulated prototype readings. To use real data, create a CSV file with:

```csv
day,weight_kg
1,5.20
2,5.35
3,5.50
```

Then update the script to load the CSV file.

## Prototype Reminder

The prediction result is for demonstration only. A production-level model requires larger real-world datasets from multiple hives and field validation.
