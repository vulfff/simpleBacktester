from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class TickData:
    name: str = "asset_name"
    close: float = 0.0   # bar close price
    volume: float = 0.0
    time: datetime = field(default_factory=datetime.now)
    open: float = 0.0    # bar open price; used for next-bar-open fill execution
    high: float = 0.0    # bar high; falls back to close when not in CSV
    low: float = 0.0     # bar low;  falls back to close when not in CSV

    def __repr__(self) -> str:
        return (
            f"TickData(name={self.name}, close={self.close}, "
            f"open={self.open}, volume={self.volume}, time={self.time.isoformat()})"
        )
