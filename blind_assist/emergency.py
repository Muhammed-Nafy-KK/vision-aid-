from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class EmergencySnapshot:
    contact_name: str
    contact_phone: str
    saved_location: str
    route_destination: str
    route_status: str
    voice_status: str
    assist_status: str
    live_status: str


class EmergencyReporter:
    def __init__(self, output_dir: str) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_report(self, snapshot: EmergencySnapshot) -> Path:
        timestamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        path = self.output_dir / f"sos-{timestamp}.txt"
        text = self._render(snapshot, timestamp)
        path.write_text(text, encoding="utf-8")
        latest = self.output_dir / "last_sos.txt"
        latest.write_text(text, encoding="utf-8")
        return latest

    def _render(self, snapshot: EmergencySnapshot, timestamp: str) -> str:
        lines = [
            "Blind Assist SOS Report",
            f"Time: {timestamp}",
            "",
            f"Emergency contact: {snapshot.contact_name or 'Not set'}",
            f"Emergency phone: {snapshot.contact_phone or 'Not set'}",
            f"Saved location: {snapshot.saved_location or 'Not set'}",
            f"Route destination: {snapshot.route_destination or 'Not set'}",
            f"Route status: {snapshot.route_status or 'No active route'}",
            f"Voice mode: {snapshot.voice_status}",
            f"Continuous assist: {snapshot.assist_status}",
            f"Live mode: {snapshot.live_status}",
            "",
            "Suggested message:",
            self._sms_text(snapshot),
        ]
        return "\n".join(lines) + "\n"

    def _sms_text(self, snapshot: EmergencySnapshot) -> str:
        location = snapshot.saved_location or snapshot.route_destination or "unknown location"
        return (
            "I need help. "
            f"My saved location is {location}. "
            f"Route status: {snapshot.route_status or 'no active route'}. "
            "Please call me or come to me."
        )
