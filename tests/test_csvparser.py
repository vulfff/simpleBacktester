"""Tests for csvparser.py — CSV tick data feed."""
import os
import tempfile
import pytest
from csvparser import CSVTickDataFeed


def _write_csv(rows: list[str]) -> str:
    """Write CSV lines to a temp file, return path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
    f.write("\n".join(rows))
    f.close()
    return f.name


class TestCSVTickDataFeed:
    def test_basic_ohlcv(self):
        path = _write_csv([
            "timestamp,open,high,low,close,volume,symbol",
            "2024-01-01 00:00:00,99,101,98,100,1000,AAPL",
            "2024-01-02 00:00:00,100,105,99,104,1500,AAPL",
        ])
        try:
            feed = CSVTickDataFeed(file_path=path)
            ticks = list(feed)
            assert len(ticks) == 2
            assert ticks[0].close == 100.0
            assert ticks[0].open == 99.0
            assert ticks[0].high == 101.0
            assert ticks[0].low == 98.0
            assert ticks[0].volume == 1000.0
            assert ticks[1].close == 104.0
        finally:
            os.remove(path)

    def test_symbol_override(self):
        path = _write_csv([
            "timestamp,close",
            "2024-01-01,50.0",
        ])
        try:
            feed = CSVTickDataFeed(file_path=path, symbol="MSFT")
            ticks = list(feed)
            assert len(ticks) == 1
            assert ticks[0].name == "MSFT"
        finally:
            os.remove(path)

    def test_column_aliases(self):
        """Columns named 'Date' and 'Close' should be auto-detected."""
        path = _write_csv([
            "Date,Close,Volume",
            "2024-01-01,100,500",
        ])
        try:
            ticks = list(CSVTickDataFeed(file_path=path))
            assert len(ticks) == 1
            assert ticks[0].close == 100.0
        finally:
            os.remove(path)

    def test_missing_close_column_raises(self):
        path = _write_csv([
            "date,value",
            "2024-01-01,100",
        ])
        try:
            with pytest.raises(ValueError, match="price/close column"):
                list(CSVTickDataFeed(file_path=path))
        finally:
            os.remove(path)

    def test_skips_bad_rows(self):
        path = _write_csv([
            "timestamp,close",
            "2024-01-01,100",
            "2024-01-02,not_a_number",
            "2024-01-03,200",
        ])
        try:
            ticks = list(CSVTickDataFeed(file_path=path))
            assert len(ticks) == 2
            assert ticks[0].close == 100.0
            assert ticks[1].close == 200.0
        finally:
            os.remove(path)

    def test_high_low_default_to_close(self):
        """When high/low columns are absent, they default to close."""
        path = _write_csv([
            "timestamp,close",
            "2024-01-01,100",
        ])
        try:
            ticks = list(CSVTickDataFeed(file_path=path))
            assert ticks[0].high == 100.0
            assert ticks[0].low == 100.0
        finally:
            os.remove(path)

    def test_custom_column_map(self):
        path = _write_csv([
            "dt,px,vol",
            "2024-01-01,55.5,100",
        ])
        try:
            feed = CSVTickDataFeed(file_path=path, column_map={"time": "dt", "close": "px", "volume": "vol"})
            ticks = list(feed)
            assert len(ticks) == 1
            assert ticks[0].close == 55.5
        finally:
            os.remove(path)
