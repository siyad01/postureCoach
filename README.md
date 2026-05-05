<div align="center">

# 🧘 PostureCoach

**Real-time AI posture monitor that lives on your desktop**

[![Build](https://github.com/siyad01/postureCoach/actions/workflows/build.yml/badge.svg)](https://github.com/siyad01/postureCoach/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue)](#download)

</div>

---

## What it does

PostureCoach watches you through your webcam while you work. When you slouch or drop your head for more than 5 seconds, it speaks to you in plain English and sends a notification. When your posture is great for 5 minutes straight, it congratulates you.

It runs as a small floating window that stays on top of everything — just like your system clock.

```
Good posture  →  score 90+  →  green overlay  →  silent
Bad posture   →  5 seconds  →  voice alert + notification
Good streak   →  5 minutes  →  voice encouragement
```

## Download

| Platform | Download | Size |
|----------|----------|------|
| **Windows 10/11** | [PostureCoach.exe](../../releases/latest) | ~200MB |
| **macOS** | [PostureCoach-macOS.zip](../../releases/latest) | ~200MB |
| **Linux** | [PostureCoach](../../releases/latest) | ~200MB |

No Python needed. Just download and run.

## How to run

**Windows:** Double-click `PostureCoach.exe`

**macOS:**
```bash
unzip PostureCoach-macOS.zip
open PostureCoach
# If blocked: System Preferences → Security → Open Anyway
```

**Linux:**
```bash
chmod +x PostureCoach
./PostureCoach
# Install espeak if voice doesn't work: sudo apt install espeak
```

## Camera setup

For best detection sit so your **full shoulders are visible** in the camera. The app automatically switches between:

- **DESK mode** — detects from shoulders up (laptop use)
- **FULL BODY mode** — detects full spine when hips are visible

## How it works

```
Webcam frame
    │
    ▼
MediaPipe Pose Landmarker
    │  33 body landmarks detected
    ▼
Posture Analyzer (2D pixel geometry)
    │  Shoulder-width normalized measurements
    │  ├── Neck angle (ear offset from shoulder)
    │  ├── Shoulder tilt (Y difference)
    │  └── Head height (nose vs shoulder line)
    ▼
8-frame smoother (eliminates jitter)
    │
    ├── Bad for 5s → Voice alert + OS notification
    ├── Good for 5min → Voice encouragement
    └── Session logger → logs/session_*.json
```

## Tech stack

| Library | Purpose |
|---------|---------|
| MediaPipe Tasks API | Pose landmark detection |
| OpenCV | Webcam capture |
| CustomTkinter | Modern dark UI |
| pyttsx3 | AI voice alerts (local TTS) |
| win11toast | Windows notifications |
| NumPy | Angle calculations |
| Pydantic | Config validation |

## Build from source

```bash
git clone https://github.com/siyad01/postureCoach
cd postureCoach
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac/Linux

pip install -r requirements.txt

# Download the pose model
curl -L -o pose_landmarker_full.task \
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task"

python app.py
```

## Controls

| Button | Action |
|--------|--------|
| Reset | Start a new session |
| Skeleton | Toggle pose overlay |
| Minimize | Send to taskbar |

## Session data

Every session is saved to `logs/session_YYYYMMDD_HHMMSS.json`:

```json
{
  "session_id": "20260503_141055",
  "summary": {
    "duration_minutes": 45.2,
    "good_posture_percent": 78.4,
    "average_score": 83,
    "total_alerts": 3,
    "longest_good_streak": 847.0
  }
}
```

## Contributing

Issues and PRs welcome. Built in Python — if you know Python you can contribute.

```bash
git checkout -b feature/your-feature
# make changes
git push origin feature/your-feature
# open a PR
```

## License

MIT — free to use, modify, distribute.

---

<div align="center">
Built with MediaPipe · OpenCV · CustomTkinter · Runs 100% locally · No cloud · No data leaves your machine
</div>
