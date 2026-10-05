from sparky.mock import find_transcript, load_transcripts, normalize, replay

Q = "Why is Program Q's melt rate so much higher than Program S's this term?"


def test_normalize_ignores_case_and_punctuation():
    assert normalize("Why is  Program Q's rate?") == normalize("why is program q s rate")


def test_seed_transcripts_cover_all_three_arms():
    t = load_transcripts("demo/transcripts.yaml")
    for arm in ("arm1", "arm2", "arm3"):
        assert find_transcript(t, arm, Q), arm
    assert find_transcript(t, "arm3", "something else") is None
    assert any(e["type"] == "cite" for e in find_transcript(t, "arm3", Q))
    assert not any(e["type"] == "cite" for e in find_transcript(t, "arm2", Q))


async def test_replay_streams_then_completes():
    evs = [e async for e in replay([{"type": "text", "text": "a b c d e"}], delay=0)]
    kinds = [e["type"] for e in evs]
    assert kinds[0] == "replay" and kinds[-1] == "done" and "text" in kinds
    assert "".join(e["text"] for e in evs if e["type"] == "text_delta") == "a b c d e"
