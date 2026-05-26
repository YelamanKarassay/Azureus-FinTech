"""Purged k-fold splitter for overlapping forward-return labels."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class PurgedKFold:
    """Time-ordered k-fold CV with label-window purging and embargo."""

    n_splits: int = 5
    embargo_days: int = 5

    def split(
        self,
        sample_dates: list[dt.date],
        label_end_dates: list[dt.date],
    ) -> Iterator[tuple[list[int], list[int]]]:
        """Yield train/test index lists with no forward-label overlap."""
        if self.n_splits < 2:
            raise ValueError("n_splits must be at least 2")
        if len(sample_dates) != len(label_end_dates):
            raise ValueError("sample_dates and label_end_dates must be the same length")
        n_samples = len(sample_dates)
        if n_samples < self.n_splits:
            return

        order = sorted(range(n_samples), key=lambda idx: (sample_dates[idx], idx))
        folds = _folds(order, self.n_splits)
        for test_idx in folds:
            if not test_idx:
                continue
            test_start = min(sample_dates[idx] for idx in test_idx)
            test_end = max(sample_dates[idx] for idx in test_idx)
            embargo_start = test_start - dt.timedelta(days=self.embargo_days)
            embargo_end = test_end + dt.timedelta(days=self.embargo_days)
            test_set = set(test_idx)
            train_idx = [
                idx
                for idx in order
                if idx not in test_set
                and not _overlaps(
                    sample_dates[idx],
                    label_end_dates[idx],
                    embargo_start,
                    embargo_end,
                )
            ]
            yield train_idx, test_idx


def _folds(indices: list[int], n_splits: int) -> list[list[int]]:
    n = len(indices)
    base = n // n_splits
    remainder = n % n_splits
    folds: list[list[int]] = []
    start = 0
    for fold in range(n_splits):
        size = base + (1 if fold < remainder else 0)
        folds.append(indices[start : start + size])
        start += size
    return folds


def _overlaps(
    label_start: dt.date,
    label_end: dt.date,
    test_start: dt.date,
    test_end: dt.date,
) -> bool:
    return label_start <= test_end and label_end >= test_start
