"""
PostureCoach CLI fallback.
Runs in an OpenCV window — no CustomTkinter required.
Use this on low-end machines or for debugging.
Run: python posturecoach.py
"""

import cv2
import time
import mediapipe as mp
import os
import logging
import ctypes

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['GLOG_minloglevel']     = '3'
os.environ['GRPC_VERBOSITY']       = 'ERROR'
logging.getLogger('mediapipe').setLevel(logging.ERROR)

from rich.console import Console
from rich.panel   import Panel
from rich.text    import Text

from config        import config, MODEL_PATH
from analyzer      import analyze_posture
from overlay       import draw_frame
from logger        import PostureLogger
from notifications import alert, encourage

console = Console()

BaseOptions           = mp.tasks.BaseOptions
PoseLandmarker        = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
VisionRunningMode     = mp.tasks.vision.RunningMode


class AlertManager:
    def __init__(self):
        self.bad_start   = None
        self.last_alert  = 0.0
        self.flash_until = 0.0

    def update(self, is_good: bool) -> bool:
        now = time.time()
        if is_good:
            self.bad_start = None
            return False
        if self.bad_start is None:
            self.bad_start = now
        bad = now - self.bad_start
        if (bad >= config.posture.alert_delay_seconds and
                now - self.last_alert >= config.posture.alert_repeat_seconds):
            self.last_alert  = now
            self.flash_until = now + 3.0
            return True
        return False

    def bad_secs(self) -> float:
        return 0.0 if not self.bad_start \
               else time.time() - self.bad_start

    def is_flashing(self) -> bool:
        return time.time() < self.flash_until


def _banner():
    t = Text()
    t.append("PostureCoach CLI  ", style="bold cyan")
    t.append("v0.2.0\n", style="bold white")
    t.append("OpenCV window mode\n\n", style="dim")
    t.append("Q", style="bold green"); t.append(" quit  ")
    t.append("S", style="bold green"); t.append(" skeleton  ")
    t.append("A", style="bold green"); t.append(" angles  ")
    t.append("R", style="bold green"); t.append(" reset\n")
    console.print(Panel(t, title="[cyan]Starting[/cyan]",
                        border_style="cyan", padding=(1, 2)))

was_good           = False
good_streak_start  = None
last_encourage_t   = 0.0
ENCOURAGE_INTERVAL = 300

def run():
    _banner()

    if not MODEL_PATH.exists():
        console.print(f"[red]Model not found: {MODEL_PATH}[/red]")
        return

    cap = cv2.VideoCapture(config.camera.camera_index)
    if not cap.isOpened():
        console.print("[red]Cannot open camera[/red]")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS,          30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)

    # Small floating window
    WIN_W, WIN_H = 360, 280
    cv2.namedWindow(config.display.window_title,
                    cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow(config.display.window_title, WIN_W, WIN_H)

    # Position bottom-right
    try:
        user32 = ctypes.windll.user32
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        cv2.moveWindow(config.display.window_title,
                       sw - WIN_W - 16, sh - WIN_H - 56)
    except Exception:
        pass  # non-Windows — skip positioning

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(
            model_asset_path=str(MODEL_PATH)),
        running_mode=VisionRunningMode.IMAGE,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        num_poses=1,
    )

    logger  = PostureLogger()
    alerter = AlertManager()

    last_log_t   = time.time()
    last_stats_t = time.time()
    last_result  = None
    last_lms     = None
    frame_count  = 0
    no_det_count = 0

    console.print("[green]✓[/green] Running!\n")

    with PoseLandmarker.create_from_options(options) as lmk:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1
            frame = cv2.flip(frame, 1)

            # Run MediaPipe
            rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=rgb)
            det = lmk.detect(mp_img)

            if det.pose_landmarks:
                last_lms    = det.pose_landmarks[0]
                last_result = analyze_posture(last_lms)
                no_det_count = 0
            else:
                no_det_count += 1
                if no_det_count > 10:
                    last_lms    = None
                    last_result = None

            # Per-second logic
            now = time.time()
            if now - last_log_t >= 1.0:
                last_log_t = now
                if last_result:
                    fired = alerter.update(last_result.is_good)
                    logger.update(last_result.is_good,
                                  last_result.score)
                    if fired:
                        alert(last_result.score,
                              alerter.bad_secs(),
                              last_result.feedback)
                        logger.record_alert(last_result.score)
                        console.print(
                            f"[bold red]⚠ ALERT[/bold red] — "
                            f"{alerter.bad_secs():.0f}s bad | "
                            f"score {last_result.score}")
                    
                    # Good posture encouragement
                    if last_result.is_good:
                        if not was_good:
                            good_streak_start = now
                            was_good = True
                        if (good_streak_start and
                                now - good_streak_start >= 60 and
                                now - last_encourage_t  >= ENCOURAGE_INTERVAL):
                            last_encourage_t = now
                            encourage(last_result.score)
                            console.print(
                                f"[green]✓ Encouragement sent — "
                                f"{last_result.score}/100[/green]")
                    else:
                        was_good          = False
                        good_streak_start = None

            # Stats every 15s
            if now - last_stats_t >= 15.0:
                last_stats_t = now
                s = logger.get_live_stats()
                console.print(
                    f"[dim]{s['elapsed_minutes']}min | "
                    f"good [green]{s['good_percent']}%[/green] | "
                    f"avg [yellow]{s['avg_score']}[/yellow] | "
                    f"alerts [red]{s['total_alerts']}[/red][/dim]")

            # Draw
            s = logger.get_live_stats()
            draw_frame(
                frame            = frame,
                landmarks        = last_lms,
                result           = last_result,
                bad_duration     = alerter.bad_secs(),
                show_alert       = alerter.is_flashing(),
                session_good_pct = s['good_percent'],
            )

            cv2.imshow(config.display.window_title, frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                config.display.show_skeleton = \
                    not config.display.show_skeleton
            elif key == ord('a'):
                config.display.show_angles = \
                    not config.display.show_angles
            elif key == ord('r'):
                logger  = PostureLogger()
                alerter = AlertManager()
                console.print("[cyan]Session reset[/cyan]")

    cap.release()
    cv2.destroyAllWindows()
    logger.save()
    console.print("[green]✓ Goodbye![/green]")


if __name__ == "__main__":
    run()