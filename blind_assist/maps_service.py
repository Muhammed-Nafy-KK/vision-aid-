from __future__ import annotations

from dataclasses import dataclass

import requests

from .config import Settings


@dataclass(slots=True)
class RouteStep:
    instruction: str
    distance_meters: int


@dataclass(slots=True)
class OutdoorRoute:
    origin_label: str
    destination_label: str
    steps: list[RouteStep]
    distance_meters: int
    duration_text: str


class MapsService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._saved_origin: str = ""
        self._active_route: OutdoorRoute | None = None
        self._step_index: int = 0
        self._session = requests.Session()
        user_agent = self.settings.nominatim_user_agent
        if self.settings.nominatim_contact_email:
            user_agent = f"{user_agent} ({self.settings.nominatim_contact_email})"
        self._session.headers.update({"User-Agent": user_agent})

    def set_origin(self, origin: str) -> str:
        self._saved_origin = origin.strip()
        return f"Saved current location as {self._saved_origin}."

    def route_to(self, destination: str) -> str:
        if not self._saved_origin:
            return "Set your current location first with set location <place>."
        route = self._compute_route(self._saved_origin, destination.strip())
        self._active_route = route
        self._step_index = 0
        return self._route_summary(route)

    def route_from_to(self, origin: str, destination: str) -> str:
        route = self._compute_route(origin.strip(), destination.strip())
        self._saved_origin = origin.strip()
        self._active_route = route
        self._step_index = 0
        return self._route_summary(route)

    def next_step(self) -> str:
        if not self._active_route or not self._active_route.steps:
            return "No active route. Say route to <destination> first."
        if self._step_index >= len(self._active_route.steps):
            return "You have reached the end of the saved route."
        step = self._active_route.steps[self._step_index]
        self._step_index += 1
        return f"Step {self._step_index}: {step.instruction} for about {step.distance_meters} meters."

    def previous_step(self) -> str:
        if not self._active_route or not self._active_route.steps:
            return "No active route."
        self._step_index = max(self._step_index - 1, 0)
        step = self._active_route.steps[self._step_index]
        return f"Step {self._step_index + 1}: {step.instruction} for about {step.distance_meters} meters."

    def repeat_step(self) -> str:
        if not self._active_route or not self._active_route.steps:
            return "No active route."
        index = max(self._step_index - 1, 0)
        step = self._active_route.steps[index]
        return f"Step {index + 1}: {step.instruction} for about {step.distance_meters} meters."

    def route_status(self) -> str:
        if not self._active_route:
            return "No active route."
        total_steps = len(self._active_route.steps)
        next_index = min(self._step_index + 1, total_steps) if total_steps else 0
        remaining_steps = max(total_steps - self._step_index, 0)
        next_instruction = ""
        if self._step_index < total_steps:
            step = self._active_route.steps[self._step_index]
            next_instruction = f" Next step: {step.instruction} for about {step.distance_meters} meters."
        return (
            f"Route to {self._active_route.destination_label}. "
            f"Step {next_index} of {total_steps}. "
            f"{remaining_steps} steps remaining."
            f"{next_instruction}"
        )

    def restart_route(self) -> str:
        if not self._active_route:
            return "No active route."
        self._step_index = 0
        return self._route_summary(self._active_route)

    def current_destination(self) -> str:
        if not self._active_route:
            return "No active route."
        return f"Current destination is {self._active_route.destination_label}."

    def stop_route(self) -> str:
        self._active_route = None
        self._step_index = 0
        return "Outdoor route cleared."

    def _route_summary(self, route: OutdoorRoute) -> str:
        first_step = route.steps[0].instruction if route.steps else "No walking steps returned."
        return (
            f"Route ready from {route.origin_label} to {route.destination_label}. "
            f"Total distance about {route.distance_meters} meters, duration about {route.duration_text}. "
            f"First step: {first_step}"
        )

    def _compute_route(self, origin: str, destination: str) -> OutdoorRoute:
        origin_point, origin_label = self._geocode(origin)
        destination_point, destination_label = self._geocode(destination)
        coordinates = (
            f"{origin_point['lon']},{origin_point['lat']};"
            f"{destination_point['lon']},{destination_point['lat']}"
        )
        response = self._session.get(
            f"{self.settings.osrm_base_url}/route/v1/foot/{coordinates}",
            params={"steps": "true", "overview": "false"},
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
        routes = payload.get("routes", [])
        if not routes:
            raise RuntimeError("OpenStreetMap routing did not return a walking route.")
        route = routes[0]
        legs = route.get("legs", [])
        steps_payload = legs[0].get("steps", []) if legs else []
        steps = [
            RouteStep(
                instruction=self._format_step(step),
                distance_meters=max(1, round(step.get("distance", 0))),
            )
            for step in steps_payload
        ]
        return OutdoorRoute(
            origin_label=origin_label,
            destination_label=destination_label,
            steps=steps,
            distance_meters=round(route.get("distance", 0)),
            duration_text=self._format_duration(route.get("duration", 0)),
        )

    def _geocode(self, place: str) -> tuple[dict[str, float], str]:
        params = {
            "q": place,
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 0,
        }
        if self.settings.nominatim_countrycodes:
            params["countrycodes"] = self.settings.nominatim_countrycodes
        if self.settings.nominatim_contact_email:
            params["email"] = self.settings.nominatim_contact_email
        response = self._session.get(
            f"{self.settings.nominatim_base_url}/search",
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        results = response.json()
        if not results:
            raise RuntimeError(f"Could not find location for {place}.")
        top = results[0]
        return {"lat": float(top["lat"]), "lon": float(top["lon"])}, top.get("display_name", place)

    def _format_step(self, step: dict) -> str:
        maneuver = step.get("maneuver", {})
        maneuver_type = (maneuver.get("type") or "continue").replace("_", " ")
        modifier = (maneuver.get("modifier") or "").replace("_", " ")
        road_name = (step.get("name") or "").strip()

        if maneuver_type == "depart":
            return f"Start and walk along {road_name}" if road_name else "Start walking"
        if maneuver_type == "arrive":
            return "Arrive at your destination"

        pieces: list[str] = []
        pieces.append(f"{maneuver_type} {modifier}".strip())
        if road_name:
            pieces.append(f"onto {road_name}")
        instruction = " ".join(piece for piece in pieces if piece).strip()
        return instruction[:1].upper() + instruction[1:] if instruction else "Continue walking"

    def _format_duration(self, seconds: float) -> str:
        total_seconds = max(1, round(seconds))
        minutes, sec = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        chunks: list[str] = []
        if hours:
            chunks.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes:
            chunks.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        if not chunks:
            chunks.append(f"{sec} second{'s' if sec != 1 else ''}")
        return " ".join(chunks)
