from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, Optional

from tickdata import TickData


@dataclass
class CSVTickDataFeed:
	file_path: str
	column_map: Dict[str, str]
	symbol: Optional[str] = None
	time_format: Optional[str] = None

	def __iter__(self) -> Iterable[TickData]:
		with open(self.file_path, "r", newline="") as handle:
			reader = csv.DictReader(handle)
			for row in reader:
				tick = self._parse_row(row)
				if tick is not None:
					yield tick

	def _parse_row(self, row: Dict[str, str]) -> Optional[TickData]:
		try:
			name = self._get_value(row, "name")
			if not name:
				name = self.symbol or "UNKNOWN"

			time_value = self._get_value(row, "time")
			time = self._parse_time(time_value)

			bid = self._parse_float(self._get_value(row, "bid"))
			ask = self._parse_float(self._get_value(row, "ask"))
			volume = self._parse_float(self._get_value(row, "volume"))

			return TickData(name=name, bid=bid, ask=ask, volume=volume, time=time)
		except Exception:
			return None

	def _get_value(self, row: Dict[str, str], logical_name: str) -> str:
		column = self.column_map.get(logical_name, "")
		return row.get(column, "") if column else ""

	def _parse_float(self, value: str) -> float:
		return float(value) if value not in (None, "") else 0.0

	def _parse_time(self, value: str) -> datetime:
		if not value:
			return datetime.utcnow()
		if self.time_format:
			return datetime.strptime(value, self.time_format)
		try:
			return datetime.fromisoformat(value)
		except ValueError:
			return datetime.utcnow()
