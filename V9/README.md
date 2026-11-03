---
title: Why this decision
emoji: 🏏
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Why this decision? — V9

V9 is today's V7 pipeline with the protections it needs to go online, built for a free Hugging Face Docker Space.
The pipeline (detection, zoomed check, captions, markers, render) is the same code as V7. Only the web app,
the packaging and a few input checks were added. Locally, without `PUBLIC=1`, it behaves like V7.

## Run it locally

From `C:\dream11_project\V9`, with `.venv` active:

```
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5002 (V7 keeps 5001). It reads the API keys from the project's `.env`.
Locally there is no password, no limits, and old jobs are kept.

Unit tests (no real clips, no API calls): `pip install pytest`, then `python -m pytest tests -q`

## What protects it online (`PUBLIC=1`, set by the Dockerfile)

| Threat | Protection |
|---|---|
| Strangers using it | `APP_PASSWORD` on every page and every request, at least 12 characters, or the app will not start |
| Password guessing | 5 wrong tries from one address means a 15 minute wait |
| Forged requests | Every post, the login included, needs a token from the page itself |
| Script injection | Content-Security-Policy with a fresh nonce per page: only the page's own script and style run. Every text the AI writes is shown as plain text, never as HTML |
| Clickjacking | The page can only be framed by itself and huggingface.co |
| Stolen cookies | HttpOnly, Secure, Partitioned; a fresh session at login; 12 hour expiry |
| Using up the Gemini quota | `DAILY_JOBS` (default 10) for everyone, `VISITOR_DAILY_JOBS` (default 3) per login, at most 3 jobs waiting at once |
| Huge or crafted uploads | 300 MB at most. ffprobe must read it as a video within 2 minutes, at most 1080p and 2 minutes long. Start and end must be real numbers of seconds |
| Hung processes | ffprobe stops after 2 minutes and ffmpeg after 15; each Gemini call after 3 minutes |
| Other people's results | A job's status and video are only shown to the login that started it; job IDs are random |
| Leftover files | Jobs are deleted after 24 hours |
| Error details | The page shows a plain message; details go only to the server log |
| API keys | Only from the Space's secrets. `.env` is never copied into the image, and keys never reach the browser |
| Changing dependencies | Every package is pinned to a tested version |
| Container | Runs as an unprivileged user (uid 1000), one gunicorn worker |
| YouTube downloads | Only clips listed in `library.json` are ever fetched, by an 11-character video ID; a visitor can never make the server download a link of their own. 300 MB and 3 minutes at most per clip, no `--exec`, partial files deleted, and the fetched clip still passes the same upload checks before a run |

What it does not protect against: anyone with the password can share it, and logging out and in again gives a new
per-visitor count (the daily total still holds). Change `APP_PASSWORD` in the Space's secrets to cut everyone off.

## Deploy to a Hugging Face Space (free)

1. Optional but recommended, on your computer, from `V9`: `python pack_clips.py`. It copies the library clips into
   `clips/`, so they are in the image and never need YouTube online. Clips left out are fetched from YouTube on first use.
2. Create a Space at https://huggingface.co/new-space: SDK **Docker**, hardware **CPU basic (free)**.
   Choose **Private** if only you will open it; choose **Public** if evaluators should reach it (the password still
   guards the app, but a public Space shows its files, the clips included).
3. In the Space's **Settings → Variables and secrets**, add these as **secrets**:
   - `GEMINI_API_KEY`: a key from a **separate Google Cloud project with billing off**, only for this Space, restricted
     to the Generative Language API. With billing off, abuse can only use up the free quota, never cost money.
   - `TYPESAFE_API_KEY`: for the markers (optional; without it there are none)
   - `APP_PASSWORD`: a long random password, sent only to the people who should use it
   - `SECRET_KEY`: a long random string, so logins survive a restart (optional)
   - `YT_COOKIES`: only if YouTube refuses the Space (see below)
   - `DAILY_JOBS` and `VISITOR_DAILY_JOBS` as variables, if the defaults do not fit
4. Upload from `V9` (needs `pip install huggingface_hub` and `hf auth login` with a write token):

   ```
   hf upload <user>/<space> . . --repo-type space --exclude "jobs/*" "tests/*" "__pycache__/*" ".env*"
   ```

5. The Space builds the image and starts. The app is at `https://<user>-<space>.hf.space`.

A random password or key: `python -c "import secrets; print(secrets.token_urlsafe(24))"`

Limits of the free Space: it sleeps after about two days without visitors and takes a minute or two to wake, its disk
is wiped on restart (jobs and the daily counts start again), and a run takes several minutes on its 2 CPUs.

## YouTube online

The clip table plays each YouTube section in the visitor's own browser, as before. When a clip is selected and is not
already in `clips/`, the server cuts that section with `yt-dlp` the first time, saves it, and reuses it after that
(until the Space restarts and its disk is wiped). To turn this off, set the variable `ALLOW_FETCH` to `0`.

YouTube often asks cloud servers to "sign in to confirm you're not a bot". If the Space log shows that:

1. Make a **spare** Google account, not your own (YouTube can block an account used from a server).
2. Signed in with it, export the youtube.com cookies as `cookies.txt` with a cookies-export browser extension.
3. Paste the whole file into a Space secret named `YT_COOKIES`. The app writes it to a private file (only the app
   user can read it) and passes it to yt-dlp. It is never sent to the browser.

If YouTube still refuses, packing the clips with `pack_clips.py` always works. YouTube changes often, so if
fetching breaks, raise `yt-dlp` in `requirements.txt` to its newest release.

## Memory

Frames are read from the clip as each stage needs them (`pipeline/frames.py`), never the whole clip at once, and the
contact sheets go to Gemini as their JPEG files. Measured on a 1080p clip with Gemini faked:

| Stage | Before | Now |
|---|---|---|
| Detection and zoomed check, 10 s clip | 2,301 MB | 268 MB |
| Detection, 60 s clip | about 13 GB (would crash) | 262 MB |
| Render, Python + ffmpeg | 153 + 364 MB | 153 + 122 MB with `LOW_MEMORY=1` |

The contact sheets are byte-for-byte the same as before, so the frames Gemini sees did not change.
`LOW_MEMORY=1` (set in the Dockerfile) runs the video encoder with 2 threads and no look-ahead: the output file is
about 50% bigger at the same quality setting. A whole run fits in about 0.5 GB, so small free hosts become possible.

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

Models: detection and the zoomed check try `gemini-3.6-flash` twice, `gemini-3.5-flash` twice, `gemini-3.5-flash-lite`
once, then `gemini-3.8-flash`. Frames go to Gemini at the clip's own size. Rule and caption text uses `gemini-3.1-flash-lite`.

## Change things here

- `sports/<sport>/decisions.py`: every decision and every prompt.
- `config.py`: models, fallback order, pause length, slow-motion speed, and the online limits.

## The clip table

"Select from here" lists the clips in `library.json`: a YouTube ID, the start and end in seconds, the sport, a
description and a decision key. `file` is optional: the MP4's path inside `videos/`. Locally, a clip without a saved
MP4 is cut once with `yt-dlp`, online too (see "YouTube online").

The rest (Cricsheet, StatsBomb, sports, limits) is as in `V7/README.md`. Results are in `RESULTS.md`, copied from V7.
