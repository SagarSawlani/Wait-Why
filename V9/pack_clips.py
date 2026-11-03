"""Copies every library clip into V8/clips, so the online app never needs yt-dlp.
Run from V8 before uploading: python pack_clips.py
Clips that were never cut are cut first with yt-dlp, on this computer."""
import os, shutil, sys
import app as web
import config

OUT = os.path.join(config.ROOT, "clips")


def main():
    missing = []
    for clip in web.LIBRARY:
        name = web.library_file(clip)
        try:
            source = web.fetch_clip(clip)
        except RuntimeError as e:
            missing.append(f"{name}: {e}")
            continue
        target = os.path.join(OUT, name)
        problem = web.check_clip(source)
        if problem:   # the online app would refuse it, so it is left out and hidden from the table
            print(f"SKIP {name}: {problem}")
            if os.path.isfile(target):
                os.remove(target)
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if not os.path.isfile(target) or os.path.getsize(target) != os.path.getsize(source):
            shutil.copyfile(source, target)
        print(f"ok   {name}")
    for line in missing:
        print("MISSING", line)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
