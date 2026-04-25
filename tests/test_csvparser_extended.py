"""
test_csvparser_extended.py — Extended CSV parser tests:
column aliases, timestamp formats, bad data, OHLC regression guard.
"""
import math
import pytest
from datetime import datetime

from csvparser import CSVTickDataFeed
from strategy_rules import PriceSeries, ATROperand, HighestHighOperand, PriceField


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _feed_from_text(text, tmp_path, filename="test.csv"):
    p = tmp_path / filename
    p.write_text(text, encoding="utf-8")
    return list(CSVTickDataFeed(file_path=str(p)))


def _feed_bytes(data, tmp_path, filename="test.csv", encoding="utf-8"):
    p = tmp_path / filename
    p.write_bytes(data)
    return list(CSVTickDataFeed(file_path=str(p)))


# ---------------------------------------------------------------------------
# TestColumnAliases
# ---------------------------------------------------------------------------

class TestColumnAliases:

    def test_close_alias_lower(self, tmp_path):
        ticks = _feed_from_text("timestamp,close\n2024-01-01,100.0\n", tmp_path)
        assert len(ticks) == 1
        assert ticks[0].close == 100.0

    def test_close_alias_title_case(self, tmp_path):
        ticks = _feed_from_text("timestamp,Close\n2024-01-01,100.0\n", tmp_path)
        assert ticks[0].close == 100.0

    def test_close_alias_c(self, tmp_path):
        ticks = _feed_from_text("timestamp,c\n2024-01-01,100.0\n", tmp_path)
        assert ticks[0].close == 100.0

    def test_close_alias_bid(self, tmp_path):
        """Legacy: bid column maps to close."""
        ticks = _feed_from_text("timestamp,bid\n2024-01-01,99.5\n", tmp_path)
        assert ticks[0].close == 99.5

    def test_close_alias_price(self, tmp_path):
        ticks = _feed_from_text("timestamp,price\n2024-01-01,101.0\n", tmp_path)
        assert ticks[0].close == 101.0

    def test_close_alias_last(self, tmp_path):
        ticks = _feed_from_text("timestamp,last\n2024-01-01,102.0\n", tmp_path)
        assert ticks[0].close == 102.0

    def test_ohlcv_all_populated(self, tmp_path):
        csv = "timestamp,open,high,low,close,volume\n2024-01-01,99,101,98,100,500\n"
        ticks = _feed_from_text(csv, tmp_path)
        t = ticks[0]
        assert t.open == 99.0
        assert t.high == 101.0
        assert t.low == 98.0
        assert t.close == 100.0
        assert t.volume == 500.0

    def test_missing_open_defaults_to_close(self, tmp_path):
        csv = "timestamp,close\n2024-01-01,100.0\n"
        ticks = _feed_from_text(csv, tmp_path)
        assert ticks[0].open == 100.0

    def test_missing_high_low_defaults_to_close(self, tmp_path):
        csv = "timestamp,close\n2024-01-01,100.0\n"
        ticks = _feed_from_text(csv, tmp_path)
        assert ticks[0].high == 100.0
        assert ticks[0].low == 100.0

    def test_missing_volume_defaults_to_zero(self, tmp_path):
        csv = "timestamp,close\n2024-01-01,100.0\n"
        ticks = _feed_from_text(csv, tmp_path)
        assert ticks[0].volume == 0.0


# ---------------------------------------------------------------------------
# TestTimestampFormats
# ---------------------------------------------------------------------------

class TestTimestampFormats:

    def test_iso_date(self, tmp_path):
        ticks = _feed_from_text("timestamp,close\n2024-01-15,100\n", tmp_path)
        assert ticks[0].time.year == 2024
        assert ticks[0].time.month == 1
        assert ticks[0].time.day == 15

    def test_iso_datetime(self, tmp_path):
        ticks = _feed_from_text("timestamp,close\n2024-01-15 09:30:00,100\n", tmp_path)
        assert ticks[0].time.hour == 9
        assert ticks[0].time.minute == 30

    def test_iso_datetime_with_t_separator(self, tmp_path):
        ticks = _feed_from_text("timestamp,close\n2024-01-15T09:30:00,100\n", tmp_path)
        assert ticks[0].time.hour == 9

    def test_iso_with_z_suffix(self, tmp_path):
        ticks = _feed_from_text("timestamp,close\n2024-01-15T09:30:00Z,100\n", tmp_path)
        assert ticks[0].time is not None

    def test_unix_epoch(self, tmp_path):
        # 1705312200 = 2024-01-15 09:30:00 UTC
        ticks = _feed_from_text("timestamp,close\n1705312200,100\n", tmp_path)
        assert ticks[0].time is not None

    def test_out_of_order_timestamps_file_order_preserved(self, tmp_path):
        csv = "timestamp,close\n2024-01-03,103\n2024-01-01,101\n2024-01-02,102\n"
        ticks = _feed_from_text(csv, tmp_path)
        assert len(ticks) == 3
        assert ticks[0].close == 103.0  # file order, not sorted
        assert ticks[1].close == 101.0

    def test_duplicate_timestamps_both_yielded(self, tmp_path):
        csv = "timestamp,close\n2024-01-01,100\n2024-01-01,101\n"
        ticks = _feed_from_text(csv, tmp_path)
        assert len(ticks) == 2


