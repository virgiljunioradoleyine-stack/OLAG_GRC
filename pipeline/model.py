"""
STEP 2 — the AI: an Isolation Forest per monitoring point.

Isolation Forest is unsupervised: it learns what NDTI readings look like at a
given point across seasons, and scores how easy each new reading is to isolate
from that normal. We never had to label pollution events, which matters because
nobody has a labelled record of galamsey spikes on the Pra.

The 7 features are deliberately chosen so an anomaly means "this river changed
in a way rainfall does not explain":

  ndti            how turbid the water is right now
  ndti_delta      how sharply it changed since the last observation
  ndti_7d_mean    short-term baseline
  ndti_30d_mean   longer baseline -- separates a spike from a drift
  month           season, so the harmattan/rainy cycle is normal, not anomalous
  control_ndti    turbidity upstream, away from the mining
  control_delta   how sharply upstream changed

The last two carry the control logic into the model itself. When it rains, every
point rises together, so a high `ndti` alongside a high `control_ndti` is a
combination the model has seen many times and scores as normal. A rise at the
monitored point *without* the upstream rise is the rare combination -- and that
is the shape of a pollution event rather than weather.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

FEATURES = ["ndti", "ndti_delta", "ndti_7d_mean", "ndti_30d_mean",
            "month", "control_ndti", "control_delta",
            "red", "red_delta", "control_red"]

MODEL_DIR = "models"
READINGS_DIR = "data/readings"
N_ESTIMATORS = 200
RANDOM_STATE = 42


def load_readings(point_id, readings_dir=READINGS_DIR):
    df = pd.read_csv(os.path.join(readings_dir, f"{point_id}.csv"))
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _rolling_mean(dates, values, days):
    """Time-window mean, inclusive of the current reading.

    Observations are irregular -- cloud decides when we get one -- so a
    fixed row-count window would span wildly different amounts of time. This
    windows by actual date.
    """
    d = dates.values.astype("datetime64[D]").astype(int)
    out = np.empty(len(values))
    for i in range(len(values)):
        m = (d <= d[i]) & (d > d[i] - days)
        out[i] = values[m].mean()
    return out


def _match_control(dates, control_df, max_days=10, column="ndti"):
    """Nearest-date control value for each row; NaN if none is close enough.

    The control is matched on a *smoothed* series rather than the single nearest
    reading. A single reading carries roughly the noise of any other -- see
    TEST_RESULTS.md section 6 -- so comparing one noisy number against another
    was asking the model to find a rainfall signal in two independent errors.
    A 30-day mean averages that down before the comparison happens.
    """
    if control_df is None or control_df.empty:
        return np.full(len(dates), np.nan), np.full(len(dates), np.nan)
    cd = control_df["date"].values.astype("datetime64[D]").astype(int)
    raw = control_df[column].to_numpy(dtype=float)
    smooth = _rolling_mean(control_df["date"], raw, 30)
    cdelta = np.concatenate([[np.nan], np.diff(smooth)])
    d = dates.values.astype("datetime64[D]").astype(int)

    value = np.full(len(d), np.nan)
    delta = np.full(len(d), np.nan)
    for i, day in enumerate(d):
        j = int(np.argmin(np.abs(cd - day)))
        if abs(cd[j] - day) <= max_days:
            value[i] = smooth[j]
            delta[i] = cdelta[j]
    return value, delta


def build_features(df, control_df):
    """Return a DataFrame of the 7 features, aligned to df's rows."""
    v = df["ndti"].to_numpy()
    f = pd.DataFrame(index=df.index)
    f["ndti"] = v
    f["ndti_delta"] = np.concatenate([[0.0], np.diff(v)])
    f["ndti_7d_mean"] = _rolling_mean(df["date"], v, 7)
    f["ndti_30d_mean"] = _rolling_mean(df["date"], v, 30)
    f["month"] = df["date"].dt.month.to_numpy()
    c_ndti, c_delta = _match_control(df["date"], control_df, column="ndti")
    f["control_ndti"] = c_ndti
    f["control_delta"] = np.nan_to_num(c_delta, nan=0.0)

    # Absolute red reflectance, alongside the normalised index. NDTI cancels a
    # uniform brightening, which is exactly what a heavy sediment load produces:
    # on the one documented pollution event red nearly doubled while NDTI moved
    # the wrong way (TEST_RESULTS.md section 1a). Neither index is sufficient
    # alone -- red also rises with atmospheric haze, which is why NDTI was chosen
    # first -- so the model gets both and the control rejects the common-mode part.
    if "red" in df.columns:
        r = pd.to_numeric(df["red"], errors="coerce").to_numpy(dtype=float)
    else:
        r = np.full(len(df), np.nan)
    f["red"] = r
    f["red_delta"] = np.concatenate([[0.0], np.diff(r)])
    if control_df is not None and "red" in control_df.columns:
        c_red, _ = _match_control(df["date"], control_df, column="red")
    else:
        c_red = np.full(len(df), np.nan)
    f["control_red"] = c_red
    # a reading with no red value falls back to this point's own level, so the
    # pair looks unremarkable rather than inventing a signal
    for col, fallback in (("red", np.nanmedian(r) if np.isfinite(r).any() else 0.0),
                          ("control_red", None)):
        if col == "control_red":
            f[col] = np.where(np.isnan(f[col]), f["red"], f[col])
        else:
            f[col] = np.where(np.isnan(f[col]), fallback, f[col])
    f["red_delta"] = np.nan_to_num(f["red_delta"].to_numpy(dtype=float), nan=0.0)
    # a missing control reading falls back to this point's own baseline, which
    # makes the pair look ordinary rather than fabricating a suppression signal
    f["control_ndti"] = np.where(np.isnan(f["control_ndti"]),
                                 f["ndti_30d_mean"], f["control_ndti"])
    return f[FEATURES]


