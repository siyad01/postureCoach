import customtkinter as ctk
import cv2
import time
import numpy as np
from PIL import Image

from config import config, MODEL_PATH
from camera import CameraThread
from analyzer import PostureResult
from overlay import draw_skeleton, draw_no_detection
from logger import PostureLogger
from notifications import alert, encourage

# ── Theme ─────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Color tokens ──────────────────────────────────────────
COL = {
    "good"      : "#4ade80",
    "bad"       : "#f87171",
    "warn"      : "#fbbf24",
    "accent"    : "#818cf8",
    "blue"      : "#60a5fa",
    "bg0"       : "#0d0d18",
    "bg1"       : "#13131f",
    "bg2"       : "#1a1a2e",
    "bg3"       : "#16213e",
    "gray_l"    : "#94a3b8",
    "gray_d"    : "#334155",
}

FONT_MONO = "Consolas"
FONT_SANS = "Segoe UI"

class AlertManager:
    def __init__(self):
        self.bad_start   = None
        self.last_alert  = 0.0
        self.flash_until = 0.0
        self._alerted_once  = False   # has alert fired this streak?

    
    def update(self, is_good: bool) -> bool:

        now = time.time()
        if is_good:
            self.bad_start = None
            self._alerted_once  = False   # has alert fired this streak?
            return False
        if self.bad_start is None:
            self.bad_start = now

        bad_secs = now - self.bad_start
        delay_met  = bad_secs >= config.posture.alert_delay_seconds
        repeat_met = (now - self.last_alert) >= config.posture.alert_repeat_seconds

        if delay_met and repeat_met:
            self.last_alert    = now
            self.flash_until   = now + 3.0
            self._alerted_once = True
            return True
        return False
    
    def bad_secs(self) -> float:
        if self.bad_start is None:
            return 0.0
        return time.time() - self.bad_start
    
    def is_flashing(self) -> bool:  
        return time.time() < self.flash_until


