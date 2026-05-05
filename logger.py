import json
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from config import LOG_DIR

# ── Data structures ──────────────────────────────────────
@dataclass
class PostureEvent:
    """A single posture state change event."""
    timestamp: str
    event_type: str     # "good", "bad", "alert", "session_start", "session_end"
    score: int
    duration: float     # seconds in this state before changing

@dataclass
class SessionSummary:
    """Summary of one working session."""
    date: str
    start_time: str
    end_time: str
    duration_minutes: float
    good_posture_percent: float
    average_score: float
    total_alerts: int
    longest_good_streak: float    # seconds
    longest_bad_streak: float     # seconds

# ── Logger ──
class PostureLogger:
    def __init__(self):
        self.session_start = time.time()
        self.session_date = datetime.now().strftime("%Y-%m-%d")
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        self.good_seconds = 0.0
        self.bad_seconds = 0.0
        self.total_alerts = 0
        self.scores =[]

        self.current_streak_start = time.time()
        self.current_is_good = None
        self.longest_good_streak = 0.0
        self.longest_bad_streak = 0.0

        self.events: list[PostureEvent] = []

        self.log_file = LOG_DIR / f"session_{self.session_id}.json"
        self.summary_file = LOG_DIR / "summary.json"

        self._log_event("session_start", 0, 0)
        print(f"[Logger] Session started → {self.log_file.name}")

    def update(self, is_good: bool, score: int):
        self.scores.append(score)
        now = time.time()

        if is_good:
            self.good_seconds += 1
        else:
            self.bad_seconds += 1

        if self.current_is_good is None:
            self.current_is_good = is_good
            self.current_streak_start = now

        elif self.current_is_good != is_good:
            streak_duration = now - self.current_streak_start
            if self.current_is_good:
                self.longest_good_streak = max(self.longest_good_streak, streak_duration)
            else:
                self.longest_bad_streak = max(self.longest_bad_streak, streak_duration)

            event_type = "good" if is_good else "bad"
            self._log_event(event_type, score, streak_duration)

            self.current_is_good = is_good
            self.current_streak_start = now

    def record_alert(self, score: int):
        self.total_alerts += 1
        self._log_event("alert", score, 0)

    def _log_event(self, event_type: str, score: int, duration: float):
        event = PostureEvent(
            timestamp=datetime.now().isoformat(),
            event_type=event_type,
            score=score,
            duration=round(duration, 1),
        )    
        self.events.append(event)

    def save(self):
        total_seconds = time.time() - self.session_start
        total_tracked = self.good_seconds + self.bad_seconds

        good_pct = (self.good_seconds / total_tracked * 100)  if total_tracked > 0 else 0.0  

        avg_score = sum(self.scores) / len(self.scores) if self.scores else 0.0

        self._log_event("session_end", int(avg_score), total_seconds)

        summary = SessionSummary(
            date=self.session_date,
            start_time=datetime.fromtimestamp(self.session_start).strftime("%H:%M:%S"),
            end_time=datetime.now().strftime("%H:%M:%S"),
            duration_minutes=round(total_seconds / 60, 1),
            good_posture_percent=round(good_pct, 1),
            average_score=round(avg_score, 1),
            total_alerts=self.total_alerts,
            longest_good_streak=round(self.longest_good_streak, 1),
            longest_bad_streak=round(self.longest_bad_streak, 1),
        )

        session_data = {
            "session_id": self.session_id,
            "summary": asdict(summary),
            "events": [asdict(e) for e in self.events],
        }

        with open(self.log_file, "w") as f:
            json.dump(session_data, f, indent=2)

        self._update_summary(summary)

        print(f"\n[Logger] Session saved → {self.log_file.name}")
        self._print_summary(summary)

    def _update_summary(self, summary: SessionSummary):
        all_sessions = []

        if self.summary_file.exists():
            with open(self.summary_file, "r") as f:
                all_sessions = json.load(f)

        all_sessions.append(asdict(summary))

        with open(self.summary_file, "w") as f:
            json.dump(all_sessions, f, indent=2)

    def _print_summary(self, summary: SessionSummary):

        print("\n" + "═" * 45)
        print("  POSTURECOACH SESSION SUMMARY")
        print("═" * 45)
        print(f"  Date          : {summary.date}")
        print(f"  Duration      : {summary.duration_minutes} minutes")
        print(f"  Good posture  : {summary.good_posture_percent}%")
        print(f"  Avg score     : {summary.average_score}/100")
        print(f"  Alerts fired  : {summary.total_alerts}")
        print(f"  Best streak   : {summary.longest_good_streak}s good posture")
        print(f"  Worst streak  : {summary.longest_bad_streak}s bad posture")
        print("═" * 45)     

    def get_live_stats(self) -> dict:
        """Returns current session stats for the UI."""
        total_tracked = self.good_seconds + self.bad_seconds
        good_pct  = (self.good_seconds / total_tracked * 100) \
                    if total_tracked > 0 else 0.0
        elapsed   = time.time() - self.session_start

        # Rolling average of last 30 scores
        recent = list(self.scores[-30:]) if self.scores else [0]
        avg    = round(sum(recent) / len(recent), 1)

        return {
            "elapsed_minutes" : round(elapsed / 60, 1),
            "good_percent"    : round(good_pct, 1),
            "avg_score"       : avg,
            "total_alerts"    : self.total_alerts,
        } 

