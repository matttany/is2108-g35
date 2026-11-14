"""Run from Delaundry: python -m ml.train_model"""
import csv
import json
from datetime import datetime
from importlib.metadata import version
from statistics import mean

import joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline

from .features import FEATURE_COLUMNS, ML_DIR, read_feature_row


def train_model():
  data_path = ML_DIR / "data" / "synthetic_demand.csv"
  with data_path.open(encoding="utf-8", newline="") as file:
    data = list(csv.DictReader(file))
  cutoff = datetime.fromisoformat("2026-09-01T00:00:00+08:00")
  # Training targets must already be observable before the first evaluation forecast.
  train = [row for row in data if datetime.fromisoformat(row["pickup_at"]) < cutoff]
  evaluation = [row for row in data if datetime.fromisoformat(row["forecast_at"]) >= cutoff]
  if not train or not evaluation:
    raise ValueError("Both temporal partitions must contain forecasts.")

  train_features = [read_feature_row(row) for row in train]
  train_targets = [int(row["new_requests"]) for row in train]
  evaluation_features = [read_feature_row(row) for row in evaluation]
  evaluation_targets = [int(row["new_requests"]) for row in evaluation]
  model = Pipeline([
    # DictVectorizer one-hot encodes hall names and passes through numeric features.
    ("features", DictVectorizer(sparse=False)),
    ("regressor", RandomForestRegressor(
      n_estimators=100, max_depth=12, min_samples_leaf=4, random_state=42, n_jobs=1,
    )),
  ])
  model.fit(train_features, train_targets)
  predictions = model.predict(evaluation_features)

  # Historical-average baseline uses training targets only, grouped by hall and pickup hour.
  groups = {}
  for row in train:
    groups.setdefault((row["residence"], row["pickup_hour"]), []).append(int(row["new_requests"]))
  means = {key: mean(values) for key, values in groups.items()}
  overall_mean = mean(train_targets)
  baseline = [means.get((row["residence"], row["pickup_hour"]), overall_mean) for row in evaluation]
  metrics = {
    "data_source": "Synthetic demonstration data; not validated on real demand.",
    "target": "New requests arriving between forecast_at and pickup_at for this hall/window",
    "cutoff": cutoff.isoformat(),
    "training_rows": len(train), "evaluation_rows": len(evaluation),
    "excluded_boundary_rows": len(data) - len(train) - len(evaluation),
    "last_training_pickup": max(row["pickup_at"] for row in train),
    "first_evaluation_forecast": min(row["forecast_at"] for row in evaluation),
    "random_forest_mae": float(mean_absolute_error(evaluation_targets, predictions)),
    "historical_average_mae": float(mean_absolute_error(evaluation_targets, baseline)),
    "features": FEATURE_COLUMNS,
    "versions": {name: version(name) for name in ["scikit-learn", "numpy", "joblib"]},
    "random_seed": 42,
  }
  artifacts = ML_DIR / "artifacts"
  artifacts.mkdir(exist_ok=True)
  # Save the same fitted pipeline that was evaluated, including its encoder.
  joblib.dump(model, artifacts / "demand_model.joblib", compress=3)
  (artifacts / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
  print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
  train_model()
