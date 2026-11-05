"""Compare the naive percentile formula against human-pace.

This is the script that produced the numbers in the README. It runs both
algorithms over the same real gap history, so the difference is not an
opinion.

Run:
    python examples/simulate.py
"""

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from human_pace import Pace
from human_pace.modes import percentile


def naive_window(gaps: list[float], min_samples: int = 8) -> float:
    """The common implementation this library argues against.

    base = max(median, p75) * 1.5
    cap  = min(20, max(10, p90 * 1.2))
    window = clamp(base, 2.5, cap)
    """
    if len(gaps) < min_samples:
        return 3.0
    recent = gaps[-50:]
    med = statistics.median(recent)
    p75 = percentile(recent, 75)
    p90 = percentile(recent, 90)
    base = max(med, p75) * 1.5
    cap = min(20.0, max(10.0, p90 * 1.2))
    return max(2.5, min(cap, base))


def load_gaps() -> list[float]:
    path = ROOT / "examples" / "sample_gaps.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["gaps"]


def histogram(gaps: list[float], width: float = 2.0) -> None:
    buckets: dict[int, int] = {}
    for g in gaps:
        b = int(g // width) * int(width)
        buckets[b] = buckets.get(b, 0) + 1
    print("    distribution (%.0fs bins)" % width)
    for b in sorted(buckets):
        bar = "#" * buckets[b]
        print("    %2d-%2ds | %-38s %d" % (b, b + width, bar, buckets[b]))


def main() -> None:
    gaps = load_gaps()
    print("Loaded %d real inter-message gaps" % len(gaps))
    print("  median %.2fs   p75 %.2fs   p90 %.2fs   max %.2fs"
          % (statistics.median(gaps), percentile(gaps, 75),
             percentile(gaps, 90), max(gaps)))
    print()
    histogram(gaps)
    print()

    # Walk the history forward, comparing what each algorithm would suggest.
    print("  n     last gap   naive    human-pace")
    print("  " + "-" * 45)
    naive_vals, new_vals = [], []
    for i in range(8, len(gaps) + 1, 12):
        hist = gaps[:i]
        nv = naive_window(hist)

        pace = Pace()
        t = 0.0
        pace.observe("u", ts=t)
        for g in hist:
            t += g
            pace.observe("u", ts=t)
        hv = pace.window("u")

        naive_vals.append(nv)
        new_vals.append(hv)
        print("  %-5d %-10.1f %-8.1f %-8.1f" % (i, hist[-1], nv, hv))

    def spread(vals):
        return max(vals) - min(vals), len({round(v, 1) for v in vals})

    ns, nd = spread(naive_vals)
    hs, hd = spread(new_vals)
    print()
    print("  naive      : range %.2fs, %d distinct values out of %d"
          % (ns, nd, len(naive_vals)))
    print("  human-pace : range %.2fs, %d distinct values out of %d"
          % (hs, hd, len(new_vals)))
    print()

    final = Pace()
    t = 0.0
    final.observe("u", ts=t)
    for g in gaps:
        t += g
        final.observe("u", ts=t)
    print("  Final window by sentence ending (same history):")
    for text in ["", "好的。", "你去吗？", "我今天去了…", "啊"]:
        d = final.decide("u", text=text)
        print("    %-16r -> %5.2fs   (%s)" % (text, d.wait, d.reason))


if __name__ == "__main__":
    main()
