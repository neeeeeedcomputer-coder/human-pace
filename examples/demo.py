"""Minimal example: adapt reply timing to how someone actually types.

Run:
    python examples/demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from human_pace import Pace

pace = Pace()

# Six messages arriving over ~20 seconds. The clock is faked so the example
# is reproducible; in a real bot just call observe() without a timestamp.
messages = [
    (0.0, "在吗？"),
    (2.1, "我今天去了趟"),
    (3.4, "那个新开的店"),
    (9.0, "人特别多"),
    (11.2, "排了半小时"),
    (26.0, "算了不说这个了。"),
]

for ts, text in messages:
    gap = pace.observe("user_1", text=text, ts=ts)
    decision = pace.decide("user_1", text=text)
    marker = "   " if gap is None else "%4.1fs" % gap
    print(f"{marker}  {text:<14}  wait={decision.wait:5.2f}s   {decision.explain()}")

print()
print("Summary:", pace.summary("user_1"))
