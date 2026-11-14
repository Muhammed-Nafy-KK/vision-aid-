from __future__ import annotations

import threading
import time
from typing import Optional

import cv2

from .config import Settings


class CameraStream:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._capture: Optional[cv2.VideoCapture] = None
        self._frame = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._capture = self._open_capture()
        if not self._capture or not self._capture.isOpened():
            raise RuntimeError(
                f"Could not open camera index {self.settings.camera_index}. "
                "Check that your camera is connected and not in use by another app."
            )
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.settings.frame_width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.settings.frame_height)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        backend = self.settings.camera_backend
        backend_codes: list[int | None]
        if backend == "dshow":
            backend_codes = [getattr(cv2, "CAP_DSHOW", None), None]
        elif backend == "v4l2":
            backend_codes = [getattr(cv2, "CAP_V4L2", None), None]
        elif backend == "any":
            backend_codes = [None]
        else:
            backend_codes = [getattr(cv2, "CAP_DSHOW", None), getattr(cv2, "CAP_V4L2", None), None]

        for code in backend_codes:
            capture = cv2.VideoCapture(self.settings.camera_index, code) if code is not None else cv2.VideoCapture(self.settings.camera_index)
            if capture and capture.isOpened():
                return capture
            if capture:
                capture.release()
        return None

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            if self._capture is None:
                time.sleep(0.1)
                continue
            ok, frame = self._capture.read()
            if ok:
                with self._lock:
                    self._frame = frame.copy()
            time.sleep(self.settings.camera_read_interval_seconds)

    def get_frame(self, timeout: float = 2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self._frame is not None:
                    return self._frame.copy()
            time.sleep(0.05)
        return None

    def get_jpeg_bytes(self, timeout: float = 2.0) -> bytes | None:
        frame = self.get_frame(timeout=timeout)
        if frame is None:
            return None
        ok, buffer = cv2.imencode(".jpg", frame)
        if not ok:
            return None
        return buffer.tobytes()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self._capture is not None:
            self._capture.release()
            self._capture = None