class PostureCoachApp(ctk.CTk):

    WINDOW_W = 380
    WINDOW_H = 620
    VIDEO_W  = 356
    VIDEO_H  = 200

    def __init__(self):

        super().__init__()

        self.title("PostureCoach")
        self.geometry(f"{self.WINDOW_W}x{self.WINDOW_H}")
        self.minsize(340, 560)
        self.configure(bg=COL["bg0"])
        self.attributes("-topmost", True)

        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(
            f"{self.WINDOW_W}x{self.WINDOW_H}"
            f"+{sw - self.WINDOW_W - 16}"
            f"+{sh - self.WINDOW_H - 56}")

        self.camera = CameraThread()
        self.logger = PostureLogger()
        self.alerter = AlertManager()
        self._ctk_img = None

        self._was_good           = False
        self._good_streak_start  = None
        self._last_encourage_t   = 0.0
        self._ENCOURAGE_INTERVAL = 300

        self._build_ui()
        self.camera.start()
        self.after(50, self._update)  # start after UI is ready
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):

        self._build_header()
        self._build_video()
        self._build_score_row()
        self._build_metrics()
        self._build_feedback()
        self._build_session_stats()
        self._build_controls()
    
    def _build_header(self):

        hdr = ctk.CTkFrame(self, fg_color=COL["bg1"],
                           corner_radius=0, height=46)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(hdr,
            text="PostureCoach",
            font=ctk.CTkFont(FONT_SANS, 15, "bold"),
            text_color=COL["accent"]
        ).pack(side="left", padx=14)

        self.mode_lbl = ctk.CTkLabel(hdr,
            text="STARTING",
            font=ctk.CTkFont(FONT_SANS, 9, "bold"),
            text_color=COL["blue"],
            fg_color=COL["bg3"],
            corner_radius=5, width=72, height=20)
        self.mode_lbl.pack(side="left", padx=4)

        self.fps_lbl = ctk.CTkLabel(hdr,
            text="-- fps",
            font=ctk.CTkFont(FONT_MONO, 10),
            text_color=COL["gray_d"])
        self.fps_lbl.pack(side="right", padx=14)

    def _build_video(self):

        vf = ctk.CTkFrame(self, fg_color=COL["bg2"],
                          corner_radius=10)
        vf.pack(fill="x", padx=10, pady=(8, 4))

        self.vid_lbl = ctk.CTkLabel(vf, text="",
            width=self.VIDEO_W, height=self.VIDEO_H)
        self.vid_lbl.pack(padx=0, pady=0)

    def _build_score_row(self):

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=4)
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=2)
        row.columnconfigure(2, weight=1)

        sc = ctk.CTkFrame(row, fg_color=COL["bg2"], corner_radius=10)
        sc.grid(row=0, column=0, sticky="nsew", padx=(0,4))
        ctk.CTkLabel(sc, text="SCORE",
            font=ctk.CTkFont(FONT_SANS, 8, "bold"),
            text_color=COL["gray_l"]).pack(pady=(8,0))
        self.score_lbl = ctk.CTkLabel(sc, text="--",
            font=ctk.CTkFont(FONT_MONO, 30, "bold"),
            text_color=COL["gray_l"])
        self.score_lbl.pack(pady=(0,8))

        st = ctk.CTkFrame(row, fg_color=COL["bg2"], corner_radius=10)
        st.grid(row=0, column=1, sticky="nsew", padx=4)
        self.status_lbl = ctk.CTkLabel(st,
            text="Initializing...",
            font=ctk.CTkFont(FONT_SANS, 13, "bold"),
            text_color=COL["gray_l"])
        self.status_lbl.pack(expand=True, pady=(12,4))
        self.score_bar = ctk.CTkProgressBar(st,
            height=5, progress_color=COL["good"],
            fg_color=COL["bg3"])
        self.score_bar.set(0)
        self.score_bar.pack(fill="x", padx=10, pady=(0,10))

        tc = ctk.CTkFrame(row, fg_color=COL["bg2"], corner_radius=10)
        tc.grid(row=0, column=2, sticky="nsew", padx=(4,0))
        ctk.CTkLabel(tc, text="BAD FOR",
            font=ctk.CTkFont(FONT_SANS, 8, "bold"),
            text_color=COL["gray_l"]).pack(pady=(8,0))
        self.timer_lbl = ctk.CTkLabel(tc, text="--",
            font=ctk.CTkFont(FONT_MONO, 20, "bold"),
            text_color=COL["gray_l"])
        self.timer_lbl.pack(pady=(0,8))

    def _build_metrics(self):

        mf = ctk.CTkFrame(self,fg_color="transparent")
        mf.pack(fill="x", padx=10, pady=4)
        for i in range(3):
            mf.columnconfigure(i, weight=1)

        self.metric_widgets = []
        names = ["Neck", "Shoulder", "Back/Head"]
        for i, name in enumerate(names):
            card = ctk.CTkFrame(mf, fg_color=COL["bg2"],
                                corner_radius=10)
            pad = (0 if i == 0 else 4, 0)
            card.grid(row=0, column=i, sticky="nsew", padx=pad)

            ctk.CTkLabel(card, text=name,
                font=ctk.CTkFont(FONT_SANS, 8),
                text_color=COL["gray_l"]).pack(pady=(6,0))

            val = ctk.CTkLabel(card, text="--",
                font=ctk.CTkFont(FONT_MONO, 13, "bold"),
                text_color=COL["gray_l"])
            val.pack()

            bar = ctk.CTkProgressBar(card, height=4,
                progress_color=COL["good"],
                fg_color=COL["bg3"], width=72)
            bar.set(0)
            bar.pack(pady=(2,8))

            self.metric_widgets.append((val, bar))

    def _build_feedback(self):

        self.fb_frame = ctk.CTkFrame(self,
            fg_color=COL["bg2"], corner_radius=10)
        self.fb_frame.pack(fill="x", padx=10, pady=4)

        self.fb_lbl = ctk.CTkLabel(self.fb_frame,
            text="Position yourself in front of camera",
            font=ctk.CTkFont(FONT_SANS, 11),
            text_color=COL["gray_l"],
            wraplength=320, justify="center")
        self.fb_lbl.pack(pady=10, padx=12)

    def _build_session_stats(self):

        sf = ctk.CTkFrame(self, fg_color=COL["bg1"], corner_radius=10)
        sf.pack(fill="x", padx=10, pady=4)
        for i in range(4):
            sf.columnconfigure(i, weight=1)

        defs = [("Session", "time"), ("Good %", "good"),
                ("Avg Score", "avg"), ("Alerts", "alerts")]
        self.stat_lbls = {}

        for i, (title, key) in enumerate(defs):
            ctk.CTkLabel(sf, text=title,
                font=ctk.CTkFont(FONT_SANS, 8),
                text_color=COL["gray_d"]).grid(
                row=0, column=i, pady=(8,0), padx=4)
            lbl = ctk.CTkLabel(sf, text="--",
                font=ctk.CTkFont(FONT_MONO, 12, "bold"),
                text_color=COL["gray_l"])
            lbl.grid(row=1, column=i, pady=(0,10))
            self.stat_lbls[key] = lbl

    def _build_controls(self):

        cf = ctk.CTkFrame(self, fg_color="transparent")
        cf.pack(fill="x", padx=10, pady=(4,12))

        btn_cfg = dict(
            font=ctk.CTkFont(FONT_SANS, 11),
            fg_color=COL["bg2"],
            hover_color=COL["bg3"],
            border_color=COL["gray_d"],
            border_width=1,
            height=30,
        )

        ctk.CTkButton(cf, text="↺  Reset",
            **btn_cfg,
            command=self._reset
        ).pack(side="left", expand=True, fill="x", padx=(0,4))

        ctk.CTkButton(cf, text="骨  Skeleton",
            **btn_cfg,
            command=self._toggle_skeleton
        ).pack(side="left", expand=True, fill="x", padx=4)

        ctk.CTkButton(cf, text="━  Minimize",
            **btn_cfg,
            command=self.iconify
        ).pack(side="left", expand=True, fill="x", padx=(4,0))

    def _update(self):

        try:
            frame, result, landmarks = self.camera.get_frame()

            if frame is not None:
                self._update_video(frame, result, landmarks)
                self._update_panels(result)
                self._handle_alert(result)

            self.fps_lbl.configure(text=f"{self.camera.get_fps():.0f} fps")

        except Exception as e:
            print(f"[UI update error] {e}")

        self.after(33, self._update)

    def _update_video(self, frame, result, landmarks):

        display = frame.copy()

        if result and landmarks:
            draw_skeleton(display, landmarks, result)
        else:
            draw_no_detection(display)

        th = int(self.VIDEO_W * frame.shape[0] / frame.shape[1])
        display = cv2.resize(display, (self.VIDEO_W, th))

        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        img = ctk.CTkImage(pil, size=(self.VIDEO_W, th))

        self.vid_lbl.configure(image=img, width=self.VIDEO_W, height=th)
        self._ctk_img = img

    def _update_panels(self, result: PostureResult | None):

        if result is None:
            self._set_no_detection()
            return

        # Score
        sc  = result.score
        col = COL["good"] if sc >= 75 else \
              COL["warn"] if sc >= 50 else COL["bad"]
        self.score_lbl.configure(text=str(sc), text_color=col)
        self.score_bar.set(sc / 100)
        self.score_bar.configure(progress_color=col)

        if result.is_good:
            self.status_lbl.configure(
                text="✓  Good posture", text_color=COL["good"])
            self.fb_frame.configure(fg_color="#0a1f12")
            self.fb_lbl.configure(
                text="✓  Keep it up!",
                text_color=COL["good"])
        else:
            self.status_lbl.configure(
                text="⚠  Fix posture", text_color=COL["bad"])
            msgs = "\n".join(f"• {m}" for m in result.feedback)
            self.fb_lbl.configure(
                text=msgs if msgs else "Adjust your position",
                text_color=COL["warn"])
            self.fb_frame.configure(fg_color="#1f0a0a")

        # Mode badge
        self.mode_lbl.configure(
            text="DESK" if result.mode == "sitting" else "FULL BODY")
        
        bad = self.alerter.bad_secs()
        if bad > 1:
            tc = COL["bad"] if bad > 5 else COL["warn"]
            self.timer_lbl.configure(
                text=f"{bad:.0f}s", text_color=tc)
        else:
            self.timer_lbl.configure(text="--", text_color=COL["gray_l"])

        # Metrics
        vals    = [result.neck_angle, result.shoulder_tilt, result.back_angle]
        threshs = [config.posture.neck_angle_threshold,
                   config.posture.shoulder_tilt_threshold,
                   config.posture.back_angle_threshold]

        for i, (vw, bw) in enumerate(self.metric_widgets):
            v, t = vals[i], threshs[i]
            c    = COL["good"] if v <= t else COL["bad"]
            vw.configure(text=f"{v:.1f}", text_color=c)
            bw.set(min(v / (t * 2), 1.0))
            bw.configure(progress_color=c)

        if result.is_good:
            self.fb_lbl.configure(
                text="✓  Great posture! Keep it up.",
                text_color=COL["good"])
            self.fb_frame.configure(fg_color="#0a1f12")
        else:
            msgs = "  •  ".join(result.feedback)
            self.fb_lbl.configure(
                text=f"↑  {msgs}",
                text_color=COL["warn"])
            self.fb_frame.configure(fg_color="#1f0a0a")

        s = self.logger.get_live_stats()
        self.stat_lbls["time"].configure(
            text=f"{s['elapsed_minutes']:.0f}m")
        self.stat_lbls["good"].configure(
            text=f"{s['good_percent']:.0f}%",
            text_color=COL["good"] if s['good_percent'] >= 70
            else COL["warn"])
        self.stat_lbls["avg"].configure(text=str(s['avg_score']))
        self.stat_lbls["alerts"].configure(
            text=str(s['total_alerts']),
            text_color=COL["bad"] if s['total_alerts'] > 0
            else COL["gray_l"])

    def _set_no_detection(self):

        self.score_lbl.configure(text="--", text_color=COL["gray_l"])
        self.status_lbl.configure(
            text="No pose detected", text_color=COL["gray_l"])
        self.score_bar.set(0)
        self.timer_lbl.configure(text="--", text_color=COL["gray_l"])
        self.mode_lbl.configure(text="SEARCHING")
        self.fb_lbl.configure(
            text="Move back — show your shoulders",
            text_color=COL["gray_l"])
        self.fb_frame.configure(fg_color=COL["bg2"])

    def _handle_alert(self, result: PostureResult | None):
        if result is None:
            return

        now   = time.time()
        fired = self.alerter.update(result.is_good)
        self.logger.update(result.is_good, result.score)

        # Bad posture alert
        if fired:
            alert(result.score, self.alerter.bad_secs(), result.feedback)
            self.logger.record_alert(result.score)
            print(f"[ALERT] fired — bad for {self.alerter.bad_secs():.1f}s "
              f"| score {result.score} "
              f"| next alert in {config.posture.alert_repeat_seconds}s")

        # Good posture encouragement
        if result.is_good:
            if not self._was_good:
                self._good_streak_start = now
                self._was_good = True
                print(f"[GOOD] posture streak started")

            good_duration = now - (self._good_streak_start or now)
            if (good_duration >= 60 and
                    now - self._last_encourage_t >= self._ENCOURAGE_INTERVAL):
                self._last_encourage_t = now
                encourage(result.score)
                print(f"[ENCOURAGE] fired — good for {good_duration:.0f}s")
        else:
            if self._was_good:
                print(f"[BAD] posture started — "
                  f"alert in {config.posture.alert_delay_seconds}s")
            self._was_good          = False
            self._good_streak_start = None

    def _reset(self):

        self.logger = PostureLogger()
        self.alerter = AlertManager()

    def _toggle_skeleton(self):
        config.display.show_skeleton = not config.display.show_skeleton

    def _on_close(self):
        self.camera.stop()
        self.logger.save()
        self.destroy()

def main():

    if not MODEL_PATH.exists():
        print(f"ERROR: Model file not found at {MODEL_PATH}")
        return 
    app = PostureCoachApp()
    app.mainloop()

if __name__ == "__main__":
    main()

        





