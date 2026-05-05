import platform
import threading
import subprocess
import queue
import os
import time

SYSTEM = platform.system()


# ══════════════════════════════════════════════════════════
# TTS ENGINE — persistent dedicated thread
# ══════════════════════════════════════════════════════════
# pyttsx3 MUST be initialized and used on the SAME thread.
# We run one permanent worker thread that owns the engine.
# Other threads just put messages into _tts_queue.

_tts_queue   : queue.Queue = queue.Queue()
_tts_ready   : threading.Event = threading.Event()
_tts_thread  = None


def _tts_worker():
    """
    Permanent background thread that owns the TTS engine.
    Waits for messages, speaks them immediately.
    Re-initializes engine on failure for robustness.
    """
    import pyttsx3

    def _make_engine():
        try:
            eng = pyttsx3.init()
            eng.setProperty('rate',   150)
            eng.setProperty('volume', 1.0)
            # Pick best voice — prefer Zira (female) on Windows
            voices = eng.getProperty('voices')
            chosen = None
            for v in voices:
                n = v.name.lower()
                if 'zira' in n:
                    chosen = v; break
            if not chosen:
                for v in voices:
                    n = v.name.lower()
                    if 'david' in n or 'english' in n:
                        chosen = v; break
            if chosen:
                eng.setProperty('voice', chosen.id)
            return eng
        except Exception as e:
            print(f"[TTS init error] {e}")
            return None

    engine = _make_engine()
    _tts_ready.set()            # signal that engine is ready

    while True:
        try:
            msg = _tts_queue.get(timeout=1.0)

            if msg is None:     # shutdown signal
                break

            if engine is None:
                engine = _make_engine()
                if engine is None:
                    print(f"[TTS] Engine unavailable, skipping: {msg}")
                    continue

            try:
                engine.say(msg)
                engine.runAndWait()
            except Exception as e:
                print(f"[TTS speak error] {e} — reinitializing engine")
                try:
                    engine.stop()
                except Exception:
                    pass
                engine = _make_engine()  # recover from bad state

        except queue.Empty:
            continue
        except Exception as e:
            print(f"[TTS worker error] {e}")


def _ensure_tts_started():
    """Start TTS worker thread if not already running."""
    global _tts_thread
    if _tts_thread is None or not _tts_thread.is_alive():
        _tts_thread = threading.Thread(
            target=_tts_worker, daemon=True, name="TTS-Worker")
        _tts_thread.start()
        _tts_ready.wait(timeout=3.0)   # wait for engine ready


def speak(text: str):
    """
    Queue a message for TTS — returns INSTANTLY.
    The dedicated worker thread speaks it with zero delay.
    Drops message if queue already has one waiting
    (don't pile up stale alerts).
    """
    _ensure_tts_started()
    # Clear stale messages — only speak the latest
    while not _tts_queue.empty():
        try:
            _tts_queue.get_nowait()
        except queue.Empty:
            break
    _tts_queue.put(text)


# ══════════════════════════════════════════════════════════
# SOUND — simple, instant, no external lib
# ══════════════════════════════════════════════════════════
def _chime_good():
    """Pleasant ascending chime — good posture reward."""
    def _go():
        try:
            if SYSTEM == "Windows":
                import winsound
                for freq, dur in [(523,100),(659,100),(784,180)]:
                    winsound.Beep(freq, dur)
                    time.sleep(0.01)
            elif SYSTEM == "Darwin":
                os.system("afplay /System/Library/Sounds/Glass.aiff &")
        except Exception:
            pass
    threading.Thread(target=_go, daemon=True).start()


# ══════════════════════════════════════════════════════════
# NOTIFICATIONS — native OS toasts
# ══════════════════════════════════════════════════════════
def _toast_windows(title: str, body: str):
    def _go():
        try:
            from win11toast import toast
            toast(title, body,
                  audio={'silent': 'true'},
                  duration='long')
        except Exception:
            # PowerShell fallback
            try:
                ps = f'''
Add-Type -AssemblyName System.Windows.Forms
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Warning
$n.Visible = $true
$n.ShowBalloonTip(6000, "{title}", "{body}",
    [System.Windows.Forms.ToolTipIcon]::Warning)
Start-Sleep 7
$n.Dispose()
'''
                subprocess.Popen(
                    ["powershell", "-WindowStyle", "Hidden",
                     "-Command", ps],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"[Toast fallback error] {e}")
    threading.Thread(target=_go, daemon=True).start()


def _toast_mac(title: str, body: str):
    def _go():
        b = body.replace('"', "'")
        t = title.replace('"', "'")
        os.system(
            f'osascript -e \'display notification "{b}" '
            f'with title "{t}"\'')
    threading.Thread(target=_go, daemon=True).start()


def _toast_linux(title: str, body: str):
    def _go():
        subprocess.Popen(
            ["notify-send", "-u", "critical",
             "-t", "6000", title, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
    threading.Thread(target=_go, daemon=True).start()


def send_notification(title: str, body: str):
    if SYSTEM == "Windows":
        _toast_windows(title, body)
    elif SYSTEM == "Darwin":
        _toast_mac(title, body)
    else:
        _toast_linux(title, body)


# ══════════════════════════════════════════════════════════
# VOICE MESSAGES
# ══════════════════════════════════════════════════════════
_BAD_MSGS = [
    "Posture alert. Please sit up straight.",
    "Heads up. Your posture needs attention.",
    "Posture reminder. Pull your shoulders back.",
    "Please correct your posture now.",
    "Your back will thank you. Sit up straight.",
    "Posture check. Align your spine.",
]

_GOOD_MSGS = [
    "Great posture. Keep it up.",
    "Excellent. Your spine is well aligned.",
    "Perfect posture. Well done.",
    "Fantastic. Keep sitting tall.",
    "Great work. Your posture looks healthy.",
]

_bad_idx  = 0
_good_idx = 0


# ══════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════
def alert(score: int, bad_secs: float, feedback: list[str]):
    """
    Bad posture alert:
      1. OS notification (instant)
      2. Voice message (instant queue, plays in ~100ms)
    No beep — voice IS the alert.
    """
    global _bad_idx

    # Pick context-aware message
    msg = _BAD_MSGS[_bad_idx % len(_BAD_MSGS)]
    _bad_idx += 1

    if feedback:
        issue = feedback[0].lower()
        if "forward" in issue or "head" in issue:
            msg = ("Posture alert. "
                   "Your head is too far forward. "
                   "Please push it back.")
        elif "shoulder" in issue:
            msg = ("Posture alert. "
                   "Your shoulders are uneven. "
                   "Please level them.")
        elif "low" in issue or "look" in issue:
            msg = ("Posture alert. "
                   "Your head is too low. "
                   "Look straight ahead.")
        elif "tilt" in issue:
            msg = ("Posture alert. "
                   "Your head is tilting. "
                   "Please straighten up.")

    # 1. Notification first — instant
    notif = (
        f"Bad posture for {bad_secs:.0f}s  •  "
        f"Score: {score}/100\n"
        f"{feedback[0] if feedback else 'Fix your posture'}"
    )
    send_notification("⚠ PostureCoach Alert", notif)

    # 2. Voice — queued, plays in ~100ms
    speak(msg)


def encourage(score: int):
    """
    Good posture milestone:
      1. Chime sound
      2. Voice praise
    No notification — stay in flow.
    """
    global _good_idx
    msg = _GOOD_MSGS[_good_idx % len(_GOOD_MSGS)]
    _good_idx += 1

    _chime_good()
    time.sleep(0.25)
    speak(msg)


# Pre-warm the TTS engine at import time so first alert is instant
_ensure_tts_started()