from __future__ import annotations

import asyncio
import base64
import threading
from typing import Callable
from typing import Iterable

import requests
from google import genai
from google.genai import errors
from google.genai import types

from .camera import CameraStream
from .config import Settings
from .prompts import LIVE_SYSTEM_PROMPT


class GeminiService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._gemini_clients = [genai.Client(api_key=key) for key in self.settings.gemini_api_keys]

    def require_client(self) -> genai.Client:
        if not self._gemini_clients:
            raise RuntimeError("Gemini API key missing. Put it in GEMINI_API_KEY inside a .env file.")
        return self._gemini_clients[0]

    def _candidate_models(self) -> list[str]:
        candidates = [self.settings.gemini_model, *self.settings.gemini_fallback_models]
        unique: list[str] = []
        for model in candidates:
            if model and model not in unique:
                unique.append(model)
        return unique

    def _is_retryable_model_error(self, exc: Exception) -> bool:
        text = str(exc)
        return any(
            marker in text
            for marker in [
                "503",
                "UNAVAILABLE",
                "429",
                "RESOURCE_EXHAUSTED",
                "quota",
                "rate limit",
                "retry",
            ]
        )

    def _provider_sequence(self) -> Iterable[str]:
        for provider in self.settings.provider_order:
            if provider == "gemini" and self.settings.gemini_api_keys:
                yield provider
            if provider == "openai" and self.settings.openai_api_keys:
                yield provider
            if provider == "deepseek" and self.settings.deepseek_api_keys:
                yield provider

    def analyze_image(self, image_bytes: bytes, prompt: str) -> str:
        provider_failures: list[str] = []
        last_error: Exception | None = None

        for provider in self._provider_sequence():
            try:
                if provider == "gemini":
                    return self._analyze_with_gemini(image_bytes, prompt)
                if provider == "openai":
                    return self._analyze_with_openai_compatible(
                        image_bytes=image_bytes,
                        prompt=prompt,
                        api_keys=self.settings.openai_api_keys,
                        base_url=self.settings.openai_base_url,
                        model=self.settings.openai_vision_model,
                        provider_name="openai",
                    )
                if provider == "deepseek":
                    if not self.settings.deepseek_vision_model:
                        provider_failures.append("deepseek(no vision model configured)")
                        continue
                    return self._analyze_with_openai_compatible(
                        image_bytes=image_bytes,
                        prompt=prompt,
                        api_keys=self.settings.deepseek_api_keys,
                        base_url=self.settings.deepseek_base_url,
                        model=self.settings.deepseek_vision_model,
                        provider_name="deepseek",
                    )
            except Exception as exc:
                provider_failures.append(f"{provider}({exc})")
                last_error = exc
                continue

        if provider_failures:
            raise RuntimeError(
                "All configured providers failed: " + "; ".join(provider_failures)
            ) from last_error
        if last_error is not None:
            raise last_error
        raise RuntimeError("No configured provider was available.")

    def _analyze_with_gemini(self, image_bytes: bytes, prompt: str) -> str:
        unavailable_models: list[str] = []
        last_error: Exception | None = None

        for client in self._gemini_clients:
            for model_name in self._candidate_models():
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[
                            types.Content(
                                role="user",
                                parts=[
                                    types.Part.from_text(text=prompt),
                                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                                ],
                            )
                        ],
                    )
                    text = (response.text or "").strip()
                    if model_name != self.settings.gemini_model:
                        print(f"[gemini fallback] used {model_name}")
                    return text
                except (errors.ServerError, errors.ClientError) as exc:
                    last_error = exc
                    if self._is_retryable_model_error(exc):
                        unavailable_models.append(model_name)
                        continue
                    raise

        if unavailable_models:
            raise RuntimeError(
                "Gemini is temporarily unavailable for these models: "
                + ", ".join(sorted(set(unavailable_models)))
                + "."
            ) from last_error
        if last_error is not None:
            raise last_error
        raise RuntimeError("Gemini request failed before a model could be used.")

    def _analyze_with_openai_compatible(
        self,
        *,
        image_bytes: bytes,
        prompt: str,
        api_keys: list[str],
        base_url: str,
        model: str,
        provider_name: str,
    ) -> str:
        if not api_keys:
            raise RuntimeError(f"{provider_name} API key missing.")
        image_url = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")
        last_error: Exception | None = None
        failures: list[str] = []

        for api_key in api_keys:
            try:
                response = requests.post(
                    base_url.rstrip("/") + "/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {"type": "image_url", "image_url": {"url": image_url}},
                                ],
                            }
                        ],
                        "max_tokens": 180,
                        "temperature": 0.2,
                    },
                    timeout=45,
                )
                if response.status_code >= 400:
                    raise RuntimeError(f"{provider_name} {response.status_code}: {response.text[:300]}")
                payload = response.json()
                text = payload["choices"][0]["message"]["content"].strip()
                print(f"[provider fallback] used {provider_name}:{model}")
                return text
            except Exception as exc:
                last_error = exc
                failures.append(str(exc))
                continue

        raise RuntimeError(f"{provider_name} failed: {' | '.join(failures[:2])}") from last_error

    async def live_navigation(
        self,
        camera: CameraStream,
        on_text: Callable[[str], None],
        stop_event: threading.Event,
    ) -> None:
        client = self.require_client()
        config = types.LiveConnectConfig(
            response_modalities=["TEXT"],
            system_instruction=LIVE_SYSTEM_PROMPT,
        )
        async with client.aio.live.connect(model=self.settings.gemini_live_model, config=config) as session:
            while not stop_event.is_set():
                image_bytes = camera.get_jpeg_bytes(timeout=2.0)
                if not image_bytes:
                    await asyncio.sleep(0.5)
                    continue
                await session.send_realtime_input(
                    video=types.Blob(mime_type="image/jpeg", data=image_bytes)
                )

                parts: list[str] = []
                async for message in session.receive():
                    if getattr(message, "text", None):
                        parts.append(message.text)
                    server_content = getattr(message, "server_content", None)
                    if server_content and getattr(server_content, "model_turn", None):
                        for part in server_content.model_turn.parts or []:
                            if getattr(part, "text", None):
                                parts.append(part.text)
                    if server_content and getattr(server_content, "turn_complete", False):
                        break

                text = " ".join(piece.strip() for piece in parts if piece and piece.strip())
                if text:
                    on_text(text)
                await asyncio.sleep(self.settings.live_interval_seconds)
