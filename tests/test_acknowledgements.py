"""Chinese acknowledgements that need no punctuation to count as finished."""

import pytest

from human_pace.signals import DONE_CAP, read_signal


@pytest.mark.parametrize(
    "text",
    [
        "好的",
        "好",
        "行",
        "行吧",
        "嗯",
        "嗯嗯",
        "对",
        "是的",
        "知道了",
        "明白了",
        "收到",
        "可以",
        "没问题",
        "晚安",
        "笑死",
        "好的。",
        "行！",
    ],
)
def test_acknowledgement_is_finished(text):
    s = read_signal(text)
    assert s.done is True, text
    assert s.cap == DONE_CAP, text


@pytest.mark.parametrize(
    "text",
    [
        "我今天下午去了一趟那个…",
        "还有个事，",
        "我跟你说",
    ],
)
def test_unfinished_stays_unfinished(text):
    s = read_signal(text)
    assert s.done is False, text


def test_bare_syllable_is_still_ambiguous():
    # Not in the acknowledgement list: still reads as possibly more coming.
    s = read_signal("啊")
    assert s.done is False


def test_acknowledgement_beats_short_fragment_rule():
    """The bug this protects against.

    "好的" is 2 characters, so a length-only rule classifies it as an
    unfinished fragment and waits 8 seconds. In Chinese chat that is the most
    common complete reply there is.
    """
    assert read_signal("好的").mult < read_signal("啊").mult
    assert read_signal("好的").cap == DONE_CAP
