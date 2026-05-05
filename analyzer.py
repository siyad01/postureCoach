import numpy as np
from dataclasses import dataclass
from config import config


@dataclass
class PostureResult:
    is_good:       bool
    neck_angle:    float
    shoulder_tilt: float
    back_angle:    float
    score:         int
    feedback:      list[str]
    mode:          str


@dataclass
class Point2D:
    x:          float
    y:          float
    visibility: float


class LM:
    NOSE           = 0
    LEFT_EYE       = 2
    RIGHT_EYE      = 5
    LEFT_EAR       = 7
    RIGHT_EAR      = 8
    LEFT_SHOULDER  = 11
    RIGHT_SHOULDER = 12
    LEFT_ELBOW     = 13
    RIGHT_ELBOW    = 14
    LEFT_WRIST     = 15
    RIGHT_WRIST    = 16
    LEFT_HIP       = 23
    RIGHT_HIP      = 24
    LEFT_KNEE      = 25
    RIGHT_KNEE     = 26


def _p(lm) -> Point2D:
    return Point2D(
        x=lm.x, y=lm.y,
        visibility=getattr(lm, 'visibility', 1.0))


def _vis(p: Point2D, t: float = 0.35) -> bool:
    return p.visibility >= t


def _mid(a: Point2D, b: Point2D) -> Point2D:
    return Point2D(
        (a.x + b.x) / 2,
        (a.y + b.y) / 2,
        min(a.visibility, b.visibility))


def _angle(a: Point2D, b: Point2D, c: Point2D) -> float:
    """Angle at B in 2D."""
    ba = np.array([a.x - b.x, a.y - b.y])
    bc = np.array([c.x - b.x, c.y - b.y])
    n  = np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6
    return float(np.degrees(np.arccos(np.clip(
        np.dot(ba, bc) / n, -1, 1))))


# ── Sitting mode — robust 2D analysis ────────────────────
def analyze_sitting(landmarks) -> PostureResult | None:
    """
    Shoulder-width normalized measurements.
    All ratios are relative to shoulder width so camera
    distance doesn't affect the readings.
    """
    pts = {i: _p(landmarks[i]) for i in [
        LM.NOSE,
        LM.LEFT_EYE,  LM.RIGHT_EYE,
        LM.LEFT_EAR,  LM.RIGHT_EAR,
        LM.LEFT_SHOULDER, LM.RIGHT_SHOULDER,
    ]}

    ls, rs = pts[LM.LEFT_SHOULDER], pts[LM.RIGHT_SHOULDER]
    if not (_vis(ls, 0.4) and _vis(rs, 0.4)):
        return None

    # Shoulder width in normalized image space
    # This is our ruler — everything is measured relative to it
    sw = abs(ls.x - rs.x)
    if sw < 0.05:   # shoulders too close together (bad angle)
        return None

    sh_mid = _mid(ls, rs)
    feedback = []

    # ── 1. Shoulder tilt ──────────────────────────────────
    # Y difference normalized by shoulder width
    # 0.15 = noticeable tilt (roughly 8-10 degrees)
    tilt_ratio = abs(ls.y - rs.y) / sw
    shoulder_tilt = tilt_ratio * 100

    if tilt_ratio > 0.18:
        feedback.append("Shoulders uneven — level them")

    # ── 2. Forward head — nose position relative to shoulders
    # When sitting straight: nose is ABOVE shoulder line (nose.y < sh_mid.y)
    # When leaning forward/down: nose approaches or drops below shoulders
    # Normalized by shoulder width for scale independence
    nose = pts[LM.NOSE]
    back_angle = 0.0
    if _vis(nose, 0.4):
        # How far above shoulders the nose is
        # Positive = nose above shoulders (good)
        # Zero/negative = nose at or below shoulder level (bad)
        nose_above = (sh_mid.y - nose.y) / sw

        # Good posture: nose should be 0.8-1.5x shoulder widths above
        # the shoulder midpoint (varies by person and camera height)
        # We flag if nose is less than 0.3 shoulder widths above shoulders
        if nose_above < 0.3:
            back_angle = abs(0.3 - nose_above) * 30
            if nose_above < 0.1:
                feedback.append("Head too low — look ahead")
        else:
            back_angle = 0.0

    # ── 3. Neck / ear offset ──────────────────────────────
    # When head is forward: ear moves horizontally
    # away from the shoulder in the X direction
    # Key insight: normalize by shoulder width, not raw pixels
    le, re = pts[LM.LEFT_EAR], pts[LM.RIGHT_EAR]

    neck_angle = 0.0
    if _vis(le, 0.3) or _vis(re, 0.3):
        # Use the more visible ear and its corresponding shoulder
        if le.visibility >= re.visibility:
            ear, shoulder = le, ls
        else:
            ear, shoulder = re, rs

        if _vis(ear, 0.3):
            # Horizontal offset of ear from shoulder
            # normalized by shoulder width
            # Good posture: ear is roughly above shoulder → ratio ~0
            # Forward head: ear moves forward → ratio increases
            ear_x_offset = abs(ear.x - shoulder.x) / sw
            neck_angle   = ear_x_offset * 40  # scale to readable number

            # Vertical: ear should be well above shoulder
            ear_y_above  = (shoulder.y - ear.y) / sw
            # If ear is not above shoulder (ear.y >= shoulder.y in image coords)
            # then head is very dropped down
            if ear_y_above < 0.3:
                neck_angle += 10  # penalize low ear position

            if neck_angle > config.posture.neck_angle_threshold:
                feedback.append("Head forward — push back")

    # ── 4. Eye level ──────────────────────────────────────
    le_eye, re_eye = pts[LM.LEFT_EYE], pts[LM.RIGHT_EYE]
    if _vis(le_eye, 0.3) and _vis(re_eye, 0.3):
        eye_w    = abs(le_eye.x - re_eye.x)
        eye_tilt = abs(le_eye.y - re_eye.y)
        if eye_w > 0 and (eye_tilt / eye_w) > 0.25:
            feedback.append("Head tilting — straighten up")

    # ── Score ─────────────────────────────────────────────
    penalty = (
        min(neck_angle,    40) * 1.2 +
        min(shoulder_tilt, 30) * 0.8 +
        min(back_angle,    20) * 1.0
    )
    score = int(np.clip(100 - penalty, 0, 100))

    return PostureResult(
        is_good       = len(feedback) == 0,
        neck_angle    = round(neck_angle, 1),
        shoulder_tilt = round(shoulder_tilt, 1),
        back_angle    = round(back_angle, 1),
        score         = score,
        feedback      = feedback,
        mode          = "sitting",
    )


