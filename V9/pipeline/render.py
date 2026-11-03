"""Renders the output MP4: rule card, 0.5x replay with a pause and caption at each moment, then a summary card.
Frames are piped to ffmpeg, so the output is always plain H.264 and plays in any browser."""
import functools, subprocess
from fractions import Fraction
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import config

FONT_FILES = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"]
BOLD_FILES = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "DejaVuSans-Bold.ttf"]
CLOSE_UP = 0.75      # a person taller than this share of the frame gets an arrow, not a huge ellipse
CAPTION_TOP = 0.74   # a marker lower than this moves the caption bar to the top of the frame
INK, MUTED, ACCENT, BAR = (245, 245, 240), (190, 190, 182), (255, 196, 61), (16, 18, 22)


@functools.lru_cache(maxsize=None)   # looking a font up searches the system font folders; once per size is enough
def font(size, bold=False):
    for name in BOLD_FILES if bold else FONT_FILES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap(draw, text, fnt, width):
    """Wraps by measured width, so it works for any resolution and font."""
    lines = []
    for chunk in str(text).split("\n"):
        line = ""
        for word in chunk.split():
            trial = f"{line} {word}".strip()
            if draw.textlength(trial, font=fnt) <= width or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def to_bgr(img):
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def card(width, height, title, body, bullets=(), footer=""):
    """A full-frame text card."""
    img = Image.new("RGB", (width, height), BAR)
    draw = ImageDraw.Draw(img)
    unit = height / 30
    margin, y, usable = int(width * 0.08), int(height * 0.13), int(width * 0.84)
    title_font, body_font = font(int(unit * 2.2), True), font(int(unit * 1.3))
    small = font(int(unit * 1.05))
    for line in wrap(draw, title, title_font, usable):
        draw.text((margin, y), line, font=title_font, fill=ACCENT)
        y += int(unit * 2.8)
    y += int(unit)
    for line in wrap(draw, body, body_font, usable):
        draw.text((margin, y), line, font=body_font, fill=INK)
        y += int(unit * 1.8)
    y += int(unit)
    for bullet in bullets:
        for i, line in enumerate(wrap(draw, bullet, small, usable - int(unit * 1.5))):
            if i == 0:
                draw.text((margin, y), "•", font=small, fill=ACCENT)
            draw.text((margin + int(unit * 1.3), y), line, font=small, fill=MUTED)
            y += int(unit * 1.5)
    if footer:
        draw.text((margin, height - int(unit * 2.5)), footer, font=small, fill=MUTED)
    return to_bgr(img)


def marker(frame, highlight):
    """Draws the marker on a copy of the frame. A dark line under a bright one shows on any background."""
    image = frame.copy()
    h, w = image.shape[:2]
    box = highlight["box"]
    left, right, top, bottom = box["left"] * w, box["right"] * w, box["top"] * h, box["bottom"] * h
    cx, cy = (left + right) / 2, (top + bottom) / 2
    line = max(2, h // 300)
    bgr = ACCENT[::-1]

    def ellipse(centre, axes):
        for colour, width in (((0, 0, 0), line + 2), (bgr, line)):
            cv2.ellipse(image, (int(centre[0]), int(centre[1])), (int(axes[0]), int(axes[1])), 0, 0, 360, colour,
                        width, cv2.LINE_AA)

    shape = highlight["shape"]
    close_up = False
    if shape == "feet" and bottom - top > h * CLOSE_UP:
        close_up, shape = True, "arrow"
    if shape == "arrow":
        side = 1 if cx < w / 2 else -1     # the tail comes from the side with more room
        length, gap = min(h * 0.2, max(h * 0.14, (bottom - top) * 0.7)), h * 0.015
        tip = (cx, top - gap)
        tail = (cx + side * length * 0.6, top - gap - length)
        if tail[1] < 0 or close_up:        # no room above, so come in from the side
            tip = (right + gap if side > 0 else left - gap, top + (bottom - top) * 0.3 if close_up else cy)
            tail = (min(max(tip[0] + side * length, 0), w - 1), tip[1])
        for colour, width in (((0, 0, 0), line + 2), (bgr, line)):
            cv2.arrowedLine(image, (int(tail[0]), int(tail[1])), (int(tip[0]), int(tip[1])), colour, width, cv2.LINE_AA,
                            tipLength=min(0.35, h * 0.045 / max(abs(tail[0] - tip[0]) + abs(tail[1] - tip[1]), 1)))
    elif shape == "feet":
        width = max(right - left, h * 0.05)
        ellipse((cx, bottom), (width * 0.7, width * 0.2))
    else:
        size = max(right - left, bottom - top)
        ellipse((cx, cy), (max(size * 0.9, h * 0.022),) * 2)
    return image


def under_caption(step):
    return bool(step and step.get("highlight")) and step["highlight"]["box"]["bottom"] > CAPTION_TOP


def overlay(frame, step, position, steps):
    """Caption bar and a timeline with one marker per moment."""
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    unit = h / 30
    margin = int(w * 0.04)
    title_font, cap_font = font(int(unit * 1.25), True), font(int(unit * 1.1))
    if step:
        lines = wrap(draw, step["caption"], cap_font, w - 2 * margin)[:3]
        box = int(unit * 2.4 + len(lines) * unit * 1.5) + int(unit * 1.2)
        top = 0 if under_caption(step) else h - box
        draw.rectangle((0, top, w, top + box), fill=BAR + (225,))
        draw.text((margin, top + int(unit * 0.4)), step["title"], font=title_font, fill=ACCENT + (255,))
        y = top + int(unit * 2.0)
        for line in lines:
            draw.text((margin, y), line, font=cap_font, fill=INK + (255,))
            y += int(unit * 1.5)
    y = h - int(unit * 0.6)
    draw.line((margin, y, w - margin, y), fill=(255, 255, 255, 110), width=max(2, int(unit * 0.12)))
    span = w - 2 * margin
    draw.line((margin, y, margin + span * position, y), fill=ACCENT + (255,), width=max(2, int(unit * 0.12)))
    r = max(3, int(unit * 0.22))
    for s in steps:
        x = margin + span * s["position"]
        draw.ellipse((x - r, y - r, x + r, y + r), fill=ACCENT + (255,))
    return to_bgr(img)


def replay_window(plan, fps, frame_count):
    """The first and last frames to replay: a short lead-in before the first moment and a tail after the last."""
    frames = [s["frame"] for s in plan["steps"]]
    last = frame_count - 1
    if not frames:
        return 0, last
    return max(min(frames) - int(fps * config.LEAD_SECONDS), 0), min(max(frames) + int(fps * config.TAIL_SECONDS), last)


def where(frame, first, last):
    return min(max(frame - first, 0) / max(last - first, 1), 1)


def timeline(plan, first, last):
    return [{**s, "position": where(s["frame"], first, last)} for s in plan["steps"]]


def open_writer(path, width, height, fps_rational):
    return subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
         "-r", str(fps_rational), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
         "-preset", config.RENDER_PRESET_LOW_MEMORY if config.LOW_MEMORY else "veryfast",
         *(config.X264_LOW_MEMORY if config.LOW_MEMORY else []), "-movflags", "+faststart", path],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)


