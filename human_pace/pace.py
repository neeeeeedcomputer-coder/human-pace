"""Pace: decide how long to wait before replying to a chat message.

The problem
-----------
Every chat bot needs to answer "should I reply now, or is the user still
typing?". The common solutions are a fixed delay, or "wait until the user
stops for N seconds". Both fail on the same case: a person who thinks in
bursts sends "我今天下午去了一趟那个..." then pauses, and a fixed 3s delay cuts them off
mid-thought.

The obvious upgrade - measure the user's typical inter-message gap - has a
trap. If you take a percentile of the whole history and scale it, the result
can exceed your hard ceiling, and then it becomes a *constant*: adaptive in
code, fixed in practice. That is easy to ship and hard to notice.

This module avoids it by asking a different question. Not "how long should I
wait", but "is this thought finished". Two signals answer it:

1. **Which mode is he in** - cluster recent gaps into fast/mid/slow and look
   at where the latest gap landed. An active burst implies more coming.
2. **How does the sentence end** - "?" wants an answer now, "..." does not.

Timing supplies a base; the sentence ending decides how to scale it, with
absolute caps so that plainly-finished sentences never inherit a slow typist's
long window.

Usage
-----
    from human_pace import Pace

    pace = Pace()
    pace.observe("user_1", text="我今天下午去了一趟那个...")   # on every incoming message
    r = pace.decide("user_1", text="我今天下午去了一趟那个...")
    if r.done:
        reply()
    else:
        await asyncio.sleep(r.wait)
        reply()
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field, asdict

from .modes import kmeans1d, nearest, percentile
from .signals import read_signal
from .store import MemoryStore, SqliteStore, Store


@dataclass
class PaceConfig:
    """Tunables. The defaults come from 200 real messages; adjust per user."""

    default_window: float = 3.0
    """Used until enough samples have been collected."""

    min_window: float = 2.5
    """Never suggest replying sooner than this - it reads as interrupting."""

    max_window: float = 20.0
    """Hard ceiling. Beyond this, waiting is worse than guessing."""

    soft_max: float = 10.0
    """Ceiling used when the data does not clearly justify waiting longer."""

    factor: float = 1.5
    """Base multiplier applied to the mode median before signal scaling."""

    min_samples: int = 8
    """Below this the history is too thin to cluster; fall back to default."""

    min_gap: float = 0.3
    """Gaps shorter than this are probably one message split by the client."""

    max_gap: float = 25.0
    """Gaps longer than this are a new conversation, not a pause."""

    mode_samples: int = 20
    """How many recent gaps feed the clustering window."""

    mode_k: int = 3
    """fast / mid / slow."""

    keep_samples: int = 200
    """History length per user."""


@dataclass
class Decision:
    """The answer to "reply now, or wait?"."""

    done: bool
    """Whether the user's message reads as a complete thought."""

    wait: float
    """Suggested delay in seconds before replying."""

    reason: str
    """Why - the sentence-end signal that fired."""

    mode: str
    """Detected rhythm: ``fast`` / ``mid`` / ``slow`` / ``cold``."""

    confidence: float
    """0..1, scaled by how many samples back the decision."""

    detail: dict = field(default_factory=dict)
    """Raw numbers, for logging and tests."""

    def explain(self) -> str:
        """One-line human-readable justification."""
        d = self.detail
        n = d.get("n", 0)
        if self.mode == "cold":
            return "cold start (n=%d) | %s x%.2f -> wait %.2fs" % (
                n,
                self.reason,
                d.get("mult", 1.0),
                self.wait,
            )
        return (
            "mode=%s(%.2fs) | last gap %.2fs | %s x%.2f "
            "| base %.2fs -> wait %.2fs | done=%s | n=%d"
            % (
                self.mode,
                d.get("mode_median", 0.0),
                d.get("last_gap", 0.0),
                self.reason,
                d.get("mult", 1.0),
                d.get("base_window", 0.0),
                self.wait,
                self.done,
                n,
            )
        )

    def as_dict(self) -> dict:
        out = asdict(self)
        return out