# ── Full body mode ────────────────────────────────────────
def analyze_full(landmarks) -> PostureResult | None:
    pts = {i: _p(landmarks[i]) for i in [
        LM.LEFT_EAR,  LM.RIGHT_EAR,
        LM.LEFT_SHOULDER,  LM.RIGHT_SHOULDER,
        LM.LEFT_HIP,  LM.RIGHT_HIP,
        LM.LEFT_KNEE, LM.RIGHT_KNEE,
    ]}
    critical = [LM.LEFT_SHOULDER, LM.RIGHT_SHOULDER,
                LM.LEFT_HIP,      LM.RIGHT_HIP]
    if not all(_vis(pts[i]) for i in critical):
        return None

    ear_mid = _mid(pts[LM.LEFT_EAR],     pts[LM.RIGHT_EAR])
    sh_mid  = _mid(pts[LM.LEFT_SHOULDER], pts[LM.RIGHT_SHOULDER])
    hi_mid  = _mid(pts[LM.LEFT_HIP],      pts[LM.RIGHT_HIP])
    kn_mid  = _mid(pts[LM.LEFT_KNEE],     pts[LM.RIGHT_KNEE])

    neck_dev = abs(180 - _angle(ear_mid, sh_mid, hi_mid))
    back_dev = abs(180 - _angle(sh_mid, hi_mid, kn_mid))
    sh_tilt  = abs(pts[LM.LEFT_SHOULDER].y -
                   pts[LM.RIGHT_SHOULDER].y) * 100

    feedback = []
    if neck_dev > config.posture.neck_angle_threshold:
        feedback.append("Head forward — pull chin back")
    if sh_tilt  > config.posture.shoulder_tilt_threshold:
        feedback.append("Shoulders uneven")
    if back_dev > config.posture.back_angle_threshold:
        feedback.append("Back curved — sit up straight")

    score = int(np.clip(
        100 - neck_dev * 2 - sh_tilt - back_dev * 2, 0, 100))

    return PostureResult(
        is_good       = len(feedback) == 0,
        neck_angle    = round(neck_dev, 1),
        shoulder_tilt = round(sh_tilt,  1),
        back_angle    = round(back_dev, 1),
        score         = score,
        feedback      = feedback,
        mode          = "full",
    )


# ── Smart dispatcher ──────────────────────────────────────
def analyze_posture(landmarks) -> PostureResult | None:
    if not landmarks:
        return None
    lh = _p(landmarks[LM.LEFT_HIP])
    rh = _p(landmarks[LM.RIGHT_HIP])
    if _vis(lh) and _vis(rh):
        r = analyze_full(landmarks)
        if r:
            return r
    return analyze_sitting(landmarks)