import os
os.environ['TF_CPP_MIN_LOG_LEVEL']       = '3'
os.environ['GLOG_minloglevel']            = '3'
os.environ['GRPC_VERBOSITY']              = 'ERROR'
os.environ['GLOG_logtostderr']            = '0'
os.environ['MEDIAPIPE_DISABLE_GPU']       = '1'

import cv2
import time
import threading
import mediapipe as mp
import logging
import collections
import numpy as np

logging.getLogger('mediapipe').setLevel(logging.ERROR)

from config import config, MODEL_PATH
from analyzer import analyze_posture, PostureResult

BaseOptions           = mp.tasks.BaseOptions
PoseLandmarker        = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
VisionRunningMode     = mp.tasks.vision.RunningMode


class SmoothedResult:
    """
    Smooths posture results over N frames to eliminate jitter.
    Uses a sliding window average on numeric values.
    """
    def __init__(self, window=8):
        self.window       = window
        self.neck_hist    = collections.deque(maxlen=window)
        self.shoulder_hist= collections.deque(maxlen=window)
        self.back_hist    = collections.deque(maxlen=window)
        self.score_hist   = collections.deque(maxlen=window)
        self.good_hist    = collections.deque(maxlen=window)
        self.last_result  = None

    def update(self, result: PostureResult | None) -> PostureResult | None:
        if result is None:
            self.neck_hist.clear()
            self.shoulder_hist.clear()
            self.back_hist.clear()
            self.score_hist.clear()
            self.good_hist.clear()
            self.last_result = None
            return None  # hold last known result briefly

        self.neck_hist.append(result.neck_angle)
        self.shoulder_hist.append(result.shoulder_tilt)
        self.back_hist.append(result.back_angle)
        self.score_hist.append(result.score)
        self.good_hist.append(1 if result.is_good else 0)

        # Smooth numeric values
        smoothed_neck     = float(np.mean(self.neck_hist))
        smoothed_shoulder = float(np.mean(self.shoulder_hist))
        smoothed_back     = float(np.mean(self.back_hist))
        smoothed_score    = int(np.mean(self.score_hist))

        # Only flip good/bad if majority of recent frames agree
        # This prevents flickering between states
        good_ratio = sum(self.good_hist) / len(self.good_hist)
        smoothed_good = good_ratio >= 0.6  # 60% of frames must agree

        # Rebuild feedback from smoothed values
        feedback = []
        from config import config as cfg
        if smoothed_neck     > cfg.posture.neck_angle_threshold:
            feedback.append("Head tilted — chin level")
        if smoothed_shoulder > cfg.posture.shoulder_tilt_threshold:
            feedback.append("Shoulders uneven — level them")
        if smoothed_back     > cfg.posture.back_angle_threshold:
            feedback.append("Head forward — push back")

        from analyzer import PostureResult
        smoothed = PostureResult(
            is_good       = smoothed_good,
            neck_angle    = round(smoothed_neck, 1),
            shoulder_tilt = round(smoothed_shoulder, 1),
            back_angle    = round(smoothed_back, 1),
            score         = smoothed_score,
            feedback      = feedback,
            mode          = result.mode,
        )
        self.last_result = smoothed
        return smoothed


class CameraThread:
    """
    Runs webcam + MediaPipe in a background thread.
    GUI thread reads results non-blocking via get_frame().
    """

    def __init__(self):
        self.running       = False
        self.thread        = None
        self._lock         = threading.Lock()
        self._frame        = None
        self._result       = None
        self._landmarks    = None
        self._fps          = 0.0
        self._smoother     = SmoothedResult(window=8)
        self._no_detect_frames = 0   # consecutive frames with no detection

    def start(self):
        self.running = True
        self.thread  = threading.Thread(
            target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=3.0)

    def get_frame(self):
        """Returns (frame_copy, result, landmarks) — thread-safe."""
        with self._lock:
            return (
                self._frame.copy() if self._frame is not None else None,
                self._result,
                self._landmarks,
            )

    def get_fps(self) -> float:
        with self._lock:
            return self._fps

    def _loop(self):
        cap = cv2.VideoCapture(config.camera.camera_index)
        if not cap.isOpened():
            print("ERROR: Cannot open webcam")
            return

        # Use lower resolution for better performance
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS,          30)

        # Reduce internal buffer — we want latest frame not buffered ones
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        options = PoseLandmarkerOptions(
            base_options=BaseOptions(
                model_asset_path=str(MODEL_PATH)),
            running_mode=VisionRunningMode.IMAGE,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            num_poses=1,
        )

        fps_t     = time.time()
        fps_count = 0
        # Only run MediaPipe every N frames for performance
        # Process every frame on fast machines, every 2nd on slow
        process_every = 1

        with PoseLandmarker.create_from_options(options) as lmk:
            while self.running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.033)
                    continue

                frame = cv2.flip(frame, 1)
                fps_count += 1

                # ── Run MediaPipe ─────────────────────────
                landmarks = None
                result    = None

                if fps_count % process_every == 0:
                    rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    mp_img = mp.Image(
                        image_format=mp.ImageFormat.SRGB,
                        data=rgb)
                    det = lmk.detect(mp_img)

                    if det.pose_landmarks:
                        last_landmarks = det.pose_landmarks[0]
                        result    = analyze_posture(last_landmarks)
                        self._no_detect_frames = 0
                    else:
                        # Clear immediately — don't hold stale data
                        last_landmarks = None
                        result         = None
                        self._no_detect_frames = 0

                # ── Smooth the result ─────────────────────
                smoothed = self._smoother.update(result)

                # ── Write to shared state ─────────────────
                with self._lock:
                    self._frame     = frame
                    self._result    = smoothed
                    self._landmarks = last_landmarks

                # ── FPS tracking ──────────────────────────
                now = time.time()
                if now - fps_t >= 1.0:
                    with self._lock:
                        self._fps = fps_count
                    fps_count = 0
                    fps_t     = now

        cap.release()