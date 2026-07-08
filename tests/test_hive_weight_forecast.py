"""Unit tests for the NESTR hive weight forecasting module."""

import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression

import hive_weight_forecast as hwf


@pytest.fixture()
def linear_model():
    """A LinearRegression trained on a simple, perfectly linear series."""
    data = pd.DataFrame({"day": range(1, 11), "weight_kg": [float(d) for d in range(1, 11)]})
    return hwf.train_model(data)


class TestLoadData:
    def test_loads_default_csv(self):
        data = hwf.load_data()
        assert {"day", "weight_kg"}.issubset(data.columns)
        assert len(data) > 0

    def test_falls_back_to_builtin_data_when_missing(self, tmp_path):
        missing = tmp_path / "does_not_exist.csv"
        data = hwf.load_data(missing)
        assert list(data["day"]) == list(range(1, 15))
        assert len(data) == 14
        assert {"day", "weight_kg"}.issubset(data.columns)

    def test_reads_provided_csv(self, tmp_path):
        csv_path = tmp_path / "readings.csv"
        csv_path.write_text("day,weight_kg\n1,5.0\n2,6.0\n")
        data = hwf.load_data(csv_path)
        assert list(data["day"]) == [1, 2]
        assert list(data["weight_kg"]) == [5.0, 6.0]

    def test_raises_when_required_columns_missing(self, tmp_path):
        csv_path = tmp_path / "bad.csv"
        csv_path.write_text("day,mass\n1,5.0\n")
        with pytest.raises(ValueError, match="day.*weight_kg"):
            hwf.load_data(csv_path)


class TestTrainModel:
    def test_returns_fitted_linear_regression(self):
        data = pd.DataFrame({"day": [1, 2, 3, 4], "weight_kg": [2.0, 4.0, 6.0, 8.0]})
        model = hwf.train_model(data)
        assert isinstance(model, LinearRegression)
        # y = 2x, so slope ~ 2 and intercept ~ 0.
        assert model.coef_[0] == pytest.approx(2.0)
        assert model.intercept_ == pytest.approx(0.0, abs=1e-9)

    def test_predicts_known_value(self, linear_model):
        prediction = float(linear_model.predict(pd.DataFrame({"day": [20]}))[0])
        assert prediction == pytest.approx(20.0)


class TestForecastNextDays:
    def test_shape_and_columns(self, linear_model):
        forecast = hwf.forecast_next_days(linear_model, start_day=11, days=7)
        assert list(forecast["day"]) == list(range(11, 18))
        assert set(forecast.columns) == {"day", "predicted_weight_kg", "harvest_ready"}
        assert len(forecast) == 7

    def test_default_days_is_seven(self, linear_model):
        forecast = hwf.forecast_next_days(linear_model, start_day=1)
        assert len(forecast) == 7

    def test_harvest_ready_flag_matches_threshold(self, linear_model):
        # Model is y = day, threshold is 8.0, so days >= 8 are harvest ready.
        forecast = hwf.forecast_next_days(linear_model, start_day=6, days=5)
        ready = dict(zip(forecast["day"], forecast["harvest_ready"]))
        assert ready[7] is False or not ready[7]
        assert bool(ready[8]) is True
        assert bool(ready[10]) is True

    def test_predictions_are_rounded(self, linear_model):
        forecast = hwf.forecast_next_days(linear_model, start_day=1, days=3)
        for value in forecast["predicted_weight_kg"]:
            assert round(value, 2) == value


class TestEstimateHarvestDay:
    def test_returns_first_day_reaching_threshold(self, linear_model):
        # y = day, threshold 8.0 -> first day >= 8 is day 8.
        day, weight = hwf.estimate_harvest_day(linear_model, latest_day=5)
        assert day == 8
        assert weight == pytest.approx(8.0)

    def test_returns_none_when_threshold_never_reached(self):
        flat = pd.DataFrame({"day": [1, 2, 3], "weight_kg": [1.0, 1.0, 1.0]})
        model = hwf.train_model(flat)
        day, weight = hwf.estimate_harvest_day(model, latest_day=3, max_future_days=10)
        assert day is None
        assert weight is None

    def test_respects_max_future_days_window(self, linear_model):
        # Threshold reached at day 8, but window only extends to day 7.
        day, weight = hwf.estimate_harvest_day(linear_model, latest_day=5, max_future_days=2)
        assert day is None
        assert weight is None


def test_main_runs_and_prints(capsys):
    hwf.main()
    captured = capsys.readouterr()
    assert "NESTR Hive Weight Forecast" in captured.out
