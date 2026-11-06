"""Statistical / ML models. Everything is fitted on REFERENCE data; thresholds are tuned on reference
'tune' batches only (never on the held-out evaluation batches)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from common import SEED, km, parse_dt

TARGET_FA = 0.001   # we tune row-level thresholds so ~0.1% of clean tune rows would alert


def _q(scores: np.ndarray, q: float = 1 - TARGET_FA) -> float:
    s = np.asarray(scores, float)
    s = s[~np.isnan(s)]
    return float(np.quantile(s, q)) if len(s) else float("inf")


def _iso_scores(model: IsolationForest, X: np.ndarray, ok: np.ndarray) -> np.ndarray:
    out = np.full(len(X), np.nan)
    if ok.any():
        out[ok] = -model.score_samples(X[ok])   # higher = more anomalous
    return out


def duration_X(df: pd.DataFrame):
    created, closed = parse_dt(df.created_date), parse_dt(df.closed_date)
    h = ((closed - created).dt.total_seconds() / 3600).to_numpy()
    X = np.c_[np.sign(h) * np.log1p(np.abs(h)), created.dt.hour.to_numpy()]
    return X, ~np.isnan(X).any(axis=1)


def latlon_X(df: pd.DataFrame):
    X = np.c_[pd.to_numeric(df.latitude, errors="coerce"), pd.to_numeric(df.longitude, errors="coerce")]
    return X, ~np.isnan(X).any(axis=1)


def pii_X(texts: pd.Series) -> np.ndarray:
    t = texts.fillna("").astype(str)
    n = t.str.len().clip(lower=1)
    digits, caps = t.str.count(r"\d"), t.str.count(r"\b[A-Z][a-z]+\b")
    return np.c_[digits / n, digits, t.str.contains("@").astype(int),
                 t.str.contains(r"\bat\b.*\bdot\b").astype(int), caps / n, caps, n]


def null_spike_cells(df: pd.DataFrame, agency_rate: pd.DataFrame, global_rate: pd.Series, min_n: int = 20):
    """z-test per (agency, column): is the null share higher than in the reference? Returns list of dicts."""
    cells = []
    for col in df.columns:
        if col == "agency" or col not in global_rate.index:
            continue
        g = df[col].isna().groupby(df["agency"]).agg(["sum", "size"])
        for agency, (k, n) in g.iterrows():
            if n < min_n:
                continue
            p0 = agency_rate.at[agency, col] if agency in agency_rate.index else global_rate[col]
            p0 = min(max(float(p0), 0.005), 0.995)
            z = (k / n - p0) / np.sqrt(p0 * (1 - p0) / n)
            cells.append({"agency": agency, "column": col, "n": int(n), "k": int(k), "p0": p0, "z": float(z),
                          "share": float(k / n)})
    return cells


class StatsModels:
    def __init__(self) -> None:
        self.thr: dict[str, float] = {}

    def fit(self, train: pd.DataFrame, tune_batches: list[pd.DataFrame]) -> StatsModels:
        tune = pd.concat(tune_batches, ignore_index=True)
        samp = train.sample(min(len(train), 50_000), random_state=SEED)

        # closed-before-created: isolation forest on [signed log duration, hour of day]
        X, ok = duration_X(samp)
        self.dur = IsolationForest(n_estimators=100, random_state=SEED).fit(X[ok])
        self.thr["duration"] = _q(self.score_duration(tune))

        # lat/long swap: isolation forest on (lat, lon)
        X, ok = latlon_X(samp)
        self.geo = IsolationForest(n_estimators=100, random_state=SEED).fit(X[ok])
        self.thr["latlon"] = _q(self.score_latlon(tune))

        # ZIP vs borough: distance from the row's lat/long to the median lat/long of its ZIP
        self.zip_xy = train.groupby("incident_zip")[["latitude", "longitude"]].median()
        self.thr["zip_dist"] = _q(self.score_zip(tune))

        # complaint_type vs descriptor: TF-IDF + logistic regression predicts complaint_type from descriptor
        g = train.groupby(["descriptor", "complaint_type"]).size().reset_index(name="n")
        self.desc_vec = TfidfVectorizer(ngram_range=(1, 2))
        self.desc_lr = LogisticRegression(max_iter=300).fit(self.desc_vec.fit_transform(g.descriptor),
                                                            g.complaint_type, sample_weight=g.n)
        self.thr["desc"] = _q(self.score_desc(tune))

        # resolution text vs status: TF-IDF + logistic regression predicts Closed / not Closed from the text
        r = train.dropna(subset=["resolution_description"])
        r = r.assign(closed=r.status.eq("Closed")).groupby(["resolution_description", "closed"]).size()
        r = r.reset_index(name="n").sample(frac=1, random_state=SEED).head(40_000)
        self.res_vec = TfidfVectorizer(ngram_range=(1, 2), max_features=20_000)
        self.res_lr = LogisticRegression(max_iter=300).fit(self.res_vec.fit_transform(r.resolution_description),
                                                           r.closed, sample_weight=r.n)
        self.thr["res"] = _q(self.score_res(tune))

        # PII: isolation forest on simple text features of resolution_description
        texts = samp.resolution_description.dropna()
        self.pii = IsolationForest(n_estimators=100, random_state=SEED).fit(pii_X(texts))
        self.thr["pii"] = _q(self.score_pii(tune))

        # null spikes: reference null rates per agency; z threshold = max z seen on tune batches (+10%)
        self.agency_rate = train.isna().groupby(train["agency"]).mean()
        self.global_rate = train.isna().mean()
        worst = max((max([c["z"] for c in null_spike_cells(b, self.agency_rate, self.global_rate)] or [0])
                     for b in tune_batches), default=0)
        self.thr["null_z"] = max(5.0, 1.1 * worst)

        # date format: how common is each 'shape' of created_date (2023-01-05T01:02:03 -> dddd-dd-ddTdd:dd:dd)
        shapes = train.created_date.dt.strftime("%Y-%m-%dT%H:%M:%S").str.replace(r"\d", "d", regex=True)
        self.shape_freq = shapes.value_counts(normalize=True).to_dict()

        # type share per column (python type names), for the 'type entropy' check
        head = train.head(5000)
        self.type_share = {c: head[c].dropna().map(lambda v: type(v).__name__).value_counts(normalize=True).to_dict()
                           for c in head.columns}
        self.col_profile = {c: self.profile(head[c]) for c in head.columns}
        return self

    @staticmethod
    def profile(s: pd.Series) -> tuple[float, float]:
        return float(s.isna().mean()), float(s.dropna().astype(str).str.len().mean() or 0.0)

    # ---- row scores (higher = more suspicious, NaN = cannot judge) ----
    def score_duration(self, df):
        X, ok = duration_X(df)
        return _iso_scores(self.dur, X, ok)

    def score_latlon(self, df):
        X, ok = latlon_X(df)
        return _iso_scores(self.geo, X, ok)

    def score_zip(self, df):
        c = self.zip_xy.reindex(df.incident_zip)
        lat, lon = pd.to_numeric(df.latitude, errors="coerce"), pd.to_numeric(df.longitude, errors="coerce")
        return km(lat.to_numpy(), lon.to_numpy(), c.latitude.to_numpy(), c.longitude.to_numpy())

    def score_desc(self, df):
        d = df.descriptor.fillna("").astype(str)
        uniq = d.unique()
        proba = self.desc_lr.predict_proba(self.desc_vec.transform(uniq))
        pos, cls = {u: i for i, u in enumerate(uniq)}, {c: i for i, c in enumerate(self.desc_lr.classes_)}
        out = np.ones(len(df))                    # unseen complaint type -> maximally suspicious
        for r, (u, t) in enumerate(zip(d, df.complaint_type)):
            if t in cls:
                out[r] = 1 - proba[pos[u], cls[t]]
        return out

    def score_res(self, df):
        text = df.resolution_description
        out = np.full(len(df), np.nan)
        ok = text.notna().to_numpy()
        if ok.any():
            p_closed = self.res_lr.predict_proba(self.res_vec.transform(text[ok].astype(str)))[:, 1]
            closed = df.status.eq("Closed").to_numpy()[ok]
            out[ok] = np.where(closed, 1 - p_closed, p_closed)
        return out

    def score_pii(self, df):
        ok = df.resolution_description.notna().to_numpy()
        X = pii_X(df.resolution_description)
        return _iso_scores(self.pii, X, ok)
