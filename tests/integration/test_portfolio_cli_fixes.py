"""Two `invest-ll-portfolio` fixes: dates with an offset, and P&L from partial sales in text."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from invest_ll.cli.portfolio import _fecha, main  # pyright: ignore[reportPrivateUsage]


def test_a_date_with_an_offset_is_converted_not_relabelled() -> None:
    assert _fecha("2026-03-01T10:00:00+02:00") == datetime(2026, 3, 1, 8, 0, tzinfo=UTC)
    assert _fecha("2026-03-01T10:00:00") == datetime(2026, 3, 1, 10, 0, tzinfo=UTC)


def test_partial_sale_pnl_is_shown_in_text_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def cli(*extra: str) -> int:
        return main(["--store", str(tmp_path), *extra])

    assert cli("cash", "deposit", "--amount", "5000", "--date", "2026-01-01") == 0
    common = ("--symbol", "AAA", "--fee", "0")
    assert (
        cli("add", "buy", *common, "--quantity", "10", "--price", "100", "--date", "2026-01-02")
        == 0
    )
    assert (
        cli("add", "sell", *common, "--quantity", "4", "--price", "150", "--date", "2026-01-03")
        == 0
    )
    capsys.readouterr()

    assert cli("show") == 0
    out = capsys.readouterr().out
    assert "ventas parciales" in out
    assert "P&L realizado total" in out
    assert "200" in out
