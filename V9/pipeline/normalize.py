"""Turns an uploaded MP4 into a frozen clip: H.264, 8-bit yuv420p, constant frame rate, even dimensions.
A clip that already complies is copied untouched. Otherwise it is encoded once, with everything fixed
in one command. Frame numbers depend on the frozen clip, so it is never encoded again."""
import json, os, shutil, subprocess
import config

PROBE_TIMEOUT = 120    # seconds; a crafted file must not hang the server
ENCODE_TIMEOUT = 900


def probe(path):
    try:
        out = _probe(path)
    except subprocess.TimeoutExpired:
        raise ValueError("not a readable video: ffprobe took too long")
    streams = json.loads(out.stdout or "{}").get("streams") if out.returncode == 0 else None
    if not streams:
        raise ValueError(f"not a readable video: {out.stderr.strip()[:200]}")
    return streams[0]


def _probe(path):
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                          "stream=codec_name,pix_fmt,width,height,r_frame_rate,avg_frame_rate,nb_read_packets,duration",
                          "-of", "json", path], capture_output=True, text=True, timeout=PROBE_TIMEOUT)


def rate(text):
    num, _, den = str(text).partition("/")
    return float(num) / float(den or 1) if float(den or 1) else 0.0


def problems(info):
    found = []
    if info.get("codec_name") != "h264":
        found.append(f"codec is {info.get('codec_name')}")
    if info.get("pix_fmt") != "yuv420p":
        found.append(f"pixel format is {info.get('pix_fmt')}")
    if abs(rate(info.get("r_frame_rate", 0)) - rate(info.get("avg_frame_rate", 0))) > 0.01:
        found.append(f"variable frame rate ({info.get('r_frame_rate')} vs {info.get('avg_frame_rate')})")
    if info.get("width", 0) % 2 or info.get("height", 0) % 2:
        found.append("odd dimensions")
    return found


def encode_command(src, dst, info, start=None, end=None):
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if start is not None:
        cmd += ["-ss", str(start)]
    cmd += ["-i", src]
    if end is not None:
        cmd += ["-t", str(end - (start or 0))]
    # out_range and format also convert full-range sources, which -pix_fmt alone leaves as yuvj420p
    cmd += ["-vf", f"scale=trunc(iw/2)*2:trunc(ih/2)*2:out_range=tv,format=yuv420p,fps={info['avg_frame_rate']}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "veryfast",
            *(config.X264_LOW_MEMORY if config.LOW_MEMORY else []),
            "-c:a", "aac", "-movflags", "+faststart", dst]
    return cmd


def normalize(src, out_dir, start=None, end=None):
    """Returns the metadata of the frozen clip. start and end are optional trim points in seconds."""
    if start is not None and end is not None and end <= start:
        raise ValueError("the trim end must be after the trim start")
    info = probe(src)
    if rate(info.get("avg_frame_rate", 0)) <= 0:
        raise ValueError("could not read the frame rate")
    clip = os.path.join(out_dir, "clip.mp4")
    found = problems(info)
    trimmed = start is not None or end is not None
    if found or trimmed:
        print(f"  encoding once: {', '.join(found) or 'trim requested'}")
        try:
            done = subprocess.run(encode_command(src, clip, info, start, end), capture_output=True, text=True,
                                  timeout=ENCODE_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise RuntimeError("ffmpeg took too long to encode the clip")
        if done.returncode:
            raise RuntimeError(f"ffmpeg failed: {done.stderr.strip()[:300]}")
    else:
        print("  already compliant, kept as it is")
        shutil.copyfile(src, clip)
    final = probe(clip)
    left = problems(final)
    if left:
        raise RuntimeError(f"clip still not compliant: {', '.join(left)}")
    meta = {"fps": rate(final["avg_frame_rate"]), "fps_rational": final["avg_frame_rate"],
            "frames": int(final.get("nb_read_packets", 0)), "width": final["width"], "height": final["height"],
            "encoded": bool(found or trimmed)}
    with open(os.path.join(out_dir, "clip.meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    return meta
