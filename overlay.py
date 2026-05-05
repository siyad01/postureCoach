import cv2
import numpy as np
from analyzer import PostureResult
from config import config


# ── Color palette (BGR) ───────────────────────────────────
class C:
    GREEN   = (80, 220, 120)
    RED     = (70, 80, 240)
    YELLOW  = (60, 200, 240)
    WHITE   = (240, 240, 248)
    BLACK   = (0, 0, 0)
    GRAY    = (120, 120, 130)
    DARK    = (20, 20, 30)
    SK_GOOD = (80, 220, 120)
    SK_BAD  = (80, 100, 240)


def _text(frame, msg, x, y,
          color=C.WHITE, scale=0.45, thick=1, shadow=True):
    font = cv2.FONT_HERSHEY_SIMPLEX
    if shadow:
        cv2.putText(frame, msg, (x+1, y+1),
                    font, scale, C.BLACK, thick+1, cv2.LINE_AA)
    cv2.putText(frame, msg, (x, y),
                font, scale, color, thick, cv2.LINE_AA)


def _alpha_rect(frame, x1, y1, x2, y2, color, alpha=0.75):
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return
    solid   = np.full_like(roi, color)
    blended = cv2.addWeighted(solid, alpha, roi, 1 - alpha, 0)
    frame[y1:y2, x1:x2] = blended


def _bar(frame, x, y, w, h, val, maxv, fg):
    cv2.rectangle(frame, (x, y), (x+w, y+h), (30, 30, 40), -1)
    fill = int(np.clip(val / maxv, 0, 1) * w)
    if fill > 2:
        cv2.rectangle(frame, (x, y), (x+fill, y+h), fg, -1)
    cv2.rectangle(frame, (x, y), (x+w, y+h), C.GRAY, 1)


# ── Pose skeleton connections ─────────────────────────────
_CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24), (23, 25), (25, 27),
    (24, 26), (26, 28), (0, 11),  (0, 12),
]


