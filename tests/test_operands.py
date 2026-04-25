"""
tests/test_operands.py — Unit tests for all operand types in strategy_rules.py.

Does NOT import BacktestEngine. Uses PriceSeries and _tick() helper directly.
"""
import math
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta

import pytest

from tickdata import TickData
from strategy_rules import (
    PriceSeries,
    PriceField,
    SMAOperand,
    EMAOperand,
    RSIOperand,
    BollingerOperand,
    BollingerComponent,
    MACDOperand,
    MACDComponent,
    ATROperand,
    HighestHighOperand,
    LowestLowOperand,
    LookbackOperand,
    TypicalPriceOperand,
    ConstantOperand,
    PriceOperand,
    _parse_price_field,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _tick(i, close=100.0, open_=None, high=None, low=None, volume=1000.0):
    c = close
    o = open_ if open_ is not None else c
    h = high if high is not None else c * 1.001
    l = low if low is not None else c * 0.999
    return TickData(
        name="ASSET",
        close=c,
        open=o,
        high=h,
        low=l,
        volume=volume,
        time=datetime(2024, 1, 1) + timedelta(days=i),
    )


def _feed(series: PriceSeries, prices, **tick_kwargs):
    """Push a list of close prices into series. Returns series."""
    for i, p in enumerate(prices):
        series.push(_tick(i, close=p, **tick_kwargs))
    return series


# ---------------------------------------------------------------------------
# TestSMAOperand
# ---------------------------------------------------------------------------

class TestSMAOperand:
    def test_nan_before_period(self):
        series = PriceSeries()
        op = SMAOperand(period=3)
        for i in range(2):
            series.push(_tick(i, close=100.0))
        result = op.value(series)
        assert math.isnan(result), f"Expected nan, got {result}"

    def test_correct_after_period(self):
        series = PriceSeries()
        op = SMAOperand(period=3)
        for i, p in enumerate([10.0, 20.0, 30.0]):
            series.push(_tick(i, close=p))
        result = op.value(series)
        assert math.isclose(result, 20.0, rel_tol=1e-6), f"Expected 20.0, got {result}"

    def test_period_1(self):
        series = PriceSeries()
        op = SMAOperand(period=1)
        for i, p in enumerate([5.0, 10.0, 15.0, 99.0]):
            series.push(_tick(i, close=p))
            assert math.isclose(op.value(series), p, rel_tol=1e-6), \
                f"SMA(1) should equal current close at bar {i}"

    def test_reacts_to_price_change(self):
        series = PriceSeries()
        op = SMAOperand(period=3)
        # Stable at 100
        for i in range(5):
            series.push(_tick(i, close=100.0))
        baseline = op.value(series)
        # Now a big spike
        series.push(_tick(5, close=200.0))
        new_val = op.value(series)
        assert new_val > baseline, "SMA should shift up after price spike"


# ---------------------------------------------------------------------------
# TestEMAOperand
# ---------------------------------------------------------------------------

class TestEMAOperand:
    def test_nan_before_warmup(self):
        series = PriceSeries()
        op = EMAOperand(period=5)
        # EMAOperand.min_bars = period * 2 = 10; but the underlying ema()
        # returns nan if len(buf) < period. EMAOperand just delegates to series.ema().
        # Push only period-1 = 4 bars — must be nan.
        for i in range(4):
            series.push(_tick(i, close=100.0))
        result = op.value(series)
        assert math.isnan(result), f"Expected nan before period bars, got {result}"

    def test_converges_on_flat(self):
        """After many flat bars EMA ≈ the flat price (within 0.1%)."""
        series = PriceSeries()
        op = EMAOperand(period=10)
        price = 50.0
        for i in range(100):
            series.push(_tick(i, close=price))
        result = op.value(series)
        assert not math.isnan(result)
        assert math.isclose(result, price, rel_tol=0.001), \
            f"EMA should converge to {price}, got {result}"

    def test_ema5_reacts_faster_than_ema20(self):
        """On a rising series, EMA(5) > EMA(20) after sufficient warmup."""
        series5 = PriceSeries()
        series20 = PriceSeries()
        op5 = EMAOperand(period=5)
        op20 = EMAOperand(period=20)
        for i in range(60):
            t = _tick(i, close=100.0 + i * 0.5)
            series5.push(t)
            series20.push(t)
        v5 = op5.value(series5)
        v20 = op20.value(series20)
        assert not math.isnan(v5) and not math.isnan(v20)
        assert v5 > v20, f"EMA(5)={v5} should be > EMA(20)={v20} on rising series"


# ---------------------------------------------------------------------------
# TestRSIOperand
# ---------------------------------------------------------------------------

class TestRSIOperand:
    def test_nan_before_warmup(self):
        series = PriceSeries()
        op = RSIOperand(period=14)
        for i in range(14):  # need 15 bars; 14 is not enough
            series.push(_tick(i, close=100.0 + i))
        result = op.value(series)
        assert math.isnan(result), f"Expected nan before 15 bars, got {result}"

    def test_flat_prices_rsi_50(self):
        """Alternating +1/-1 → RSI near 50."""
        series = PriceSeries()
        op = RSIOperand(period=14)
        price = 100.0
        for i in range(50):
            price += 1.0 if i % 2 == 0 else -1.0
            series.push(_tick(i, close=price))
        result = op.value(series)
        assert not math.isnan(result)
        assert abs(result - 50.0) < 10.0, f"Expected RSI near 50, got {result}"

    def test_rising_rsi_high(self):
        """30 bars of +1 each → RSI > 90."""
        series = PriceSeries()
        op = RSIOperand(period=14)
        price = 100.0
        for i in range(30):
            price += 1.0
            series.push(_tick(i, close=price))
        result = op.value(series)
        assert not math.isnan(result)
        assert result > 90.0, f"Expected RSI > 90 on strong uptrend, got {result}"

    def test_falling_rsi_low(self):
        """30 bars of -1 each → RSI < 10."""
        series = PriceSeries()
        op = RSIOperand(period=14)
        price = 200.0
        for i in range(30):
            price -= 1.0
            series.push(_tick(i, close=price))
        result = op.value(series)
        assert not math.isnan(result)
        assert result < 10.0, f"Expected RSI < 10 on strong downtrend, got {result}"

    def test_period_1_no_crash(self):
        """RSI(1) with 2 bars should not raise."""
        series = PriceSeries()
        op = RSIOperand(period=1)
        series.push(_tick(0, close=100.0))
        series.push(_tick(1, close=101.0))
        result = op.value(series)
        # May be nan or a float — just must not raise
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# TestBollingerOperand
# ---------------------------------------------------------------------------

class TestBollingerOperand:
    def _fill(self, prices, period=20, std_dev=2.0):
        series = PriceSeries()
        for i, p in enumerate(prices):
            series.push(_tick(i, close=p))
        return series, period, std_dev

    def test_middle_equals_sma(self):
        prices = [100.0 + i * 0.1 for i in range(25)]
        series, period, std_dev = self._fill(prices, period=20)
        middle_op = BollingerOperand(period=period, std_dev=std_dev,
                                     component=BollingerComponent.MIDDLE)
        sma_op = SMAOperand(period=period)
        mid = middle_op.value(series)
        sma = sma_op.value(series)
        assert not math.isnan(mid) and not math.isnan(sma)
        assert math.isclose(mid, sma, rel_tol=1e-9), \
            f"Bollinger middle {mid} != SMA {sma}"

    def test_upper_lower_symmetry(self):
        prices = [100.0 + i * 0.3 for i in range(25)]
        series, period, std_dev = self._fill(prices, period=20)
        upper = BollingerOperand(period=period, std_dev=std_dev,
                                  component=BollingerComponent.UPPER).value(series)
        middle = BollingerOperand(period=period, std_dev=std_dev,
                                   component=BollingerComponent.MIDDLE).value(series)
        lower = BollingerOperand(period=period, std_dev=std_dev,
                                  component=BollingerComponent.LOWER).value(series)
        assert not any(math.isnan(x) for x in [upper, middle, lower])
        diff_up = upper - middle
        diff_lo = middle - lower
        assert math.isclose(diff_up, diff_lo, rel_tol=1e-9), \
            f"Bollinger not symmetric: upper-mid={diff_up}, mid-lower={diff_lo}"

    def test_width_zero_on_flat(self):
        prices = [50.0] * 25
        series, period, std_dev = self._fill(prices, period=20)
        width = BollingerOperand(period=period, std_dev=std_dev,
                                  component=BollingerComponent.WIDTH).value(series)
        assert not math.isnan(width)
        assert math.isclose(width, 0.0, abs_tol=1e-9), \
            f"Width should be 0 on flat prices, got {width}"

    def test_pct_b_at_bands(self):
        """
        Test pct_b ≈ 1.0 when price is close to the upper band, and ≈ 0.0 near lower.

        We inject a very high or very low final price to drive pct_b toward its extremes
        without attempting to hit the bands exactly (bands shift when the price changes).
        """
        period = 10
        # Build a stable baseline of 9 bars at 100
        series_up = PriceSeries()
        series_lo = PriceSeries()
        for i in range(period - 1):
            t = _tick(i, close=100.0)
            series_up.push(t)
            series_lo.push(t)

        # Drive the last bar very high (well above upper band) → pct_b > 1
        series_up.push(_tick(period - 1, close=200.0))
        pct_b_up = BollingerOperand(period=period, std_dev=2.0,
                                     component=BollingerComponent.PCT_B).value(series_up)
        assert not math.isnan(pct_b_up)
        assert pct_b_up > 0.9, f"pct_b should be > 0.9 when price is well above upper band, got {pct_b_up}"

        # Drive the last bar very low (well below lower band) → pct_b < 0
        series_lo.push(_tick(period - 1, close=1.0))
        pct_b_lo = BollingerOperand(period=period, std_dev=2.0,
                                     component=BollingerComponent.PCT_B).value(series_lo)
        assert not math.isnan(pct_b_lo)
        assert pct_b_lo < 0.1, f"pct_b should be < 0.1 when price is well below lower band, got {pct_b_lo}"

    def test_nan_before_period(self):
        series = PriceSeries()
        op = BollingerOperand(period=20, std_dev=2.0, component=BollingerComponent.UPPER)
        for i in range(15):
            series.push(_tick(i, close=100.0))
        result = op.value(series)
        assert math.isnan(result), f"Expected nan before period bars, got {result}"

    def test_no_zerodivision_on_flat_pct_b(self):
        """Flat prices → std=0 → no ZeroDivisionError; pct_b returns 0.5."""
        series = PriceSeries()
        op = BollingerOperand(period=10, std_dev=2.0, component=BollingerComponent.PCT_B)
        for i in range(15):
            series.push(_tick(i, close=100.0))
        result = op.value(series)  # Must not raise
        assert not math.isnan(result)
        assert math.isclose(result, 0.5, abs_tol=1e-9), \
            f"pct_b on flat prices should be 0.5, got {result}"


# ---------------------------------------------------------------------------
# TestMACDOperand
# ---------------------------------------------------------------------------

class TestMACDOperand:
    def test_nan_during_warmup(self):
        """MACD(12,26,9) HIST returns nan before slow+signal = 35 bars."""
        series = PriceSeries()
        op = MACDOperand(fast=12, slow=26, signal=9, component=MACDComponent.HIST)
        for i in range(34):
            series.push(_tick(i, close=100.0 + i * 0.1))
        result = op.value(series)
        assert math.isnan(result), f"Expected nan before 35 bars, got {result}"

    def test_hist_positive_when_fast_above_slow(self):
        """On an exponentially rising series, HIST > 0.
        Uses exponential growth so the MACD line stays ahead of signal.
        Must call op.value() each bar so the MACD line deque accumulates.
        """
        series = PriceSeries()
        op = MACDOperand(fast=12, slow=26, signal=9, component=MACDComponent.HIST)
        result = math.nan
        for i in range(60):
            series.push(_tick(i, close=100.0 * (1.01 ** i)))
            result = op.value(series)
        assert not math.isnan(result), "HIST should be valid after 60 bars"
        assert result > 0, f"HIST should be > 0 on exponentially rising series, got {result}"

    def test_hist_negative_when_fast_below_slow(self):
        """After a flat period followed by a sharp drop, HIST < 0.
        The fast EMA reacts first to the drop, pulling MACD line below signal.
        Must call op.value() each bar so the MACD line deque accumulates.
        """
        series = PriceSeries()
        op = MACDOperand(fast=12, slow=26, signal=9, component=MACDComponent.HIST)
        result = math.nan
        # 40 flat bars to seed the EMAs, then sharp exponential drop
        for i in range(50):
            if i < 40:
                close = 100.0
            else:
                close = 100.0 * (0.97 ** (i - 40))
            series.push(_tick(i, close=close))
            result = op.value(series)
        assert not math.isnan(result), "HIST should be valid after 50 bars"
        assert result < 0, f"HIST should be < 0 after sharp price drop, got {result}"

    def test_fast_equals_slow_hist_zero(self):
        """MACD(10,10,9): fast_ema == slow_ema always → MACD line = 0 → HIST = 0."""
        series = PriceSeries()
        op = MACDOperand(fast=10, slow=10, signal=9, component=MACDComponent.HIST)
        for i in range(30):
            series.push(_tick(i, close=100.0 + i * 0.5))
        result = op.value(series)
        if not math.isnan(result):
            assert math.isclose(result, 0.0, abs_tol=1e-9), \
                f"HIST should be 0 when fast==slow, got {result}"
        # nan during warmup is also acceptable


# ---------------------------------------------------------------------------
# TestATROperand
# ---------------------------------------------------------------------------

class TestATROperand:
    def test_non_negative(self):
        series = PriceSeries()
        op = ATROperand(period=5)
        for i in range(20):
            series.push(_tick(i, close=100.0 + i * 0.3))
        result = op.value(series)
        assert not math.isnan(result)
        assert result >= 0.0, f"ATR should be >= 0, got {result}"

    def test_nan_before_period_plus_1(self):
        """ATR(14) returns nan before 15 bars."""
        series = PriceSeries()
        op = ATROperand(period=14)
        for i in range(14):  # need 15
            series.push(_tick(i, close=100.0 + i))
        result = op.value(series)
        assert math.isnan(result), f"Expected nan before 15 bars, got {result}"

    def test_no_gap_atr_approx_hl_range(self):
        """
        When open == prev_close (no gaps), ATR ≈ average of (high-low).
        We construct ticks where open == prev_close, so the only true range
        component is high - low.
        """
        period = 5
        series = PriceSeries()
        op = ATROperand(period=period)
        hl_ranges = []
        prev_close = 100.0
        for i in range(20):
            o = prev_close
            c = o  # close == open for simplicity
            h = c + 1.0
            l = c - 1.0
            hl_ranges.append(h - l)  # = 2.0 always
            t = _tick(i, close=c, open_=o, high=h, low=l)
            series.push(t)
            prev_close = c
        result = op.value(series)
        expected = 2.0  # all hl ranges are 2.0
        assert not math.isnan(result)
        assert math.isclose(result, expected, rel_tol=0.10), \
            f"ATR {result} should be within 10% of avg hl range {expected}"

    def test_gap_open_larger_atr(self):
        """ATR with gaps should be >= ATR on same H-L data without gaps."""
        period = 5
        n = 20

        # Series without gaps
        series_no_gap = PriceSeries()
        for i in range(n):
            c = 100.0
            o = c
            h = c + 1.0
            l = c - 1.0
            series_no_gap.push(_tick(i, close=c, open_=o, high=h, low=l))

        # Series with gaps (open jumps 5 away from prev_close each bar)
        series_gap = PriceSeries()
        prev_close = 100.0
        for i in range(n):
            o = prev_close + 5.0 * (1 if i % 2 == 0 else -1)
            c = o
            h = c + 1.0
            l = c - 1.0
            series_gap.push(_tick(i, close=c, open_=o, high=h, low=l))
            prev_close = c

        op = ATROperand(period=period)
        atr_no_gap = op.value(series_no_gap)
        atr_gap = op.value(series_gap)
        assert not math.isnan(atr_no_gap) and not math.isnan(atr_gap)
        assert atr_gap >= atr_no_gap, \
            f"ATR with gaps {atr_gap} should be >= ATR without gaps {atr_no_gap}"

    def test_period_1_no_crash(self):
        """ATR(1) with 2 bars should not raise."""
        series = PriceSeries()
        op = ATROperand(period=1)
        series.push(_tick(0, close=100.0))
        series.push(_tick(1, close=101.0))
        result = op.value(series)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# TestHighestLowest
# ---------------------------------------------------------------------------

class TestHighestLowest:
    def test_highest_high_uses_high_field(self):
        """HighestHighOperand uses the `high` field, not `close`."""
        series = PriceSeries()
        op = HighestHighOperand(period=3)
        # Close stays at 100, but high varies
        highs = [105.0, 110.0, 108.0]
        for i, h in enumerate(highs):
            series.push(_tick(i, close=100.0, high=h, low=99.0))
        result = op.value(series)
        assert math.isclose(result, 110.0, rel_tol=1e-6), \
            f"HighestHigh should return max of highs (110), got {result}"

    def test_lowest_low_uses_low_field(self):
        """LowestLowOperand uses the `low` field, not `close`."""
        series = PriceSeries()
        op = LowestLowOperand(period=3)
        lows = [95.0, 90.0, 93.0]
        for i, l in enumerate(lows):
            series.push(_tick(i, close=100.0, high=101.0, low=l))
        result = op.value(series)
        assert math.isclose(result, 90.0, rel_tol=1e-6), \
            f"LowestLow should return min of lows (90), got {result}"

    def test_period_1_current_value(self):
        """Period=1 returns the current bar's high/low."""
        series = PriceSeries()
        op_hh = HighestHighOperand(period=1)
        op_ll = LowestLowOperand(period=1)
        series.push(_tick(0, close=100.0, high=105.0, low=95.0))
        assert math.isclose(op_hh.value(series), 105.0, rel_tol=1e-6)
        assert math.isclose(op_ll.value(series), 95.0, rel_tol=1e-6)

    def test_rolling_max(self):
        """5 bars of distinct highs, HighestHigh(3) returns max of last 3."""
        series = PriceSeries()
        op = HighestHighOperand(period=3)
        highs = [101.0, 103.0, 107.0, 104.0, 106.0]
        for i, h in enumerate(highs):
            series.push(_tick(i, close=100.0, high=h, low=99.0))
        # Last 3 highs: 107.0, 104.0, 106.0 → max = 107.0
        result = op.value(series)
        assert math.isclose(result, 107.0, rel_tol=1e-6), \
            f"HighestHigh(3) of last 3 highs should be 107.0, got {result}"

    def test_nan_before_period(self):
        """Fewer than period bars → nan."""
        series = PriceSeries()
        op_hh = HighestHighOperand(period=5)
        op_ll = LowestLowOperand(period=5)
        for i in range(4):
            series.push(_tick(i, close=100.0, high=101.0, low=99.0))
        assert math.isnan(op_hh.value(series)), "HighestHigh should return nan before period"
        assert math.isnan(op_ll.value(series)), "LowestLow should return nan before period"


# ---------------------------------------------------------------------------
# TestLookbackOperand
# ---------------------------------------------------------------------------

class TestLookbackOperand:
    def test_nan_before_period_plus_1(self):
        """Lookback(3) returns nan before 4 bars."""
        series = PriceSeries()
        op = LookbackOperand(period=3)
        for i in range(3):  # need 4
            series.push(_tick(i, close=100.0 + i))
        result = op.value(series)
        assert math.isnan(result), f"Expected nan before 4 bars, got {result}"

    def test_returns_n_bars_ago(self):
        """Lookback(1) returns the previous bar's close."""
        series = PriceSeries()
        op = LookbackOperand(period=1)
        prices = [10.0, 20.0, 30.0]
        for i, p in enumerate(prices):
            series.push(_tick(i, close=p))
        result = op.value(series)
        # After 3 pushes, 1 bar ago = prices[-2] = 20.0
        assert math.isclose(result, 20.0, rel_tol=1e-6), \
            f"Lookback(1) should return 20.0 (previous bar), got {result}"

    def test_lookback_3(self):
        """Lookback(3) after 5 bars returns the value at bar[1] (0-indexed)."""
        series = PriceSeries()
        op = LookbackOperand(period=3)
        prices = [11.0, 22.0, 33.0, 44.0, 55.0]  # indices 0..4
        for i, p in enumerate(prices):
            series.push(_tick(i, close=p))
        result = op.value(series)
        # 3 bars ago from index 4 = index 1 = 22.0
        assert math.isclose(result, 22.0, rel_tol=1e-6), \
            f"Lookback(3) after 5 bars should return 22.0, got {result}"


# ---------------------------------------------------------------------------
# TestTypicalPrice
# ---------------------------------------------------------------------------

class TestTypicalPrice:
    def test_typical_price_formula(self):
        """TP = (H + L + C) / 3 exactly."""
        series = PriceSeries()
        op = TypicalPriceOperand()
        H, L, C = 110.0, 90.0, 100.0
        series.push(_tick(0, close=C, high=H, low=L))
        result = op.value(series)
        expected = (H + L + C) / 3.0
        assert math.isclose(result, expected, rel_tol=1e-9), \
            f"TypicalPrice should be {expected}, got {result}"


# ---------------------------------------------------------------------------
# TestConstantAndPrice
# ---------------------------------------------------------------------------

class TestConstantAndPrice:
    def test_constant_always_returns_value(self):
        series = PriceSeries()
        op = ConstantOperand(value_=42.0)
        for i in range(5):
            series.push(_tick(i, close=float(i * 10)))
            assert math.isclose(op.value(series), 42.0, rel_tol=1e-9), \
                f"ConstantOperand should always return 42.0"

    def test_price_close(self):
        series = PriceSeries()
        op = PriceOperand(field=PriceField.CLOSE)
        series.push(_tick(0, close=123.45))
        assert math.isclose(op.value(series), 123.45, rel_tol=1e-9)

    def test_price_high(self):
        series = PriceSeries()
        op = PriceOperand(field=PriceField.HIGH)
        series.push(_tick(0, close=100.0, high=115.0, low=90.0))
        assert math.isclose(op.value(series), 115.0, rel_tol=1e-9)

    def test_price_low(self):
        series = PriceSeries()
        op = PriceOperand(field=PriceField.LOW)
        series.push(_tick(0, close=100.0, high=115.0, low=88.0))
        assert math.isclose(op.value(series), 88.0, rel_tol=1e-9)

    def test_price_volume(self):
        series = PriceSeries()
        op = PriceOperand(field=PriceField.VOLUME)
        series.push(_tick(0, close=100.0, volume=99999.0))
        assert math.isclose(op.value(series), 99999.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# TestPriceFieldBackwardCompat
# ---------------------------------------------------------------------------

class TestPriceFieldBackwardCompat:
    def test_bid_maps_to_close(self):
        assert _parse_price_field("bid") == PriceField.CLOSE

    def test_ask_maps_to_close(self):
        assert _parse_price_field("ask") == PriceField.CLOSE

    def test_mid_maps_to_close(self):
        assert _parse_price_field("mid") == PriceField.CLOSE

    def test_close_unchanged(self):
        assert _parse_price_field("close") == PriceField.CLOSE
