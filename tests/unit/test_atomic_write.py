"""A data file is replaced in one step: readers see the old one or the new one, never half."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from invest_ll.fetch import atomic_write
from invest_ll.fetch.atomic_write import replace_atomically

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path


def test_the_new_content_lands_and_no_temporary_is_left(tmp_path: Path) -> None:
    destination = tmp_path / "klines_1d.parquet"
    destination.write_text("old", encoding="utf-8")

    replace_atomically(destination, lambda p: p.write_text("new", encoding="utf-8"))

    assert destination.read_text(encoding="utf-8") == "new"
    assert [p.name for p in tmp_path.iterdir()] == ["klines_1d.parquet"]


def test_a_write_that_fails_halfway_leaves_the_old_file_intact(tmp_path: Path) -> None:
    destination = tmp_path / "klines_1d.parquet"
    destination.write_text("old", encoding="utf-8")

    def half_and_crash(p: Path) -> None:
        p.write_text("ne", encoding="utf-8")
        raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        replace_atomically(destination, half_and_crash)

    assert destination.read_text(encoding="utf-8") == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["klines_1d.parquet"]


def test_a_file_held_open_elsewhere_is_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On Windows a file another reader has open cannot be replaced for a moment."""
    destination = tmp_path / "etf_1d.parquet"
    original_replace = type(destination).replace
    refusals = [PermissionError("in use"), PermissionError("in use")]

    def busy_then_free(self: Path, target: Path) -> Path:
        if refusals:
            raise refusals.pop()
        return original_replace(self, target)

    monkeypatch.setattr(type(destination), "replace", busy_then_free)
    replace_atomically(destination, lambda p: p.write_text("new", encoding="utf-8"), pause=0.0)
    assert destination.read_text(encoding="utf-8") == "new"
    assert atomic_write.ATTEMPTS > 2
