"""Second-layer tests. No real clips and no API calls."""
import os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import verify


def moment(key, frame, **extra):
    return {"key": key, "label": key, "frame": frame, "timestamp": frame / 25, "evidence": "first", **extra}


WINDOWS = {"a": [8, 9, 10, 11, 12], "b": [18, 19, 20, 21, 22]}


def run(answers, derived=None, extra=()):
    moments = [moment("a", 10), moment("b", 20), *extra]
    return verify.apply_answers(moments, answers, WINDOWS, derived or {}, 25)


def test_moved_frame_updates_time_and_evidence():
    kept, removed, changes = run({"a": {"frame": 11, "evidence": "zoomed"}, "b": {"frame": 20}})
    assert kept[0]["frame"] == 11 and kept[0]["timestamp"] == 0.44 and kept[0]["evidence"] == "zoomed"
    assert changes == [{"key": "a", "from": 10, "to": 11}] and not removed


def test_null_removes_the_moment():
    kept, removed, _ = run({"a": {"frame": 10}, "b": {"frame": None}})
    assert [m["key"] for m in kept] == ["a"] and removed[0]["key"] == "b"


def test_frame_outside_the_window_is_ignored():
    kept, _, changes = run({"a": {"frame": 99}, "b": {"frame": 20}})
    assert kept[0]["frame"] == 10 and not changes


def test_missing_reply_keeps_the_first_answer():
    kept, removed, _ = run({})
    assert [m["frame"] for m in kept] == [10, 20] and not removed


def test_time_order_is_kept():
    windows = {"a": [10, 11, 12], "b": [10, 11, 12]}
    moments = [moment("a", 11), moment("b", 12)]
    kept, _, _ = verify.apply_answers(moments, {"a": {"frame": 12}, "b": {"frame": 10}}, windows, {}, 25)
    assert [m["frame"] for m in kept] == [12, 12]


def test_derived_moment_follows_its_source():
    extra = [moment("miss", 19, derived=True)]
    kept, _, _ = run({"a": {"frame": 10}, "b": {"frame": 21}}, {"miss": ("b", -1)}, extra)
    assert next(m for m in kept if m["key"] == "miss")["frame"] == 20


def test_crop_stays_inside_the_frame():
    frame = np.zeros((1080, 1920, 3), np.uint8)
    assert verify.crop(frame, None).shape == frame.shape
    for box in [(0.0, 0.1, 0.0, 0.1), (0.9, 1.0, 0.9, 1.0), (0.4, 0.6, 0.45, 0.55)]:
        c = verify.crop(frame, box)
        assert c.shape[0] > 0 and c.shape[1] > 0 and c.shape[0] <= 1080


def test_targets_people_not_the_ball():
    assert verify.target_for("football", "referee_signal") == "the referee"
    assert verify.target_for("cricket", "umpire_signal") == "the umpire"
    assert verify.target_for("cricket", "stumps_hit").endswith("batter's end")
    assert verify.target_for("cricket", "ball_reaches_boundary") is None


def test_gemini_failure_changes_nothing(tmp_path, monkeypatch):
    def fail(*a, **k):
        raise RuntimeError("no")
    class Fake:
        def __len__(self):
            return 30

        def read(self, wanted):
            return {i: np.zeros((90, 160, 3), np.uint8) for i in wanted}
    monkeypatch.setattr(verify, "open_clip", lambda clip: Fake())
    monkeypatch.setattr(verify, "jev_box", lambda f, t: None)
    monkeypatch.setattr(verify.llm, "generate", fail)
    detections = {"moments": [moment("release", 10)], "rejected": []}
    event = {"sport": "cricket"}
    assert verify.verify("x", "bowled", event, detections, str(tmp_path), 25) is detections
