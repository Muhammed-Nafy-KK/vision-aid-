from __future__ import annotations

import queue
import subprocess
import sys
import threading

import pyttsx3
import sounddevice as sd
import speech_recognition as sr

from .config import Settings


class Speaker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._queue: queue.Queue[str] = queue.Queue()
        self._speaking = threading.Event()
        self._enabled = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", self.settings.tts_rate)
        except Exception as exc:
            self._enabled = False
            print(f"[tts disabled] {exc}")
            while True:
                text = self._queue.get()
                print(f"[speak disabled] {text}")
        while True:
            text = self._queue.get()
            self._speaking.set()
            try:
                for chunk in self._split_for_speech(text):
                    print(f"[speak] {chunk}")
                    self._speak_with_windows_tts(chunk, self.settings.tts_rate)
            finally:
                self._speaking.clear()

    def _speak_with_windows_tts(self, text: str, tts_rate: int) -> None:
        try:
            self._speak_in_subprocess(text, tts_rate)
        except Exception as exc:
            print(f"[audio output warning] {exc}")

    def _split_for_speech(self, text: str) -> list[str]:
        cleaned = " ".join(text.split())
        if len(cleaned) <= 140:
            return [cleaned]
        parts: list[str] = []
        current = ""
        for sentence in cleaned.replace("?", ".").replace("!", ".").split("."):
            sentence = sentence.strip()
            if not sentence:
                continue
            candidate = sentence if not current else f"{current}. {sentence}"
            if len(candidate) > 140 and current:
                parts.append(current + ".")
                current = sentence
            else:
                current = candidate
        if current:
            parts.append(current + ".")
        return parts or [cleaned]

    def _speak_in_subprocess(self, text: str, tts_rate: int) -> None:
        script = (
            "import sys, pyttsx3; "
            "text=sys.argv[1]; rate=int(sys.argv[2]); "
            "engine=pyttsx3.init(); engine.setProperty('rate', rate); "
            "engine.say(text); engine.runAndWait()"
        )
        subprocess.run(
            [sys.executable, "-c", script, text, str(tts_rate)],
            check=True,
            timeout=30,
        )

    def say(self, text: str) -> None:
        cleaned = " ".join(text.split())
        if cleaned:
            self._queue.put(cleaned)

    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set()


class Transcriber:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._recognizer = sr.Recognizer()
        self._recognizer.dynamic_energy_threshold = True
        self._recognizer.pause_threshold = self.settings.pause_threshold
        self._recognizer.non_speaking_duration = self.settings.non_speaking_duration
        self._recognizer.phrase_threshold = self.settings.phrase_threshold
        self._input_device_index = self._select_input_device()
        self._calibrated = False

    def _select_input_device(self) -> int | None:
        try:
            devices = sr.Microphone.list_microphone_names()
        except Exception as exc:
            print(f"[audio input warning] {exc}")
            return None

        for keyword in self.settings.preferred_input_keywords:
            for index, device in enumerate(devices):
                name = device.lower()
                if any(blocked in name for blocked in self.settings.excluded_input_keywords):
                    continue
                if keyword in name:
                    print(f"[audio input] using {device}")
                    return index

        for index, device in enumerate(devices):
            name = device.lower()
            if any(blocked in name for blocked in self.settings.excluded_input_keywords):
                continue
            print(f"[audio input] using {device}")
            return index
        return None

    def _microphone(self) -> sr.Microphone:
        return sr.Microphone(
            device_index=self._input_device_index,
            sample_rate=self.settings.sample_rate,
        )

    def record_and_transcribe(self, duration: float | None = None) -> str:
        duration = duration or self.settings.command_record_seconds
        try:
            with self._microphone() as source:
                if not self._calibrated:
                    self._recognizer.adjust_for_ambient_noise(
                        source,
                        duration=self.settings.ambient_adjust_seconds,
                    )
                    self._calibrated = True
                audio = self._recognizer.listen(
                    source,
                    timeout=self.settings.listen_timeout_seconds,
                    phrase_time_limit=duration,
                )
            text = self._recognizer.recognize_faster_whisper(
                audio,
                model=self.settings.whisper_model,
                beam_size=self.settings.whisper_beam_size,
                init_options={
                    "device": "cpu",
                    "compute_type": "int8",
                },
                vad_filter=True,
                condition_on_previous_text=False,
            )
            return text.lower().strip()
        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            return ""

    def listen_progressive(self) -> str:
        # SpeechRecognition keeps listening once speech starts, until pause or max phrase length.
        return self.record_and_transcribe(duration=self.settings.extended_listen_seconds)