# ---------------------------------------------------------------------------
# TestBadDataHandling
# ---------------------------------------------------------------------------

class TestBadDataHandling:

    def test_non_numeric_price_row_skipped(self, tmp_path):
        csv = "timestamp,close\n2024-01-01,abc\n2024-01-02,100\n"
        ticks = _feed_from_text(csv, tmp_path)
        assert len(ticks) == 1
        assert ticks[0].close == 100.0

    def test_negative_prices_passed_through(self, tmp_path):
        """Parser does not validate price sign — passes through as-is."""
        csv = "timestamp,close\n2024-01-01,-5.0\n"
        ticks = _feed_from_text(csv, tmp_path)
        assert ticks[0].close == -5.0

    def test_high_less_than_low_passed_through(self, tmp_path):
        """Parser does not validate OHLC relationships."""
        csv = "timestamp,open,high,low,close,volume\n2024-01-01,100,95,105,100,1000\n"
        ticks = _feed_from_text(csv, tmp_path)
        assert ticks[0].high == 95.0
        assert ticks[0].low == 105.0

    def test_empty_file_no_rows(self, tmp_path):
        csv = "timestamp,close\n"
        ticks = _feed_from_text(csv, tmp_path)
        assert len(ticks) == 0

    def test_no_close_column_raises_value_error(self, tmp_path):
        csv = "timestamp,notaclose\n2024-01-01,100\n"
        with pytest.raises(ValueError, match="price/close"):
            _feed_from_text(csv, tmp_path)

    def test_windows_crlf_line_endings(self, tmp_path):
        data = b"timestamp,close\r\n2024-01-01,100\r\n2024-01-02,101\r\n"
        ticks = _feed_bytes(data, tmp_path)
        assert len(ticks) == 2
        assert ticks[0].close == 100.0

    def test_extra_unknown_columns_ignored(self, tmp_path):
        csv = "timestamp,close,extra_col,another\n2024-01-01,100,foo,bar\n"
        ticks = _feed_from_text(csv, tmp_path)
        assert len(ticks) == 1
        assert ticks[0].close == 100.0

    def test_nan_string_price_row_skipped(self, tmp_path):
        csv = "timestamp,close\n2024-01-01,NaN\n2024-01-02,100\n"
        ticks = _feed_from_text(csv, tmp_path)
        # _safe_float returns None for NaN → skipped
        assert len(ticks) == 1


# ---------------------------------------------------------------------------
# TestOHLCRegressionGuard
# ---------------------------------------------------------------------------

class TestOHLCRegressionGuard:

    def test_high_low_populated_from_csv(self, tmp_path):
        """CSV with explicit high/low → TickData.high and .low populated correctly."""
        csv = "timestamp,open,high,low,close,volume\n2024-01-01,99,105,95,100,1000\n"
        ticks = _feed_from_text(csv, tmp_path)
        assert ticks[0].high == 105.0
        assert ticks[0].low == 95.0

    def test_atr_on_csv_feed_returns_non_nan(self, tmp_path):
        """ATR on a CSV feed must return non-NaN values after warmup.
        Regression guard: high/low not being populated would cause NaN ATR."""
        rows = ["timestamp,open,high,low,close,volume"]
        for i in range(20):
            close = 100 + i
            rows.append(f"2024-01-{i+1:02d},{close-0.5},{close+1},{close-1},{close},1000")
        csv = "\n".join(rows)
        ticks = _feed_from_text(csv, tmp_path)
        series = PriceSeries()
        atr = ATROperand(period=5)
        found_non_nan = False
        for tick in ticks:
            series.push(tick)
            val = atr.value(series)
            if not math.isnan(val):
                found_non_nan = True
                assert val > 0, "ATR must be positive"
        assert found_non_nan, "ATR never returned a non-NaN value"

    def test_highest_high_on_csv_feed_returns_non_nan(self, tmp_path):
        """HighestHighOperand on a CSV feed must return non-NaN after warmup."""
        rows = ["timestamp,open,high,low,close,volume"]
        for i in range(10):
            close = 100 + i
            rows.append(f"2024-01-{i+1:02d},{close},{close+2},{close-2},{close},1000")
        csv = "\n".join(rows)
        ticks = _feed_from_text(csv, tmp_path)
        series = PriceSeries()
        hh = HighestHighOperand(period=3)
        found_non_nan = False
        for tick in ticks:
            series.push(tick)
            val = hh.value(series)
            if not math.isnan(val):
                found_non_nan = True
                assert val >= 100, "HighestHigh should be >= starting price"
        assert found_non_nan, "HighestHigh never returned a non-NaN value"
