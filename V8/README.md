---
title: Why this decision
emoji: 🏏
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Why this decision? — V8

V7 made safe to put online. The pipeline is the same as V7; only the web app, the clip table and the packaging changed.
Upload a clip of an official's decision in cricket, football, basketball or tennis. You get back a video with the rule
explained, a 0.5x replay, and a pause with a caption at each key moment.

## Run it locally

From `C:\dream11_project\V8`, with `.venv` active:

```
python app.py
```

Open http://127.0.0.1:5001. It reads the API keys from the project's `.env`. Locally there is no password, no limits,
and old jobs are kept, exactly like V7.

Unit tests (no real clips, no API calls): `python -m pytest tests -q`

## What changes online (`PUBLIC=1`, set by the Dockerfile)

| Protection | How |
|---|---|
| Password on every page | `APP_PASSWORD` secret, at least 12 characters, or the app will not start. 5 wrong tries from one address means a 15 minute wait |
| Forged requests | Every post needs the page's CSRF token. Cookies are HttpOnly, Secure and Partitioned, so they work inside the Hugging Face page |
| Quota | `DAILY_JOBS` (default 10) for everyone, `VISITOR_DAILY_JOBS` (default 3) per login, at most 3 jobs waiting at once |
| Uploads | 300 MB at most. ffprobe must read it as a video, at most 1080p, and its frames must fit in 6 GB of memory (about 1,000 frames at 1080p, 2,300 at 720p) |
| Other people's results | A job's status and video are only shown to the login that started it |
| Old files | Jobs are deleted after 24 hours |
| Errors | The page shows a plain message; details go only to the server log |
| Headers | Content-Security-Policy, nosniff, HSTS, no-store on pages |
| Keys | Only from the Space's secrets. `.env` is never copied into the image |
| YouTube | yt-dlp is not installed, because YouTube blocks most cloud servers. The table only lists clips packed by `pack_clips.py` |

## Deploy to a Hugging Face Space (free)

1. On this computer, from `V8`: `python pack_clips.py`. It copies the library clips into `clips/` and leaves out
   any that would be refused online (3 of them now: too many frames).
2. Create a Space at https://huggingface.co/new-space: SDK **Docker**, hardware **CPU basic (free)**.
3. In the Space's **Settings → Variables and secrets**, add these as **secrets**:
   - `GEMINI_API_KEY`: a key from a separate Google Cloud project, only for this Space
   - `TYPESAFE_API_KEY`: for the markers (optional; without it there are none)
   - `APP_PASSWORD`: a long random password, sent to the people who should use it
   - `SECRET_KEY`: a long random string, so logins survive a restart (optional)
   - `DAILY_JOBS` and `VISITOR_DAILY_JOBS` as variables, if the defaults do not fit
4. Upload from `V8` (needs `pip install huggingface_hub` and `hf auth login` with a write token):

   ```
   hf upload <user>/<space> . . --repo-type space --exclude "jobs/*" "tests/*" "__pycache__/*" ".env*"
   ```

5. The Space builds the image and starts. The app is at `https://<user>-<space>.hf.space`.

A random password or key: `python -c "import secrets; print(secrets.token_urlsafe(24))"`

Limits of the free Space: it sleeps after about two days without visitors and takes a minute or two to wake, its disk
is wiped on restart (jobs and the daily counts start again), and a public Space shows its files, clips included.

## How one clip is processed

| Stage | File | What happens |
|---|---|---|
| Normalize | `pipeline/normalize.py` | Keeps a compliant clip untouched. Otherwise encodes once to H.264, yuv420p, constant frame rate |
| Event | `sports/<sport>/events.py` | Reads one ball from a Cricsheet file, or uses the decision chosen on the page |
| Rule | `pipeline/rules.py` | Looks up the Law by exact mapping, simplifies it with an LLM, validates citations, caches |
| Moments | `pipeline/detect.py` | Sends numbered contact sheets to Gemini and validates the frames |
| Check | `pipeline/verify.py` | Re-checks each moment on zoomed crops, then keeps, moves or removes it |
| Captions | `pipeline/plan.py` | The LLM writes the words. Frames come only from detection |
| Markers | `pipeline/spotlight.py` | Jev finds what `sports/<sport>/marks.py` lists at each moment, and its presence score decides if a marker is drawn |
| Video | `pipeline/render.py` | Renders the rule card, slow replay with pauses, and end card |

Each run is saved in `jobs/<id>/`: `clip.mp4`, `event.json`, `rule.json`, `detections.json`, `plan.json`, `markers.json`, `output.mp4`.

## Change things here

- `sports/<sport>/decisions.py`: every decision and every prompt.
- `config.py`: models, fallback order, pause length, slow-motion speed, and the online limits.

## The clip table

"Select from here" lists the clips in `library.json`: a YouTube ID, the start and end in seconds, the sport, a
description and a decision key. `file` is optional: the MP4's path inside `videos/`. Locally, a clip without a saved
MP4 is cut once with `yt-dlp`. Online, the clips come from `clips/`.

The rest (Cricsheet, StatsBomb, sports, limits) is as in `V7/README.md`.
