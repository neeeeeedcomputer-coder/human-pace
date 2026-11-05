"""Generate the README charts as plain SVG (no matplotlib, no runtime deps).

Produces:
    assets/three-peaks.svg   histogram of the 200 real gaps
    assets/window.svg        naive formula vs human-pace over the same history

Run:
    python examples/make_chart.py
"""

import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from human_pace import Pace
from human_pace.modes import percentile

ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

# Palette chosen to stay legible on both GitHub light and dark backgrounds.
FG = "#57606a"
MUTED = "#8b949e"
GRID = "#d0d7de"
ACCENT = "#0969da"
WARN = "#cf222e"
FILL = "#0969da"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_open(w: int, h: int) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="-apple-system,BlinkMacSystemFont,'
        f'Segoe UI,Helvetica,Arial,sans-serif">'
    ]


def text(x, y, s, size=12, fill=FG, anchor="start", weight="400"):
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
        f'text-anchor="{anchor}" font-weight="{weight}">{esc(s)}</text>'
    )


def line(x1, y1, x2, y2, stroke=GRID, width=1, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{stroke}" stroke-width="{width}"{d}/>'
    )


def rect(x, y, w, h, fill=FILL, opacity=1.0, rx=2):
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
        f'fill="{fill}" opacity="{opacity}" rx="{rx}"/>'
    )


def polyline(points, stroke, width=2.0):
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return (
        f'<polyline points="{pts}" fill="none" stroke="{stroke}" '
        f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>'
    )


# ---------------------------------------------------------------- data

def load_gaps() -> list[float]:
    data = json.loads((ROOT / "examples" / "sample_gaps.json").read_text("utf-8"))
    return data["gaps"]


def naive_window(gaps: list[float]) -> float:
    if len(gaps) < 8:
        return 3.0
    recent = gaps[-50:]
    med = statistics.median(recent)
    p75 = percentile(recent, 75)
    p90 = percentile(recent, 90)
    base = max(med, p75) * 1.5
    cap = min(20.0, max(10.0, p90 * 1.2))
    return max(2.5, min(cap, base))


def pace_window(history: list[float]) -> float:
    p = Pace()
    t = 0.0
    p.observe("u", ts=t)
    for g in history:
        t += g
        p.observe("u", ts=t)
    return p.window("u")


# ---------------------------------------------------------------- chart 1

def chart_histogram(gaps: list[float]) -> str:
    W, H = 720, 340
    L, R, T, B = 56, 24, 52, 46
    pw, ph = W - L - R, H - T - B

    binw = 2.0
    buckets: dict[int, int] = {}
    for g in gaps:
        b = int(g // binw) * int(binw)
        buckets[b] = buckets.get(b, 0) + 1
    maxb = max(buckets.values())  # max VALUE, not max key
    maxb = maxb * 1.08            # a little headroom for the peak labels
    keys = sorted(buckets)
    n = len(keys)
    bw = pw / n

    out = svg_open(W, H)
    out.append(text(L, 26, "Inter-message gaps from 200 real messages", 15, FG, weight="600"))
    out.append(text(L, 44, "Three peaks - a single percentile describes none of them", 12, MUTED))

    # y grid
    for frac in (0.0, 0.5, 1.0):
        y = T + ph - ph * frac
        out.append(line(L, y, L + pw, y))
        out.append(text(L - 8, y + 4, str(int(maxb * frac)), 11, MUTED, "end"))
    # bars
    for i, k in enumerate(keys):
        v = buckets[k]
        h = ph * v / maxb
        x = L + i * bw
        out.append(rect(x + 2, T + ph - h, bw - 4, h, FILL, 0.72))

    # x labels every other bin
    for i, k in enumerate(keys):
        if i % 2 == 0:
            out.append(text(L + i * bw + bw / 2, T + ph + 18, f"{k}-{k+2}", 10, MUTED, "middle"))

    out.append(text(L + pw / 2, H - 8, "gap between consecutive messages (seconds)", 11, MUTED, "middle"))

    # annotate the peaks
    for lo, hi, label in ((4, 6, "fast"), (14, 16, "thinking"), (22, 24, "away")):
        idxs = [i for i, k in enumerate(keys) if lo <= k < hi]
        if not idxs:
            continue
        i = max(idxs, key=lambda j: buckets[keys[j]])
        x = L + i * bw + bw / 2
        y = T + ph - ph * buckets[keys[i]] / maxb - 8
        out.append(text(x, y, label, 10, ACCENT, "middle", "600"))

    out.append("</svg>")
    return "\n".join(out)


# ---------------------------------------------------------------- chart 2

def chart_window(gaps: list[float]) -> str:
    W, H = 720, 340
    L, R, T, B = 56, 104, 52, 46
    pw, ph = W - L - R, H - T - B

    xs, naive, ours = [], [], []
    for i in range(8, len(gaps) + 1, 4):
        hist = gaps[:i]
        xs.append(i)
        naive.append(naive_window(hist))
        ours.append(pace_window(hist))

    ymax = 21.0
    n = len(xs)

    def px(i):
        return L + pw * i / (n - 1)

    def py(v):
        return T + ph - ph * min(v, ymax) / ymax

    out = svg_open(W, H)
    out.append(text(L, 26, "Suggested wait, same history, two algorithms", 15, FG, "start", "600"))
    out.append(text(L, 44, "The percentile formula sits pinned at its 20s ceiling", 12, MUTED))

    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        y = T + ph - ph * frac
        out.append(line(L, y, L + pw, y))
        out.append(text(L - 8, y + 4, f"{ymax*frac:.0f}s", 11, MUTED, "end"))

    out.append(polyline([(px(i), py(v)) for i, v in enumerate(naive)], WARN, 2.0))
    out.append(polyline([(px(i), py(v)) for i, v in enumerate(ours)], ACCENT, 2.0))

    # legend
    lx = L + pw + 12
    out.append(line(lx, 70, lx + 18, 70, WARN, 2.0))
    out.append(text(lx + 22, 74, "percentile", 11, FG))
    out.append(line(lx, 90, lx + 18, 90, ACCENT, 2.0))
    out.append(text(lx + 22, 94, "human-pace", 11, FG))

    out.append(text(L + pw / 2, H - 8, "messages seen so far", 11, MUTED, "middle"))
    out.append("</svg>")
    return "\n".join(out)


def main() -> None:
    gaps = load_gaps()

    p1 = ASSETS / "three-peaks.svg"
    p1.write_text(chart_histogram(gaps), encoding="utf-8")
    print("wrote", p1, p1.stat().st_size, "bytes")

    p2 = ASSETS / "window.svg"
    p2.write_text(chart_window(gaps), encoding="utf-8")
    print("wrote", p2, p2.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
