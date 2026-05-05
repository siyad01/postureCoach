from pydantic import BaseModel
from pathlib import Path
import os
import sys


# Works both when running as script AND as packaged .exe
if getattr(sys, 'frozen', False):
    # PyInstaller bundle — files extracted to _MEIPASS
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent

MODEL_PATH = BASE_DIR / "pose_landmarker_full.task"

# Logs always go next to the exe/script, never in _MEIPASS
if getattr(sys, 'frozen', False):
    LOG_DIR = Path(sys.executable).parent / "logs"
else:
    LOG_DIR = Path(__file__).parent / "logs"

LOG_DIR.mkdir(exist_ok=True)


class PostureConfig(BaseModel):
    # ── Neck angle ────────────────────────────────────────
    # 2D pixel space — ear horizontal offset from shoulder
    # scaled to 0-60 range. 15 = moderate forward lean
    neck_angle_threshold: float = 18.0

    # ── Shoulder tilt ─────────────────────────────────────
    # Percentage of shoulder width — 12 = noticeable tilt
    shoulder_tilt_threshold: float = 18.0

    # ── Back / head forward ───────────────────────────────
    # Nose drop below shoulder line, scaled 0-30+
    # 8 = head clearly tilted down toward screen
    back_angle_threshold: float = 8.0

    # ── Alert timing ──────────────────────────────────────
    # How long bad posture must persist before alerting
    alert_delay_seconds: int = 5

    # How long between repeated alerts
    alert_repeat_seconds: int = 120

    # ── Landmark visibility ───────────────────────────────
    # Minimum confidence to use a landmark (0.0-1.0)
    # 0.35 is good for sitting — lower than standing
    min_visibility: float = 0.35


class CameraConfig(BaseModel):
    camera_index: int = 0
    width:  int = 1280
    height: int = 720
    fps:    int = 30


class DisplayConfig(BaseModel):
    show_skeleton: bool = True
    show_angles:   bool = True
    show_score:    bool = True
    window_title:  str  = "PostureCoach"


class Config(BaseModel):
    posture: PostureConfig = PostureConfig()
    camera:  CameraConfig  = CameraConfig()
    display: DisplayConfig = DisplayConfig()


# Single instance imported everywhere
config = Config()