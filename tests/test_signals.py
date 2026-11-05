"""Sentence-end signals."""

from human_pace.signals import (
    ASK_CAP,
    DONE_CAP,
    SHORT_FRAGMENT_CAP,
    read_signal,
)


def test_empty_text_is_neutral():
    s = read_signal("")
    assert s.mult == 1.0
    assert s.cap is None
    assert s.done is False


def test_question_gets_fastest_reply():
    for text in ["你去吗？", "在吗?", "行不行。", "真的吗", "你来不来"]:
        s = read_signal(text)
        assert s.done is True, text
        assert s.cap == ASK_CAP, text
        assert s.mult < 0.5, text


def test_period_is_done_and_capped():
    for text in ["好的。", "行！", "知道了~"]:
        s = read_signal(text)
        assert s.done is True, text
        assert s.cap == DONE_CAP, text


def test_trailing_off_means_keep_waiting():
    for text in ["我今天去了…", "我今天去了..."]:
        s = read_signal(text)
        assert s.done is False, text
        assert s.mult > 1.0, text
        assert s.cap is None, text


def test_comma_means_more_coming():
    for text in ["还有一点，", "我跟你说：", "那个人—"]:
        s = read_signal(text)
        assert s.done is False, text
        assert s.mult > 1.0, text


def test_short_fragment_is_ambiguous_but_capped():
    s = read_signal("啊")
    assert s.done is False
    assert s.cap == SHORT_FRAGMENT_CAP


def test_long_unpunctuated_reads_as_finished():
    s = read_signal("今天下午我把那个事弄完了然后就想跟你说一声")
    assert s.done is True
    assert s.mult < 1.0


def test_trailing_whitespace_is_ignored():
    assert read_signal("好的。   ").reason == read_signal("好的。").reason
