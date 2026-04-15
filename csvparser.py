"""
csvparser.py
============
Reads a CSV file and yields TickData objects.

The column_map dict maps internal field names → CSV column headers:
  {
    "time":   "timestamp",   # datetime column
    "close":  "close",       # bar close price (aliases: Close, c, bid, price, last)
    "volume": "volume",      # optional
    "name":   "symbol",      # optional – overridden by symbol arg
  }

Rows where the price columns cannot be parsed are silently skipped.
"""

from __future__ import annotations

import csv
import math
from datetime import datetime, timezone
from typing import Dict, Iterator, Optional

from tickdata import TickData


# Common datetime formats to try when no explicit format is given.
_FALLBACK_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y%m%d",
    "%Y%m%d%H%M%S",
]


def _parse_dt(raw: str, fmt: Optional[str] = None) -> datetime:
    """Parse a datetime string, trying fmt first then a list of fallbacks."""
    raw = raw.strip()
    if fmt:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    for f in _FALLBACK_FORMATS:
        try:
            return datetime.strptime(raw, f)
        except ValueError:
            continue
    # Last resort: try treating it as a unix timestamp (float seconds)
    try:
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        pass
    raise ValueError(f"Cannot parse datetime: {raw!r}")


def _safe_float(val: str) -> Optional[float]:
    """Return float or None if the value is empty / non-numeric."""
    val = val.strip().replace(",", "")
    if not val:
        return None
    try:
        v = float(val)
        return v if math.isfinite(v) else None
    except ValueError:
        return None


class CSVTickDataFeed:
    """
    Iterable that yields TickData from a CSV file.

    Parameters
    ----------
    file_path   : path to the CSV file
    column_map  : maps internal keys (time, close, volume, name)
                  to actual CSV column headers
    symbol      : overrides the name column (or provides a default)
    time_format : strftime format string for parsing timestamps
    """

    # Default mapping – covers many common OHLCV exports
    DEFAULT_MAP: Dict[str, str] = {
        "time":   "timestamp",
        "close":  "close",
        "volume": "volume",
        "name":   "symbol",
    }

    # Alternative column names tried when the mapped column is absent
    _ALIASES: Dict[str, list[str]] = {
        "time":   ["timestamp", "date", "datetime", "time", "Date", "DateTime", "Timestamp"],
        "close":  ["close", "Close", "c", "bid", "Bid", "price", "Price", "last", "Last"],
        "open":   ["open", "Open", "o"],
        "high":   ["high", "High", "h", "high_price"],
        "low":    ["low", "Low", "l", "low_price"],
        "volume": ["volume", "Volume", "vol", "Vol"],
        "name":   ["symbol", "Symbol", "ticker", "Ticker", "asset", "name"],
    }

    def __init__(
        self,
        file_path: str,
        column_map: Optional[Dict[str, str]] = None,
        symbol: Optional[str] = None,
        time_format: Optional[str] = None,
    ) -> None:
        self.file_path   = file_path
        self.column_map  = {**self.DEFAULT_MAP, **(column_map or {})}
        self.symbol      = symbol
        self.time_format = time_format

    # ------------------------------------------------------------------

    def __iter__(self) -> Iterator[TickData]:
        # Try common encodings in order; latin-1 never raises UnicodeDecodeError
        fh = None
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                candidate = open(self.file_path, newline="", encoding=enc)
                candidate.read(4096)   # probe for decode errors
                candidate.seek(0)
                fh = candidate
                break
            except UnicodeDecodeError:
                candidate.close()
        if fh is None:
            raise ValueError(f"Cannot decode CSV file: {self.file_path!r}")
        with fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                return

            headers = set(reader.fieldnames)

            # Resolve column names: prefer explicit map, fall back to aliases
            def resolve(key: str) -> Optional[str]:
                mapped = self.column_map.get(key, "")
                if mapped and mapped in headers:
                    return mapped
                for alias in self._ALIASES.get(key, []):
                    if alias in headers:
                        return alias
                return None

            col_time   = resolve("time")
            col_close  = resolve("close")
            col_open   = resolve("open")
            col_high   = resolve("high")
            col_low    = resolve("low")
            col_volume = resolve("volume")
            col_name   = resolve("name")

            if col_close is None:
                raise ValueError(
                    f"Could not find a price/close column in CSV. "
                    f"Headers found: {list(reader.fieldnames)}. "
                    f"column_map supplied: {self.column_map}"
                )

            default_name = self.symbol or "ASSET"
            skipped = 0

            for row in reader:
                # --- price --------------------------------------------------
                bar_close = _safe_float(row.get(col_close, ""))
                if bar_close is None:
                    skipped += 1
                    continue

                open_raw = _safe_float(row.get(col_open, "")) if col_open else None
                bar_open = open_raw if open_raw is not None else bar_close

                high_raw = _safe_float(row.get(col_high, "")) if col_high else None
                bar_high = high_raw if high_raw is not None else bar_close

                low_raw = _safe_float(row.get(col_low, "")) if col_low else None
                bar_low = low_raw if low_raw is not None else bar_close

                volume = _safe_float(row.get(col_volume, "")) if col_volume else 0.0
                if volume is None:
                    volume = 0.0

                # --- timestamp ----------------------------------------------
                if col_time and row.get(col_time, "").strip():
                    try:
                        dt = _parse_dt(row[col_time], self.time_format)
                    except ValueError:
                        skipped += 1
                        continue   # skip rows with unparseable timestamps
                else:
                    skipped += 1
                    continue       # skip rows with no timestamp at all

                # --- symbol -------------------------------------------------
                if self.symbol:
                    name = self.symbol
                elif col_name and row.get(col_name, "").strip():
                    name = row[col_name].strip()
                else:
                    name = default_name

                yield TickData(
                    name=name,
                    close=bar_close,
                    volume=volume,
                    time=dt,
                    open=bar_open,
                    high=bar_high,
                    low=bar_low,
                )