@dataclass
class PointModel:
    point_id: str
    scaler: StandardScaler
    forest: IsolationForest
    features: list
    n_samples: int
    contamination: float
    train_scores: np.ndarray = None   # score distribution seen during training

    def percentile_of(self, score):
        """Where a score falls in the training distribution, 0-100.

        Raw Isolation Forest scores are not comparable between points -- each
        forest is fitted to its own river. Expressing a score as a percentile of
        that point's own training distribution makes alert thresholds mean the
        same thing everywhere.
        """
        if self.train_scores is None or len(self.train_scores) == 0:
            return float("nan")
        return float((self.train_scores < score).mean() * 100.0)

    def score(self, feature_row):
        """Score one reading. Accepts a sequence or a mapping of features.

        The row is rebuilt as a one-row DataFrame with the training column names
        so the scaler sees the same schema it was fitted on -- passing a bare
        array works but relies on positional order silently matching, which is
        exactly the kind of coupling that breaks quietly when a feature is added.
        """
        if isinstance(feature_row, dict):
            values = [feature_row[f] for f in self.features]
        else:
            values = list(feature_row)
        row = pd.DataFrame([values], columns=self.features, dtype=float)
        x = self.scaler.transform(row)
        return int(self.forest.predict(x)[0]), float(self.forest.score_samples(x)[0])


def train(point_id, contamination=0.05, readings_dir=READINGS_DIR):
    df = load_readings(point_id, readings_dir)
    control = load_readings("control", readings_dir)
    X = build_features(df, control)
    scaler = StandardScaler().fit(X)
    forest = IsolationForest(
        n_estimators=N_ESTIMATORS,
        contamination=contamination,
        random_state=RANDOM_STATE,
    ).fit(scaler.transform(X))
    train_scores = forest.score_samples(scaler.transform(X))
    model = PointModel(point_id, scaler, forest, list(FEATURES), len(df),
                       contamination, train_scores)
    return model, df, X


def save(model, model_dir=MODEL_DIR):
    os.makedirs(model_dir, exist_ok=True)
    path = os.path.join(model_dir, f"{model.point_id}.pkl")
    joblib.dump(model, path)
    return path


def load(point_id, model_dir=MODEL_DIR):
    return joblib.load(os.path.join(model_dir, f"{point_id}.pkl"))


def predict(point_id, new_reading, control_reading, model_dir=MODEL_DIR):
    """Score one new reading.

    `new_reading` and `control_reading` are dicts carrying at least the keys the
    feature set needs. Returns (prediction, anomaly_score) where prediction is
    -1 for anomaly and 1 for normal, and a lower score is more anomalous.
    """
    m = load(point_id, model_dir)
    row = [
        new_reading["ndti"],
        new_reading.get("ndti_delta", 0.0),
        new_reading.get("ndti_7d_mean", new_reading["ndti"]),
        new_reading.get("ndti_30d_mean", new_reading["ndti"]),
        new_reading["month"],
        control_reading.get("ndti", new_reading["ndti"]),
        control_reading.get("ndti_delta", 0.0),
    ]
    return m.score(row)
