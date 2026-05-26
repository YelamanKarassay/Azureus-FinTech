"""Purged k-fold splitter tests."""

from __future__ import annotations

import datetime as dt

from azureus.models.cv.purged_kfold import PurgedKFold


def test_purged_kfold_purges_label_overlap_and_embargo() -> None:
    sample_dates = [dt.date(2024, 1, 1) + dt.timedelta(days=i) for i in range(20)]
    label_end_dates = [date + dt.timedelta(days=4) for date in sample_dates]
    splitter = PurgedKFold(n_splits=4, embargo_days=2)

    for train_idx, test_idx in splitter.split(sample_dates, label_end_dates):
        test_start = min(sample_dates[idx] for idx in test_idx)
        test_end = max(sample_dates[idx] for idx in test_idx)
        embargo_start = test_start - dt.timedelta(days=2)
        embargo_end = test_end + dt.timedelta(days=2)

        assert set(train_idx).isdisjoint(test_idx)
        for idx in train_idx:
            assert label_end_dates[idx] < embargo_start or sample_dates[idx] > embargo_end


def test_purged_kfold_is_deterministic() -> None:
    sample_dates = [dt.date(2024, 1, 1) + dt.timedelta(days=i) for i in range(12)]
    label_end_dates = [date + dt.timedelta(days=1) for date in sample_dates]
    splitter = PurgedKFold(n_splits=3, embargo_days=1)

    first = list(splitter.split(sample_dates, label_end_dates))
    second = list(splitter.split(sample_dates, label_end_dates))

    assert first == second
