"""Hysteresis-based arrival state machine."""

from dataclasses import dataclass
from typing import Dict


@dataclass
class ArrivalState:
    arrived: bool = False
    enter_count: int = 0
    exit_count: int = 0


@dataclass(frozen=True)
class ArrivalResult:
    arrived: bool
    arrival_event: bool
    departure_event: bool


class ArrivalDetector:
    def __init__(self, enter_required: int = 3, exit_required: int = 5, exit_margin_db: int = 10):
        self.enter_required = enter_required
        self.exit_required = exit_required
        self.exit_margin_db = exit_margin_db
        self._states: Dict[str, ArrivalState] = {}

    def update(self, beacon_id: str, filtered_rssi: int, arrival_rssi: int) -> ArrivalResult:
        state = self._states.setdefault(beacon_id, ArrivalState())
        arrival_event = False
        departure_event = False

        if not state.arrived:
            if filtered_rssi >= arrival_rssi:
                state.enter_count += 1
                if state.enter_count >= self.enter_required:
                    state.arrived = True
                    state.enter_count = 0
                    state.exit_count = 0
                    arrival_event = True
            else:
                state.enter_count = 0
        else:
            if filtered_rssi <= arrival_rssi - self.exit_margin_db:
                state.exit_count += 1
                if state.exit_count >= self.exit_required:
                    state.arrived = False
                    state.exit_count = 0
                    departure_event = True
            else:
                state.exit_count = 0

        return ArrivalResult(state.arrived, arrival_event, departure_event)

    def is_arrived(self, beacon_id: str) -> bool:
        return self._states.get(beacon_id, ArrivalState()).arrived

    def update_missing(self, beacon_id: str) -> ArrivalResult:
        """Count a timed-out scan as an exit sample for an arrived beacon."""
        state = self._states.setdefault(beacon_id, ArrivalState())
        departure_event = False
        state.enter_count = 0
        if state.arrived:
            state.exit_count += 1
            if state.exit_count >= self.exit_required:
                state.arrived = False
                state.exit_count = 0
                departure_event = True
        return ArrivalResult(state.arrived, False, departure_event)

    def retain(self, beacon_ids) -> None:
        valid = set(beacon_ids)
        self._states = {key: value for key, value in self._states.items() if key in valid}