def draw_skeleton(frame, landmarks, result: PostureResult):
    """
    Draw pose skeleton on frame.
    Green = good posture, Red = bad posture.
    Called by both app.py (GUI) and posturecoach.py (CLI).
    """
    if not landmarks or not config.display.show_skeleton:
        return

    h, w    = frame.shape[:2]
    sk_col  = C.SK_GOOD if result.is_good else C.SK_BAD
    dim_col = tuple(max(0, c // 3) for c in sk_col)

    # Draw bones
    for a, b in _CONNECTIONS:
        la, lb = landmarks[a], landmarks[b]
        if la.visibility < config.posture.min_visibility:
            continue
        if lb.visibility < config.posture.min_visibility:
            continue
        x1, y1 = int(la.x * w), int(la.y * h)
        x2, y2 = int(lb.x * w), int(lb.y * h)
        # thick dim glow + thin bright line = modern look
        cv2.line(frame, (x1, y1), (x2, y2), dim_col, 4, cv2.LINE_AA)
        cv2.line(frame, (x1, y1), (x2, y2), sk_col,  1, cv2.LINE_AA)

    # Draw joints
    for idx in [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]:
        lm = landmarks[idx]
        if lm.visibility < config.posture.min_visibility:
            continue
        x, y = int(lm.x * w), int(lm.y * h)
        cv2.circle(frame, (x, y), 5, dim_col, -1)
        cv2.circle(frame, (x, y), 3, C.WHITE,  -1)


def draw_no_detection(frame):
    """
    Shown when MediaPipe finds no person in frame.
    Called by both app.py and posturecoach.py.
    """
    h, w = frame.shape[:2]
    _alpha_rect(frame, 0, 0, w, 38, C.DARK, 0.82)
    _text(frame,
          "Move back — show shoulders",
          8, 24, C.YELLOW, 0.45, 1)


# ── CLI overlay (used by posturecoach.py only) ────────────
def draw_cli_hud(frame, result: PostureResult,
                 bad_duration: float = 0.0,
                 show_alert: bool = False,
                 session_good_pct: float = 0.0):
    """
    Full HUD drawn onto the OpenCV window.
    Only used by the CLI fallback (posturecoach.py).
    The GUI app (app.py) draws its own UI with CustomTkinter.
    """
    h, w = frame.shape[:2]

    # ── Top bar ───────────────────────────────────────────
    bar_h   = 44
    bg_col  = (10, 35, 15) if result.is_good else (35, 12, 15)
    _alpha_rect(frame, 0, 0, w, bar_h, bg_col, 0.88)
    accent = C.GREEN if result.is_good else C.RED
    cv2.line(frame, (0, bar_h), (w, bar_h), accent, 1)

    # Score
    sc_col = C.GREEN  if result.score >= 75 else \
             C.YELLOW if result.score >= 50 else C.RED
    _text(frame, str(result.score), 10, 30, sc_col, 0.9, 2)
    _bar(frame, 48, 14, 75, 8, result.score, 100, sc_col)

    # Mode
    mode = "DESK" if result.mode == "sitting" else "FULL"
    _text(frame, mode, 132, 20, C.GRAY, 0.35, 1, shadow=False)

    # Session good %
    _bar(frame, 132, 28, 60, 6, session_good_pct, 100, C.GREEN)
    _text(frame, f"{session_good_pct:.0f}%",
          132, 40, C.GRAY, 0.30, 1, shadow=False)

    # Status right
    if result.is_good:
        _text(frame, "GOOD", w - 58, 26, C.GREEN, 0.55, 2)
    elif bad_duration > 0:
        t_col = C.RED if bad_duration > 5 else C.YELLOW
        _text(frame, f"{bad_duration:.0f}s",
              w - 44, 26, t_col, 0.6, 2)

    # B/S/N indicator dots
    labels  = ["B", "S", "N"]
    vals    = [result.back_angle,
               result.shoulder_tilt,
               result.neck_angle]
    threshs = [config.posture.back_angle_threshold,
               config.posture.shoulder_tilt_threshold,
               config.posture.neck_angle_threshold]
    for i, (lbl, val, thr) in enumerate(zip(labels, vals, threshs)):
        dx  = w - 70 + i * 22
        col = C.GREEN if val <= thr else C.RED
        cv2.circle(frame, (dx, 10), 7, col, -1)
        cv2.circle(frame, (dx, 10), 7, C.DARK, 1)
        _text(frame, lbl, dx - 4, 14,
              C.WHITE, 0.28, 1, shadow=False)

    # ── Bottom feedback bar ───────────────────────────────
    _alpha_rect(frame, 0, h - 28, w, h,
                (8, 25, 10) if result.is_good else (30, 10, 12),
                0.80)
    cv2.line(frame, (0, h - 28), (w, h - 28), accent, 1)

    if result.is_good:
        _text(frame, "✓  Great posture!", 8, h - 8,
              C.GREEN, 0.42, 1)
    else:
        msg = result.feedback[0] if result.feedback else ""
        _text(frame, f"↑  {msg}", 8, h - 8,
              C.YELLOW, 0.40, 1)

    # ── Alert flash ───────────────────────────────────────
    if show_alert:
        cv2.rectangle(frame, (0, 0), (w-1, h-1), C.RED, 4)
        _alpha_rect(frame,
                    w//2 - 130, h//2 - 22,
                    w//2 + 130, h//2 + 18,
                    (40, 10, 10), 0.90)
        _text(frame,
              f"SIT STRAIGHT  •  {bad_duration:.0f}s",
              w//2 - 122, h//2 + 6, C.RED, 0.55, 2)


# ── Unified entry point ───────────────────────────────────
def draw_frame(frame, landmarks, result: PostureResult | None,
               bad_duration: float = 0.0,
               show_alert: bool = False,
               session_good_pct: float = 0.0):
    """
    Master draw function for CLI mode (posturecoach.py).
    GUI mode (app.py) calls draw_skeleton directly.
    """
    if result is None:
        draw_no_detection(frame)
        return

    draw_skeleton(frame, landmarks, result)
    draw_cli_hud(frame, result,
                 bad_duration, show_alert, session_good_pct)