class Pace:
    """Tracks one or more users' typing rhythm and advises on reply timing."""

    def __init__(
        self,
        config: PaceConfig | None = None,
        store: Store | None = None,
        *,
        sqlite_path: str | None = None,
    ) -> None:
        self.config = config or PaceConfig()
        if store is not None:
            self.store: Store = store
        elif sqlite_path:
            self.store = SqliteStore(sqlite_path, keep=self.config.keep_samples)
        else:
            self.store = MemoryStore(keep=self.config.keep_samples)
        self._last_ts: dict[str, float] = {}

    # ------------------------------------------------------------------ input

    def observe(
        self, key: str, text: str = "", ts: float | None = None
    ) -> float | None:
        """Register that ``key`` sent a message. Returns the gap, or None.

        Call this on every incoming message, before deciding anything. The
        first call for a key returns ``None`` because there is no previous
        message to measure against.

        ``text`` is accepted for symmetry with :meth:`decide` and is not used
        for timing; the gap is measured wall-clock.
        """
        now = ts if ts is not None else time.time()
        last = self._last_ts.get(key)
        self._last_ts[key] = now
        if last is None:
            return None

        gap = now - last
        # Too short: the client split one message into several parts.
        # Too long: he walked away; this is a new conversation, not a pause.
        if gap < self.config.min_gap or gap > self.config.max_gap:
            return None

        self.store.add(key, gap, now)
        return gap

    # ----------------------------------------------------------------- output

    def window(self, key: str, text: str = "") -> float:
        """Seconds to wait. Convenience wrapper around :meth:`decide`."""
        return self.decide(key, text).wait

    def decide(self, key: str, text: str = "") -> Decision:
        """Combine rhythm and sentence ending into a decision."""
        cfg = self.config
        gaps = self.store.recent(key, max(cfg.mode_samples, 50))

        if len(gaps) < cfg.min_samples:
            base_window = cfg.default_window
            mode = "cold"
            detail: dict = {"n": len(gaps)}
            mode_median = cfg.default_window
            confidence = 0.0
        else:
            base_window, mode, mode_median, detail = self._mode_window(gaps)
            confidence = min(1.0, len(gaps) / float(cfg.mode_samples))

        sig = read_signal(text)
        wait = base_window * sig.mult
        if sig.cap is not None:
            wait = min(wait, sig.cap)
        # A signal-specific cap may legitimately sit below min_window: nobody
        # feels interrupted by an answer to a direct question. So lower the
        # floor as well, instead of letting the floor silently undo the cap.
        floor = cfg.min_window
        if sig.cap is not None:
            floor = min(floor, sig.cap)
        wait = max(floor, min(cfg.max_window, wait))

        detail.update(
            {
                "base_window": round(base_window, 3),
                "signal": sig.reason,
                "mult": sig.mult,
                "cap": sig.cap,
                "wait": round(wait, 3),
            }
        )

        return Decision(
            done=sig.done,
            wait=wait,
            reason=sig.reason,
            mode=mode,
            confidence=round(confidence, 2),
            detail=detail,
        )

    def _mode_window(self, gaps: list[float]):
        """Base window from the cluster the latest gap belongs to."""
        cfg = self.config
        recent = gaps[: cfg.mode_samples]
        centers, groups = kmeans1d(recent, cfg.mode_k)

        if not centers:
            return cfg.default_window, "cold", cfg.default_window, {"n": len(recent)}

        last = recent[0]
        j = nearest(centers, last)
        group = groups[j] or [last]
        mode_median = statistics.median(group)

        # The ceiling follows the overall P90 so that a genuinely slow typist
        # is allowed a longer wait, but never past max_window.
        p90 = percentile(gaps, 90)
        cap = min(cfg.max_window, max(cfg.soft_max, p90 * 1.2))

        base = mode_median * cfg.factor
        base = max(cfg.min_window, min(cap, base))

        # Label by absolute position, not cluster index: if every gap is slow,
        # all three centers are slow and index 0 would be mislabelled "fast".
        overall = statistics.median(gaps)
        if overall > 0 and mode_median < overall * 0.8:
            mode = "fast"
        elif overall > 0 and mode_median > overall * 1.2:
            mode = "slow"
        else:
            mode = "mid"

        detail = {
            "n": len(recent),
            "centers": [round(c, 2) for c in centers],
            "last_gap": round(last, 2),
            "mode_median": round(mode_median, 2),
            "overall_median": round(overall, 2),
            "p90": round(p90, 2),
            "cap": round(cap, 2),
        }
        return base, mode, mode_median, detail

    def summary(self, key: str) -> dict:
        """Everything known about one user, for dashboards and debugging."""
        gaps = self.store.recent(key, 100)
        if not gaps:
            return {"n": 0, "window": self.config.default_window}
        d = self.decide(key, "")
        return {
            "n": len(gaps),
            "median": round(statistics.median(gaps), 2),
            "p75": round(percentile(gaps, 75), 2),
            "p90": round(percentile(gaps, 90), 2),
            "min": round(min(gaps), 2),
            "max": round(max(gaps), 2),
            "mode": d.mode,
            "window": round(d.wait, 2),
        }

    def reset(self, key: str | None = None) -> None:
        """Forget history for one user, or everyone."""
        self.store.clear(key)
        if key is None:
            self._last_ts.clear()
        else:
            self._last_ts.pop(key, None)
