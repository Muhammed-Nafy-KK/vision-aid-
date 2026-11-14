from __future__ import annotations

import asyncio
from difflib import SequenceMatcher
from pathlib import Path
import threading
import time

from .camera import CameraStream
from .config import Settings
from .emergency import EmergencyReporter
from .emergency import EmergencySnapshot
from .gemini_service import GeminiService
from .local_vision import basic_navigation_hint
from .local_vision import basic_scene_hint
from .maps_service import MapsService
from .prompts import (
    CROSSING_PROMPT,
    GENERAL_DESCRIPTION_PROMPT,
    NAVIGATION_PROMPT,
    READ_TEXT_PROMPT,
    SAFETY_SCAN_PROMPT,
    object_finding_prompt,
    scene_question_prompt,
)
from .speech import Speaker, Transcriber


class BlindAssistApp:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.camera = CameraStream(self.settings)
        self.speaker = Speaker(self.settings)
        self.transcriber = Transcriber(self.settings)
        self.gemini = GeminiService(self.settings)
        self.maps = MapsService(self.settings)
        output_dir = Path(self.settings.emergency_output_dir)
        if not output_dir.is_absolute():
            output_dir = Path.cwd() / output_dir
        self.emergency = EmergencyReporter(str(output_dir))
        self._voice_stop = threading.Event()
        self._voice_thread: threading.Thread | None = None
        self._voice_enabled = True
        self._voice_session_active = False
        self._live_stop = threading.Event()
        self._live_thread: threading.Thread | None = None
        self._last_live_message = ""
        self._assist_stop = threading.Event()
        self._assist_thread: threading.Thread | None = None
        self._last_assist_message = ""

    def start(self) -> None:
        self.camera.start()
        self.ensure_voice_listener()
        message = f"Blind assist is ready. Say {self.settings.wake_word} to start voice session, and say bye to stop."
        if self.settings.device_profile in {"pi3", "pi3b+", "pi4", "pi5"}:
            message += f" {self.settings.device_profile} mode is active."
        self.speaker.say(message)

    def stop(self) -> None:
        self.shutdown_voice_listener()
        self.stop_assist_mode()
        self.stop_live_mode()
        self.camera.stop()

    def _with_frame(self, prompt: str) -> str:
        try:
            image_bytes = self.camera.get_jpeg_bytes(timeout=3.0)
            if not image_bytes:
                return "I could not get a camera frame."
            return self.gemini.analyze_image(image_bytes, prompt)
        except Exception as exc:
            fallback = self._fallback_for_prompt(prompt)
            if fallback:
                return fallback
            return f"Request failed: {exc}"

    def _fallback_for_prompt(self, prompt: str) -> str:
        frame = self.camera.get_frame(timeout=1.0)
        if frame is None:
            return ""
        if prompt in {NAVIGATION_PROMPT, SAFETY_SCAN_PROMPT, CROSSING_PROMPT}:
            return basic_navigation_hint(frame)
        if prompt == GENERAL_DESCRIPTION_PROMPT:
            return basic_scene_hint(frame)
        return ""

    def describe_scene(self) -> str:
        return self._with_frame(GENERAL_DESCRIPTION_PROMPT)

    def navigation_help(self) -> str:
        return self._with_frame(NAVIGATION_PROMPT)

    def safety_scan(self) -> str:
        return self._with_frame(SAFETY_SCAN_PROMPT)

    def crossing_help(self) -> str:
        return self._with_frame(CROSSING_PROMPT)

    def read_text(self) -> str:
        return self._with_frame(READ_TEXT_PROMPT)

    def audio_test(self) -> str:
        return "This is a wired headphone audio test."

    def pi_self_test(self) -> str:
        results: list[str] = []

        results.append(f"profile {self.settings.device_profile}")
        results.append(f"camera backend {self.settings.camera_backend}")
        results.append(f"frame {self.settings.frame_width}x{self.settings.frame_height}")
        results.append(f"whisper {self.settings.whisper_model}")

        mic_index = self.transcriber._input_device_index
        if mic_index is None:
            results.append("mic not selected")
        else:
            results.append(f"mic ok index {mic_index}")

        frame = self.camera.get_frame(timeout=1.5)
        if frame is None:
            results.append("camera no frame")
        else:
            height, width = frame.shape[:2]
            results.append(f"camera ok {width}x{height}")

        try:
            self.speaker.say("Self test audio check.")
            results.append("speaker queued")
        except Exception:
            results.append("speaker failed")

        alerts_dir = Path(self.settings.emergency_output_dir)
        if not alerts_dir.is_absolute():
            alerts_dir = Path.cwd() / alerts_dir
        try:
            alerts_dir.mkdir(parents=True, exist_ok=True)
            results.append(f"sos dir ok {alerts_dir}")
        except Exception:
            results.append("sos dir failed")

        try:
            response = self.maps._session.get(
                f"{self.settings.nominatim_base_url}/search",
                params={"q": "bengaluru", "format": "jsonv2", "limit": 1},
                timeout=10,
            )
            if response.ok:
                results.append("maps network ok")
            else:
                results.append(f"maps network http {response.status_code}")
        except Exception:
            results.append("maps network failed")

        live_status = "enabled" if self.settings.enable_live_mode else "disabled"
        results.append(f"live mode {live_status}")
        return "Self test: " + ". ".join(results) + "."

    def find_object(self, target: str) -> str:
        return self._with_frame(object_finding_prompt(target))

    def ask_question(self, question: str) -> str:
        return self._with_frame(scene_question_prompt(question))

    def start_live_mode(self) -> str:
        if self._live_thread and self._live_thread.is_alive():
            return "Live navigation is already running."
        if not self.settings.enable_live_mode:
            return f"Live navigation is disabled in {self.settings.device_profile} mode to keep the device responsive."
        if not self.settings.gemini_live_configured:
            return "Gemini live mode needs at least one Gemini API key."

        self._live_stop.clear()

        def runner() -> None:
            try:
                asyncio.run(
                    self.gemini.live_navigation(
                        self.camera,
                        on_text=self._handle_live_message,
                        stop_event=self._live_stop,
                    )
                )
            except Exception as exc:
                print(f"[live error] {exc}")
                self.speaker.say(f"Live mode stopped. {exc}")

        self._live_thread = threading.Thread(target=runner, daemon=True)
        self._live_thread.start()
        return "Live navigation started."

    def stop_live_mode(self) -> None:
        self._live_stop.set()
        if self._live_thread and self._live_thread.is_alive():
            self._live_thread.join(timeout=1.0)
        self._live_thread = None

    def start_assist_mode(self) -> str:
        if self._assist_thread and self._assist_thread.is_alive():
            return "Continuous assist is already running."

        self._assist_stop.clear()
        self._last_assist_message = ""

        def runner() -> None:
            while not self._assist_stop.is_set():
                if self.speaker.is_speaking:
                    time.sleep(0.5)
                    continue
                try:
                    message = self.safety_scan()
                    cleaned = " ".join(message.split())
                    if cleaned and cleaned != self._last_assist_message:
                        self._last_assist_message = cleaned
                        print(f"[assist] {cleaned}")
                        self.speaker.say(cleaned)
                except Exception as exc:
                    print(f"[assist error] {exc}")
                time.sleep(self.settings.assist_interval_seconds)

        self._assist_thread = threading.Thread(target=runner, daemon=True)
        self._assist_thread.start()
        return "Continuous assist started."

    def stop_assist_mode(self) -> None:
        self._assist_stop.set()
        if self._assist_thread and self._assist_thread.is_alive():
            self._assist_thread.join(timeout=1.0)
        self._assist_thread = None

    def emergency_help(self) -> str:
        route_status = self.maps.route_status()
        route_destination = ""
        if self.maps._active_route:
            route_destination = self.maps._active_route.destination_label
        snapshot = EmergencySnapshot(
            contact_name=self.settings.emergency_contact_name,
            contact_phone=self.settings.emergency_contact_phone,
            saved_location=self.maps._saved_origin,
            route_destination=route_destination,
            route_status="" if route_status == "No active route." else route_status,
            voice_status="on" if self._voice_enabled else "off",
            assist_status="on" if self._assist_thread and self._assist_thread.is_alive() else "off",
            live_status="on" if self._live_thread and self._live_thread.is_alive() else "off",
        )
        report_path = self.emergency.create_report(snapshot)
        parts = ["Emergency mode."]
        if self.settings.emergency_contact_name or self.settings.emergency_contact_phone:
            contact = " ".join(
                piece
                for piece in [self.settings.emergency_contact_name, self.settings.emergency_contact_phone]
                if piece
            )
            parts.append(f"Contact: {contact}.")
        if self.maps._saved_origin:
            parts.append(f"Saved location: {self.maps._saved_origin}.")
        elif self.maps._active_route:
            parts.append(f"Route destination: {self.maps._active_route.destination_label}.")
        else:
            parts.append("No saved location yet.")
        parts.append(f"SOS report saved at {report_path}.")
        parts.append("Say route stop, voice off, or call for nearby help if needed.")
        return " ".join(parts)

    def status_summary(self) -> str:
        assist_state = "on" if self._assist_thread and self._assist_thread.is_alive() else "off"
        live_state = "on" if self._live_thread and self._live_thread.is_alive() else "off"
        voice_state = "on" if self._voice_enabled else "off"
        return f"Voice {voice_state}. Continuous assist {assist_state}. Live mode {live_state}."

    def _handle_live_message(self, text: str) -> None:
        cleaned = " ".join(text.split())
        if cleaned and cleaned != self._last_live_message:
            self._last_live_message = cleaned
            print(f"[live] {cleaned}")
            self.speaker.say(cleaned)

    def ensure_voice_listener(self) -> None:
        if self._voice_thread and self._voice_thread.is_alive():
            return

        self._voice_stop.clear()

        def runner() -> None:
            while not self._voice_stop.is_set():
                if self.speaker.is_speaking:
                    time.sleep(0.5)
                    continue
                try:
                    heard = self.transcriber.listen_progressive()
                except Exception as exc:
                    print(f"[voice error] {exc}")
                    time.sleep(1.0)
                    continue
                if not heard:
                    continue
                print(f"[heard] {heard}")
                try:
                    if self._is_voice_on_phrase(heard):
                        self._voice_enabled = True
                        self.speaker.say("Voice mode on.")
                        continue
                    if self._is_voice_off_phrase(heard):
                        self._voice_enabled = False
                        self._voice_session_active = False
                        self.speaker.say("Voice mode off.")
                        continue
                    if not self._voice_enabled:
                        continue
                    if self._is_session_end_phrase(heard):
                        self._voice_session_active = False
                        self.speaker.say("Session stopped.")
                        continue
                    if not self._voice_session_active:
                        if not self._starts_with_wake_word(heard):
                            continue
                        self._voice_session_active = True
                        command = self._extract_inline_command(heard)
                        if not command:
                            print("[session] listening")
                            continue
                    else:
                        command = self._extract_inline_command(heard, require_wake=False)
                        if self._starts_with_wake_word(heard):
                            command = self._extract_inline_command(heard)
                            if not command:
                                print("[session] listening")
                                continue
                    print(f"[command] {command}")
                    if command:
                        result = self.handle_command(command)
                        if result:
                            print(result)
                            self.speaker.say(result)
                except Exception as exc:
                    print(f"[command error] {exc}")

        self._voice_thread = threading.Thread(target=runner, daemon=True)
        self._voice_thread.start()
    
    def start_voice_mode(self) -> str:
        self.ensure_voice_listener()
        if self._voice_enabled:
            return "Voice mode is already on."
        self._voice_enabled = True
        return f"Voice mode on. Say {self.settings.wake_word} with your command."

    def stop_voice_mode(self) -> None:
        self._voice_enabled = False
        self._voice_session_active = False

    def shutdown_voice_listener(self) -> None:
        self._voice_stop.set()
        if self._voice_thread and self._voice_thread.is_alive():
            self._voice_thread.join(timeout=1.0)
        self._voice_thread = None

    def _strip_wake_word(self, text: str, require_wake: bool = True) -> str:
        lowered = text.strip().lower()
        prefix = f"{self.settings.wake_word} "
        if lowered.startswith(prefix):
            return lowered[len(prefix):].strip()
        if lowered == self.settings.wake_word:
            return ""
        words = lowered.split()
        if words and self._similar(words[0], self.settings.wake_word) >= self.settings.wake_word_similarity:
            return " ".join(words[1:]).strip()
        if not require_wake:
            return lowered
        return lowered

    def _starts_with_wake_word(self, text: str) -> bool:
        lowered = text.strip().lower()
        if lowered == self.settings.wake_word or lowered.startswith(f"{self.settings.wake_word} "):
            return True
        first_word = lowered.split()[0] if lowered.split() else ""
        return bool(first_word) and self._similar(first_word, self.settings.wake_word) >= self.settings.wake_word_similarity

    def _similar(self, a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()

    def _is_voice_on_phrase(self, heard: str) -> bool:
        cleaned = self._strip_wake_word(heard)
        return cleaned in {"voice on", "start voice", "turn voice on"}

    def _is_voice_off_phrase(self, heard: str) -> bool:
        cleaned = self._strip_wake_word(heard)
        return cleaned in {"voice off", "stop voice", "turn voice off"}

    def _is_session_end_phrase(self, heard: str) -> bool:
        cleaned = self._extract_inline_command(heard, require_wake=False)
        return cleaned in {"bye", "goodbye", "bye bye", "stop session", "end session"}

    def _extract_inline_command(self, heard: str, require_wake: bool = True) -> str:
        return self._strip_wake_word(heard, require_wake=require_wake)

    def handle_command(self, command: str) -> str:
        lowered = command.strip().lower()
        normalized = self._normalize_spoken_command(lowered)
        normalized = self._best_simple_command_match(normalized)

        if self._matches_any(normalized, "help", "commands", "what can you do", "all commands"):
            return (
                "Commands: describe, navigate, safety, crossing, read, label, find <item>, ask <question>, "
                "assist on, assist off, live on, live off, set location <place>, route to <place>, route from <origin> to <destination>, "
                "next step, previous step, repeat step, route status, restart route, destination, stop route, "
                "sos, status, audio test, pi self test, voice on, voice off, listen, quit."
            )
        if self._matches_any(
            normalized,
            "describe",
            "scene",
            "describe scene",
            "what is around me",
            "what here",
            "what is here",
            "describe here",
            "tell me scene",
        ):
            return self.describe_scene()
        if self._matches_any(
            normalized,
            "navigate",
            "guide me",
            "obstacles",
            "road",
            "path",
            "help walk",
            "way",
            "show path",
        ):
            return self.navigation_help()
        if self._matches_any(
            normalized,
            "safety",
            "safe",
            "safety check",
            "check safety",
            "danger",
            "hazard",
        ):
            return self.safety_scan()
        if self._matches_any(
            normalized,
            "crossing",
            "road crossing",
            "cross road",
            "can i cross",
        ):
            return self.crossing_help()
        if self._matches_any(
            normalized,
            "read",
            "read text",
            "ocr",
            "read this",
            "text",
            "read here",
            "what is written",
            "label",
            "labels",
        ):
            return self.read_text()
        if normalized.startswith("find "):
            return self.find_object(normalized[5:].strip())
        if normalized.startswith("ask "):
            return self.ask_question(command[4:].strip())
        if self._looks_like_find_command(normalized):
            return self.find_object(self._extract_find_target(normalized))
        if self._looks_like_scene_question(normalized):
            return self.ask_question(normalized)
        if self._matches_any(
            normalized,
            "live on",
            "start live",
            "start navigation",
            "live",
            "start guide",
            "start",
        ):
            return self.start_live_mode()
        if self._matches_any(
            normalized,
            "live off",
            "stop live",
            "stop navigation",
            "stop guide",
        ):
            self.stop_live_mode()
            return "Live navigation stopped."
        if self._matches_any(
            normalized,
            "assist on",
            "start assist",
            "continuous on",
            "smart cane on",
        ):
            return self.start_assist_mode()
        if self._matches_any(
            normalized,
            "assist off",
            "stop assist",
            "continuous off",
            "smart cane off",
        ):
            self.stop_assist_mode()
            return "Continuous assist stopped."
        if normalized.startswith("set location "):
            return self.maps.set_origin(command[len("set location "):].strip())
        if normalized.startswith("route from ") and " to " in normalized:
            body = command[len("route from "):].strip()
            origin, destination = body.split(" to ", 1)
            return self.maps.route_from_to(origin, destination)
        if normalized.startswith(("route to ", "go to ")):
            target = command.split(" ", 2)[2].strip()
            return self.maps.route_to(target)
        if self._matches_any(normalized, "next step", "next", "route next"):
            return self.maps.next_step()
        if self._matches_any(normalized, "previous step", "back step", "route back"):
            return self.maps.previous_step()
        if self._matches_any(normalized, "repeat step", "repeat", "route repeat"):
            return self.maps.repeat_step()
        if self._matches_any(normalized, "route status", "route progress", "progress", "where am i on route"):
            return self.maps.route_status()
        if self._matches_any(normalized, "restart route", "route restart", "start route again"):
            return self.maps.restart_route()
        if self._matches_any(normalized, "destination", "where am i going", "route destination"):
            return self.maps.current_destination()
        if self._matches_any(normalized, "stop route", "route stop", "clear route"):
            return self.maps.stop_route()
        if self._matches_any(normalized, "voice on", "start voice", "voice start"):
            return self.start_voice_mode()
        if self._matches_any(normalized, "voice off", "stop voice", "voice stop"):
            self.stop_voice_mode()
            return "Voice mode stopped."
        if self._matches_any(normalized, "listen", "mic", "microphone", "hear me"):
            heard = self.transcriber.record_and_transcribe()
            return f"I heard: {heard or 'nothing clear'}"
        if self._matches_any(normalized, "sos", "emergency", "help me", "emergency help"):
            return self.emergency_help()
        if self._matches_any(normalized, "status", "mode status", "system status"):
            return self.status_summary()
        if self._matches_any(normalized, "pi self test", "self test", "system test", "hardware test"):
            return self.pi_self_test()
        if self._matches_any(normalized, "audio test", "test audio", "speaker test", "headphone test"):
            return self.audio_test()
        if self._matches_any(normalized, "quit", "exit", "stop app", "close app", "close"):
            raise SystemExit
        return "I did not understand that command."

    def _matches_any(self, text: str, *phrases: str) -> bool:
        return text in set(phrases)

    def _normalize_spoken_command(self, text: str) -> str:
        cleaned = " ".join(text.split())
        if cleaned.startswith("there is any "):
            cleaned = "is there any " + cleaned[len("there is any ") :]
        elif cleaned.startswith("there any "):
            cleaned = "is there any " + cleaned[len("there any ") :]

        replacements = {
            "reed": "read",
            "red": "read",
            "reed text": "read text",
            "lable": "label",
            "lebel": "label",
            "describ": "describe",
            "nay vigate": "navigate",
            "na vigate": "navigate",
            "navigatee": "navigate",
            "micro phone": "microphone",
            "lissen": "listen",
            "any cahir": "any chair",
            "any cahi r": "any chair",
            "cahi r": "chair",
            " hear": " here",
        }
        for old, new in replacements.items():
            cleaned = cleaned.replace(old, new)
        return cleaned.strip()

    def _looks_like_scene_question(self, text: str) -> bool:
        prefixes = (
            "is there ",
            "is there any ",
            "any ",
            "where ",
            "what ",
            "who ",
            "can you see ",
            "do you see ",
            "there is any ",
            "there any ",
        )
        return text.startswith(prefixes)

    def _looks_like_find_command(self, text: str) -> bool:
        return text.startswith(
            (
                "chair here",
                "laptop here",
                "bottle here",
                "person here",
                "door here",
                "chair",
                "laptop",
                "bottle",
                "person",
                "door",
                "phone",
                "bag",
                "table",
            )
        )

    def _extract_find_target(self, text: str) -> str:
        if text.endswith(" here"):
            return text[:-5].strip()
        return text

    def _best_simple_command_match(self, text: str) -> str:
        simple_commands = [
            "help",
            "commands",
            "describe",
            "describe scene",
            "navigate",
            "guide me",
            "safety",
            "read",
            "read text",
            "assist on",
            "assist off",
            "previous step",
            "repeat step",
            "route status",
            "live on",
            "live off",
            "status",
            "sos",
            "pi self test",
            "voice on",
            "voice off",
            "voice start",
            "voice stop",
            "listen",
            "quit",
        ]
        best = text
        best_score = 0.0
        for command in simple_commands:
            score = self._similar(text, command)
            if score > best_score:
                best = command
                best_score = score
        if best_score >= self.settings.command_similarity and len(text.split()) <= 3:
            return best
        return text


def main() -> None:
    settings = Settings()
    app = BlindAssistApp(settings)
    app.start()

    print("Blind Assist CLI")
    print("Type help for commands.")
    if not settings.configured:
        print("Gemini API key not found. Create a .env file with GEMINI_API_KEY=your_key")

    try:
        while True:
            try:
                command = input("> ").strip()
            except EOFError:
                time.sleep(0.5)
                continue
            if not command:
                continue
            result = app.handle_command(command)
            if result:
                print(result)
                app.speaker.say(result)
    except (KeyboardInterrupt, SystemExit):
        print("Shutting down.")
    finally:
        app.stop()
