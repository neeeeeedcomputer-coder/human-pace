"""Sentence-end signals: is the user done typing, or just pausing?

Timing alone can never tell "he is thinking" from "he finished". Punctuation
can. These rules are deliberately blunt - they are not trying to parse
language, only to catch the few endings that reliably mean *something*:

    "你去吗？"      -> he is waiting for an answer      -> reply fast
    "好的。"        -> that thought is closed           -> reply fast
    "我今天去了…"    -> trailing off                    -> keep waiting
    "还有一点，"     -> comma means more is coming      -> keep waiting

Each signal carries an absolute cap as well as a multiplier. The multiplier
scales with the user's own typing pace; the cap prevents a slow typist's
large base window from leaking into sentences that are plainly finished.
A slow typist who types "好的。" should get a reply in seconds, not 11.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- patterns (order matters: checked top to bottom) ---

# Asking a question: trailing question mark, a question particle at the end,
# or the A-not-A pattern (来不来 / 行不行 / 有没有).
_ASK = re.compile(
    r"[?？]\s*$"
    r"|(?:吗|么)[。.!！?？~]*\s*$"
    r"|(.)(?:不|没)\1[。.!！?？~]*\s*$"
)

# Explicitly unfinished: comma / enumeration / dash / colon at the end.
_OPEN = re.compile(r"[，,、—\-：:]\s*$")

# Trailing off: ellipsis (CJK or ASCII).
_TRAIL = re.compile(r"(?:…|\.\.\.)\s*$")

# Clearly finished.
_DONE = re.compile(r"[。！!~～]\s*$")

# --- absolute caps (seconds) ---
# A question should not wait long, ever.
ASK_CAP = 2.0
# A closed statement should not wait long, ever.
DONE_CAP = 4.0
# A bare short fragment may still grow, but don't sit on it all day.
SHORT_FRAGMENT_CAP = 8.0
# "Short" measured in characters (CJK counts as 1).
SHORT_LEN = 8


@dataclass(frozen=True)
class Signal:
    """What the end of the message tells us."""

    mult: float
    """Scale applied to the pace-derived base window. <1 = reply sooner."""

    reason: str
    """Human-readable explanation, used in logs and ``Decision.explain()``."""

    cap: float | None = None
    """Hard upper bound in seconds, regardless of the base window."""

    done: bool = False
    """Whether this reads as a finished thought."""


def read_signal(text: str) -> Signal:
    """Classify the ending of ``text``.

    Returns a neutral signal (mult=1.0) when there is no text, so callers can
    pass empty strings safely.
    """
    t = (text or "").strip()
    if not t:
        return Signal(1.0, "no text")

    if _ASK.search(t):
        return Signal(0.35, "waiting for an answer", ASK_CAP, True)

    if _OPEN.search(t) or _TRAIL.search(t):
        return Signal(1.45, "sentence not finished", None, False)

    if _DONE.search(t):
        return Signal(0.60, "sentence finished", DONE_CAP, True)

    if len(t) <= SHORT_LEN:
        return Signal(1.20, "short fragment, may continue", SHORT_FRAGMENT_CAP, False)

    return Signal(0.85, "long line, no punctuation", None, True)
