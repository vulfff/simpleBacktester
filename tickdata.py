from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class TickData:
    name: str = "asset_name"
    bid: float = 0.0
    ask: float = 0.0
    volume: float = 0.0
    time: datetime = field(default_factory=datetime.now)
    open: float = 0.0   # bar open price; used for next-bar-open fill execution
    high: float = 0.0   # bar high; falls back to bid when not in CSV
    low: float = 0.0    # bar low;  falls back to bid when not in CSV

    def __repr__(self) -> str:
        return (
            f"TickData(name={self.name}, bid={self.bid}, ask={self.ask}, "
            f"volume={self.volume}, time={self.time.isoformat()})"
        )

