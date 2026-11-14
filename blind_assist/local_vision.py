from __future__ import annotations

import cv2
import numpy as np


def _edge_density(frame) -> tuple[float, float, float]:
    height, width = frame.shape[:2]
    lower = frame[int(height * 0.45) :, :]
    gray = cv2.cvtColor(lower, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 60, 160)

    third = width // 3
    left = edges[:, :third]
    center = edges[:, third : third * 2]
    right = edges[:, third * 2 :]

    def density(region) -> float:
        if region.size == 0:
            return 0.0
        return float(np.count_nonzero(region)) / float(region.size)

    return density(left), density(center), density(right)


def basic_navigation_hint(frame) -> str:
    left, center, right = _edge_density(frame)
    busiest = max(left, center, right)
    safest_side = "left" if left < right else "right"

    if center > 0.12:
        if abs(left - right) < 0.02:
            return "AI is unavailable. Basic check suggests something may block the path ahead."
        return f"AI is unavailable. Basic check suggests the path ahead may be blocked. {safest_side.title()} side looks a little clearer."
    if busiest < 0.04:
        return "AI is unavailable. Basic check suggests the path ahead looks mostly clear."
    if left > right + 0.03:
        return "AI is unavailable. Basic check suggests the left side is more crowded than the right."
    if right > left + 0.03:
        return "AI is unavailable. Basic check suggests the right side is more crowded than the left."
    return "AI is unavailable. Basic check suggests no strong obstacle directly ahead."


def basic_scene_hint(frame) -> str:
    height, width = frame.shape[:2]
    brightness = float(np.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)))
    if brightness < 45:
        light_text = "The scene looks quite dark."
    elif brightness > 180:
        light_text = "The scene looks very bright."
    else:
        light_text = "The scene has moderate lighting."

    return f"{light_text} {basic_navigation_hint(frame)}"
