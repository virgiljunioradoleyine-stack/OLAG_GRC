"""
Chronological splitting.

A random split on a time series is a data-leakage machine: neighbouring
observations are correlated, so a shuffled test set is effectively memorised
from its neighbours in training. Every split here is by date, in order, and the
test period is never touched until final evaluation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from ..config import TRAIN_END, VALIDATION_END


@dataclass
class SplitSpec:
    train_end: str
    validation_end: str

    def describe(self):
        return (f"train <= {self.train_end}; "
                f"validation {self.train_end} < t <= {self.validation_end}; "
                f"test > {self.validation_end}")


DEFAULT_SPLIT = SplitSpec(TRAIN_END, VALIDATION_END)


def chronological_split(df, spec=DEFAULT_SPLIT, date_col="date"):
    """Return (train_idx, val_idx, test_idx) as boolean masks.

    Raises if the split would leave the training period empty, because a model
    fitted on nothing is worse than no model: it would still produce numbers.
    """
    d = pd.to_datetime(df[date_col])
    train_end = pd.Timestamp(spec.train_end)
    val_end = pd.Timestamp(spec.validation_end)

    train = d <= train_end
    val = (d > train_end) & (d <= val_end)
    test = d > val_end

    if not train.any():
        raise ValueError(
            f"chronological split leaves no training data "
            f"(earliest observation {d.min()}, train_end {spec.train_end})")
    return train.to_numpy(), val.to_numpy(), test.to_numpy()


def split_summary(df, spec=DEFAULT_SPLIT, date_col="date"):
    tr, va, te = chronological_split(df, spec, date_col)
    d = pd.to_datetime(df[date_col])

    def rng(mask):
        if not mask.any():
            return None
        return f"{d[mask].min().date()} .. {d[mask].max().date()}"

    return {
        "spec": spec.describe(),
        "train": {"n": int(tr.sum()), "range": rng(tr)},
        "validation": {"n": int(va.sum()), "range": rng(va)},
        "test": {"n": int(te.sum()), "range": rng(te)},
    }
