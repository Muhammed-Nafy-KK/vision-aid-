from __future__ import annotations

import os
from dataclasses import dataclass
from dataclasses import field

from dotenv import load_dotenv


load_dotenv()

_RAW_DEVICE_PROFILE = os.getenv("DEVICE_PROFILE", "pc").strip().lower()


def _csv_env(*names: str) -> list[str]:
    values: list[str] = []
    for name in names:
        raw = os.getenv(name, "")
        if not raw:
            continue
        for item in raw.split(","):
            cleaned = item.strip()
            if cleaned and cleaned not in values:
                values.append(cleaned)
    return values


def _profile_default(pc: str, *, pi3: str | None = None, pi4: str | None = None, pi5: str | None = None) -> str:
    defaults = {
        "pc": pc,
        "pi3": pi3 or pc,
        "pi3b+": pi3 or pc,
        "pi4": pi4 or pi3 or pc,
        "pi5": pi5 or pi4 or pi3 or pc,
    }
    return defaults.get(_RAW_DEVICE_PROFILE, pc)


def _env_or_profile(name: str, pc: str, *, pi3: str | None = None, pi4: str | None = None, pi5: str | None = None) -> str:
    return os.getenv(name, _profile_default(pc, pi3=pi3, pi4=pi4, pi5=pi5))


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    device_profile: str = _RAW_DEVICE_PROFILE
    gemini_api_key: str = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
    gemini_api_keys: list[str] = field(
        default_factory=lambda: _csv_env("GEMINI_API_KEYS", "GEMINI_API_KEY", "GOOGLE_API_KEY")
    )
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_fallback_models: list[str] = field(
        default_factory=lambda: [
            model.strip()
            for model in os.getenv(
                "GEMINI_FALLBACK_MODELS",
                "gemini-2.0-flash,gemini-2.0-flash-lite,gemini-flash-latest",
            ).split(",")
            if model.strip()
        ]
    )
    gemini_live_model: str = os.getenv("GEMINI_LIVE_MODEL", "gemini-live-2.5-flash-preview")
    openai_api_keys: list[str] = field(default_factory=lambda: _csv_env("OPENAI_API_KEYS", "OPENAI_API_KEY"))
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    openai_vision_model: str = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini").strip()
    deepseek_api_keys: list[str] = field(default_factory=lambda: _csv_env("DEEPSEEK_API_KEYS", "DEEPSEEK_API_KEY"))
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").strip()
    deepseek_vision_model: str = os.getenv("DEEPSEEK_VISION_MODEL", "").strip()
    provider_order: list[str] = field(
        default_factory=lambda: [
            provider.strip().lower()
            for provider in os.getenv("PROVIDER_ORDER", "gemini,openai,deepseek").split(",")
            if provider.strip()
        ]
    )
    nominatim_base_url: str = os.getenv("NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org").strip().rstrip("/")
    osrm_base_url: str = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org").strip().rstrip("/")
    nominatim_countrycodes: str = os.getenv("NOMINATIM_COUNTRYCODES", "in").strip().lower()
    nominatim_contact_email: str = os.getenv("NOMINATIM_CONTACT_EMAIL", "").strip()
    nominatim_user_agent: str = os.getenv("NOMINATIM_USER_AGENT", "BlindAssist/1.0").strip()
    camera_index: int = int(os.getenv("CAMERA_INDEX", "0"))
    camera_backend: str = os.getenv("CAMERA_BACKEND", _profile_default("auto", pi3="v4l2", pi4="v4l2", pi5="v4l2")).strip().lower()
    frame_width: int = int(_env_or_profile("FRAME_WIDTH", "640", pi3="320", pi4="640", pi5="640"))
    frame_height: int = int(_env_or_profile("FRAME_HEIGHT", "480", pi3="240", pi4="480", pi5="480"))
    camera_read_interval_seconds: float = float(
        _env_or_profile("CAMERA_READ_INTERVAL_SECONDS", "0.03", pi3="0.08", pi4="0.05", pi5="0.04")
    )
    live_interval_seconds: float = float(_env_or_profile("LIVE_INTERVAL_SECONDS", "2.5", pi3="5.0", pi4="3.5", pi5="2.5"))
    assist_interval_seconds: float = float(_env_or_profile("ASSIST_INTERVAL_SECONDS", "3.0", pi3="4.5", pi4="3.5", pi5="3.0"))
    whisper_model: str = _env_or_profile("WHISPER_MODEL", "base", pi3="tiny", pi4="base", pi5="base").strip()
    whisper_beam_size: int = int(_env_or_profile("WHISPER_BEAM_SIZE", "3", pi3="1", pi4="2", pi5="3"))
    sample_rate: int = int(os.getenv("SAMPLE_RATE", "16000"))
    initial_listen_seconds: float = float(os.getenv("INITIAL_LISTEN_SECONDS", "2.2"))
    extended_listen_seconds: float = float(os.getenv("EXTENDED_LISTEN_SECONDS", "3.8"))
    command_record_seconds: float = float(_env_or_profile("COMMAND_RECORD_SECONDS", "4", pi3="5", pi4="4.5", pi5="4"))
    ambient_adjust_seconds: float = float(os.getenv("AMBIENT_ADJUST_SECONDS", "0.6"))
    listen_timeout_seconds: float = float(os.getenv("LISTEN_TIMEOUT_SECONDS", "3.0"))
    pause_threshold: float = float(os.getenv("PAUSE_THRESHOLD", "0.8"))
    non_speaking_duration: float = float(os.getenv("NON_SPEAKING_DURATION", "0.3"))
    phrase_threshold: float = float(os.getenv("PHRASE_THRESHOLD", "0.2"))
    wake_word: str = os.getenv("WAKE_WORD", "hi")
    wake_word_similarity: float = float(os.getenv("WAKE_WORD_SIMILARITY", "0.72"))
    command_similarity: float = float(os.getenv("COMMAND_SIMILARITY", "0.76"))
    tts_rate: int = int(os.getenv("TTS_RATE", "180"))
    preferred_output_name: str = os.getenv("PREFERRED_OUTPUT_NAME", "").strip().lower()
    preferred_output_keywords: list[str] = field(
        default_factory=lambda: [
            keyword.strip().lower()
            for keyword in os.getenv(
                "PREFERRED_OUTPUT_KEYWORDS",
                "headphone,headset,airpods,earphone,bluetooth",
            ).split(",")
            if keyword.strip()
        ]
    )
    excluded_output_keywords: list[str] = field(
        default_factory=lambda: [
            keyword.strip().lower()
            for keyword in os.getenv(
                "EXCLUDED_OUTPUT_KEYWORDS",
                "bluetooth,airpods,hands-free,headset",
            ).split(",")
            if keyword.strip()
        ]
    )
    preferred_input_keywords: list[str] = field(
        default_factory=lambda: [
            keyword.strip().lower()
            for keyword in os.getenv(
                "PREFERRED_INPUT_KEYWORDS",
                "usb2.0 device,usb microphone,usb mic,microphone",
            ).split(",")
            if keyword.strip()
        ]
    )
    excluded_input_keywords: list[str] = field(
        default_factory=lambda: [
            keyword.strip().lower()
            for keyword in os.getenv(
                "EXCLUDED_INPUT_KEYWORDS",
                "logitech,webcam,c925,c920",
            ).split(",")
            if keyword.strip()
        ]
    )
    emergency_contact_name: str = os.getenv("EMERGENCY_CONTACT_NAME", "").strip()
    emergency_contact_phone: str = os.getenv("EMERGENCY_CONTACT_PHONE", "").strip()
    emergency_output_dir: str = os.getenv("EMERGENCY_OUTPUT_DIR", "alerts").strip()
    enable_live_mode: bool = _bool_env("ENABLE_LIVE_MODE", _RAW_DEVICE_PROFILE not in {"pi3", "pi3b+"})
    profile_override_defaults: bool = _bool_env("PROFILE_OVERRIDE_DEFAULTS", True)

    def __post_init__(self) -> None:
        profile = self.device_profile
        if not self.profile_override_defaults:
            return

        if profile in {"pi3", "pi3b+"}:
            if self.camera_backend == "auto":
                self.camera_backend = "v4l2"
            if self.frame_width == 640 and self.frame_height == 480:
                self.frame_width = 320
                self.frame_height = 240
            if self.camera_read_interval_seconds == 0.03:
                self.camera_read_interval_seconds = 0.08
            if self.live_interval_seconds == 2.5:
                self.live_interval_seconds = 5.0
            if self.assist_interval_seconds == 3.0:
                self.assist_interval_seconds = 4.5
            if self.whisper_model == "base":
                self.whisper_model = "tiny"
            if self.whisper_beam_size == 3:
                self.whisper_beam_size = 1
            if self.command_record_seconds == 4:
                self.command_record_seconds = 5.0
            if os.getenv("ENABLE_LIVE_MODE") is None:
                self.enable_live_mode = False

        if profile == "pi4":
            if self.camera_backend == "auto":
                self.camera_backend = "v4l2"
            if self.camera_read_interval_seconds == 0.03:
                self.camera_read_interval_seconds = 0.05
            if self.live_interval_seconds == 2.5:
                self.live_interval_seconds = 3.5
            if self.assist_interval_seconds == 3.0:
                self.assist_interval_seconds = 3.5
            if self.whisper_beam_size == 3:
                self.whisper_beam_size = 2

    @property
    def configured(self) -> bool:
        return bool(self.gemini_api_keys or self.openai_api_keys or self.deepseek_api_keys)

    @property
    def gemini_live_configured(self) -> bool:
        return bool(self.gemini_api_keys) and self.enable_live_mode
