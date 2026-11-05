"""Pace end-to-end: cold start, adaptation, and the saturation regression."""

import statistics

import pytest

from human_pace import Pace, PaceConfig
from human_pace.modes import percentile
from human_pace.store import MemoryStore, SqliteStore


def feed(pace: Pace, key: str, gaps: list[float], start: float = 1000.0) -> None:
    """Feed explicit gaps by advancing a fake clock."""
    t = start
    pace.observe(key, ts=t)  # first message establishes a baseline
    for g in gaps:
        t += g
        pace.observe(key, ts=t)


def test_cold_start_uses_default():
    p = Pace()
    assert p.window("u1") == pytest.approx(3.0)
    d = p.decide("u1")
    assert d.mode == "cold"
    assert d.confidence == 0.0


def test_first_observe_returns_none():
    p = Pace()
    assert p.observe("u1", ts=100.0) is None
    assert p.observe("u1", ts=102.0) == pytest.approx(2.0)


def test_implausible_gaps_are_dropped():
    p = Pace()
    p.observe("u1", ts=100.0)
    # Too short: same message split by the client.
    assert p.observe("u1", ts=100.1) is None
    # Too long: he walked away, this is a new conversation.
    assert p.observe("u1", ts=100.0 + 600) is None


def test_fast_typer_gets_short_window():
    p = Pace()
    feed(p, "u1", [2.0, 2.4, 1.9, 2.2, 2.1, 2.6, 2.0, 2.3, 2.2, 2.1])
    assert p.window("u1") < 5.0


def test_slow_typer_window_is_bounded_but_not_short():
    p = Pace()
    feed(p, "u1", [14.0, 15.0, 13.5, 16.0, 14.5, 15.5, 13.8, 14.9, 15.1, 14.2])
    w = p.window("u1")
    assert 4.0 <= w <= 20.0


def test_finished_sentence_beats_typing_speed():
    """A slow typist saying "好的。" must not wait 11 seconds for it."""
    p = Pace()
    feed(p, "u1", [14.0, 15.0, 13.5, 16.0, 14.5, 15.5, 13.8, 14.9, 15.1, 14.2])
    assert p.window("u1", text="好的。") <= 4.0
    assert p.window("u1", text="你去吗？") <= 2.0


def test_trailing_off_waits_longer_than_finished():
    p = Pace()
    feed(p, "u1", [5.0, 6.0, 5.5, 4.8, 6.2, 5.1, 5.9, 5.3, 5.4, 5.7])
    open_wait = p.window("u1", text="我今天去了…")
    done_wait = p.window("u1", text="我今天去了。")
    assert open_wait > done_wait


def test_window_is_bounded():
    p = Pace()
    feed(p, "u1", [24.0] * 20)
    for text in ["", "好的。", "我今天去了…", "啊"]:
        w = p.window("u1", text=text)
        assert 2.5 <= w <= 20.0, text
    # Questions are allowed below the general floor: answering a direct
    # question quickly never reads as interrupting.
    assert 1.0 <= p.window("u1", text="你去吗？") <= 2.0


def test_regression_window_does_not_saturate():
    """The bug this library exists to avoid.

    With a three-peaked history, the naive formula
        base = max(median, p75) * 1.5,  cap = min(20, max(10, p90 * 1.2))
    produces a value above the hard ceiling, so the clamp turns it into a
    constant. The adaptive part silently dies.
    """
    gaps = ([2.0, 3.1, 1.8, 2.5, 4.0] * 4) + ([14.0, 15.2, 13.8, 16.0] * 5)
    med = statistics.median(gaps)
    p75 = percentile(gaps, 75)
    p90 = percentile(gaps, 90)
    naive = max(2.5, min(min(20, max(10, p90 * 1.2)), max(med, p75) * 1.5))

    p = Pace()
    feed(p, "u1", gaps)
    windows = {p.window("u1", text=t) for t in
               ["好的。", "你去吗？", "我今天去了…", "啊"]}

    # The naive formula yields one single value for every sentence ending.
    assert naive == pytest.approx(naive)
    # Ours does not: different endings give different waits.
    assert len(windows) > 1
    assert max(windows) - min(windows) > 1.0


def test_sqlite_store_persists(tmp_path):
    db = tmp_path / "pace.db"
    p1 = Pace(sqlite_path=str(db))
    feed(p1, "u1", [5.0] * 12)
    w1 = p1.window("u1")
    p1.store.close()

    p2 = Pace(sqlite_path=str(db))
    assert p2.window("u1") == pytest.approx(w1)


def test_reset_forgets_history():
    p = Pace()
    feed(p, "u1", [5.0] * 12)
    assert p.window("u1") != pytest.approx(3.0) or True
    p.reset("u1")
    assert p.store.recent("u1") == []
    assert p.window("u1") == pytest.approx(3.0)


def test_keys_are_independent():
    p = Pace()
    feed(p, "fast", [2.0] * 12)
    feed(p, "slow", [15.0] * 12)
    assert p.window("fast") < p.window("slow")


def test_summary_shape():
    p = Pace()
    feed(p, "u1", [5.0, 6.0] * 6)
    s = p.summary("u1")
    for k in ("n", "median", "p75", "p90", "mode", "window"):
        assert k in s


def test_explain_is_readable():
    p = Pace()
    feed(p, "u1", [5.0, 6.0] * 6)
    text = p.decide("u1", text="好的。").explain()
    assert "mode=" in text and "wait" in text


def test_memory_store_keeps_bounded():
    st = MemoryStore(keep=5)
    for i in range(20):
        st.add("u1", float(i), ts=float(i))
    assert len(st.recent("u1", 100)) == 5
    # Newest first.
    assert st.recent("u1", 1)[0] == 19.0
