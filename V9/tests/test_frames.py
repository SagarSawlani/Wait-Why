import cv2
import numpy as np
import config
from pipeline import detect, normalize, render
from pipeline.frames import Clip


def make_clip(path, count=12, size=(64, 36)):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, size)
    for i in range(count):
        writer.write(np.full((size[1], size[0], 3), (i * 20) % 256, np.uint8))
    writer.release()
    return str(path)


def all_frames(path):
    cap, out = cv2.VideoCapture(path), []
    while True:
        ok, f = cap.read()
        if not ok:
            return out
        out.append(f)


def test_reads_only_the_wanted_frames_with_their_true_numbers(tmp_path):
    src = make_clip(tmp_path / "c.avi")
    full = all_frames(src)
    got = Clip(src).read([9, 2, 5])
    assert sorted(got) == [2, 5, 9]
    for i, f in got.items():
        assert np.array_equal(f, full[i])


def test_counts_frames_and_ignores_numbers_past_the_end(tmp_path):
    src = make_clip(tmp_path / "c.avi")
    clip = Clip(src)
    assert len(clip) == 12
    assert sorted(clip.read([11, 40])) == [11]
    assert clip.read([]) == {}


def test_sheets_from_a_clip_match_sheets_from_all_frames(tmp_path):
    src = make_clip(tmp_path / "c.avi", count=30)
    a = detect.build_sheets(all_frames(src), 2, str(tmp_path / "a"))
    b = detect.build_sheets(Clip(src), 2, str(tmp_path / "b"))
    assert a[0] == b[0] and len(a[1]) == len(b[1]) == 2
    for pa, pb in zip(a[1], b[1]):
        assert np.array_equal(cv2.imread(pa), cv2.imread(pb))


def test_low_memory_changes_only_the_encoder_settings(monkeypatch):
    info = {"avg_frame_rate": "25/1"}
    monkeypatch.setattr(config, "LOW_MEMORY", False)
    plain = normalize.encode_command("a.mp4", "b.mp4", info)
    monkeypatch.setattr(config, "LOW_MEMORY", True)
    small = normalize.encode_command("a.mp4", "b.mp4", info)
    assert [x for x in small if x not in config.X264_LOW_MEMORY] == plain
    assert "zerolatency" in small and "zerolatency" not in plain


def test_low_memory_renders_at_most_720p(monkeypatch):
    monkeypatch.setattr(config, "LOW_MEMORY", True)
    assert render.output_size(1920, 1080) == (1280, 720)
    assert render.output_size(1280, 720) == (1280, 720)
    assert render.output_size(640, 360) == (640, 360)
    assert all(v % 2 == 0 for v in render.output_size(1918, 1078))
    monkeypatch.setattr(config, "LOW_MEMORY", False)
    assert render.output_size(1920, 1080) == (1920, 1080)
