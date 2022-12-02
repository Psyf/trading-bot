from dataclasses import dataclass
from typing import Literal, Tuple
import re


@dataclass
class TradingCall:
    symbol: str
    side: Literal["BUY", "SELL"]
    entry: Tuple[float, float]
    stop_loss: float
    targets: list[float]


class TradingCallParser:
    def __init__(self):
        pass

    def tokenize(self, txt: str) -> dict[str, str]:
        match = re.search(r"setup: ([a-z]+)", txt)
        if match:
            return {"symbol": match.group(1).upper()}

        match = re.search(r"(\w+) trade", txt)
        if match:
            side = match.group(1).upper()
            if side != "LONG" and side != "SHORT":
                raise ValueError("Invalid trade type")
            return {"side": "BUY" if side == "LONG" else "SELL"}
        match = re.search(r"entry zone: (\d+\.\d+[^\d]*\d+\.\d+)", txt)

        if match:
            return {"entry": match.group(1)}

        match = re.search(r"stop-loss: (\d+\.\d+)", txt)
        if match:
            return {"stop_loss": match.group(1)}

        match = re.search(r"target.*(\d+\.\d+)", txt)
        if match:
            return {"target": match.group(1)}
        return {}

    def parse(self, txt: str) -> TradingCall:
        # Parse the text
        targets = []
        entry = (0.0, 0.0)
        parsed_data: dict[str, str] = {}
        for line in txt.lower().split("\n"):
            t = self.tokenize(line)
            if "target" in t:
                targets.append(float(t["target"]))
            elif "entry" in t:
                splits = t["entry"].split("-")
                entries = [float(s.strip()) for s in splits]
                entry = (entries[0], entries[1])
            else:
                parsed_data.update(t)

        return TradingCall(
            symbol=parsed_data["symbol"],
            side=parsed_data["side"],  # type: ignore
            entry=entry,
            stop_loss=float(parsed_data["stop_loss"]),
            targets=targets,
        )