def output_size(width, height):
    """The output video's size. Low-memory hosts get at most OUTPUT_HEIGHT lines (even numbers, for H.264):
    drawing on and encoding a 1080p video was the biggest memory use of a run. Detection is unaffected."""
    if not config.LOW_MEMORY or height <= config.OUTPUT_HEIGHT:
        return width, height
    return int(width * config.OUTPUT_HEIGHT / height) // 2 * 2, config.OUTPUT_HEIGHT


def output_rate(meta):
    """The output frame rate: the clip's own rate divided by SLOWDOWN. Each clip frame is then written once and
    still shows for SLOWDOWN clip frames' time, which looks the same as writing it SLOWDOWN times at the clip's
    rate, for a fraction of the frames to draw and encode. Returns (rate as a string for ffmpeg, rate as a number)."""
    rate = Fraction(str(meta.get("fps_rational") or meta["fps"])).limit_denominator(100000) / config.SLOWDOWN
    return f"{rate.numerator}/{rate.denominator}", float(rate)


def render(clip, plan, meta, out_path):
    width, height = output_size(meta["width"], meta["height"])
    fps = meta["fps"]                    # the clip's rate: frame numbers and timestamps are in clip time
    rate_text, out_fps = output_rate(meta)
    held_frames = lambda seconds: max(1, round(out_fps * seconds))
    frame_count = max(meta.get("frames") or 0, 1)
    first, last = replay_window(plan, fps, frame_count)
    steps = timeline(plan, first, last)
    by_frame = {}
    for s in steps:
        by_frame.setdefault(s["frame"], []).append(s)

    writer = open_writer(out_path, width, height, rate_text)
    write = lambda image, count=1: [writer.stdin.write(image.tobytes()) for _ in range(count)]
    try:
        rule = plan["rule"]
        cited = ", ".join(rule.get("citations", []))
        bullets = rule.get("conditions", [])[:5] + [f"Does not count: {e}" for e in rule.get("exceptions", [])[:2]]
        write(card(width, height, plan["label"], rule["summary"], bullets,
                   f"{plan.get('rulebook', 'Laws of Cricket')}: {cited}" if cited else ""), held_frames(config.INTRO_SECONDS))
        cap = cv2.VideoCapture(clip)
        index, active = 0, None
        while True:
            if index < first:   # frames before the replay are skipped without being converted
                if not cap.grab():
                    break
                index += 1
                continue
            ok, frame = cap.read()
            if not ok or index > last:
                break
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_LINEAR)   # 30% less CPU than AREA; no visible difference
            if index >= first:
                for s in by_frame.get(index, []):
                    active = s
                    held = marker(frame, s["highlight"]) if s.get("highlight") else frame   # boxes only fit this frame
                    write(overlay(held, s, where(index, first, last), steps), held_frames(config.PAUSE_SECONDS))
                write(overlay(frame, active, where(index, first, last), steps))   # once: the output rate is slowed down
            index += 1
        cap.release()
        if not index:
            raise ValueError("could not read the clip for rendering")
        points = [f"{s['title']}: {s['caption']}" for s in steps]
        # limits are instructions for the caption LLM, so they never go on screen
        write(card(width, height, plan["headline"], rule["title"], points[:5], "AI-generated explanation"), held_frames(5))
        writer.stdin.close()
        err = writer.stderr.read().decode(errors="replace")
        if writer.wait():
            raise RuntimeError(f"ffmpeg failed: {err[:300]}")
    except OSError:   # Windows reports a closed pipe as a plain OSError
        raise RuntimeError(f"ffmpeg stopped: {writer.stderr.read().decode(errors='replace')[:300]}")
    return out_path
