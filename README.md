# Why this decision?

Fans see an official's call during a live match but not the reason for it. Press **Why this decision?** on a clip of
the call and you get the rule in plain words for beginners, then a 0.5x replay that pauses at each key moment with a
caption and a marker on the action. It covers cricket, football, basketball and tennis.

**Live app:** https://why-this-decision.onrender.com (password-protected; the password is shared with evaluators
separately). Everything runs live: each clip is analysed when you press the button, nothing is precomputed. The
first visit after a quiet spell takes about a minute while the free server wakes up, and a run takes about 2 to 4
minutes.

## How it works

1. **Rule:** the official rulebook (MCC Laws of Cricket, IFAB Laws of the Game, NBA rules, Rules of Tennis) is looked
   up by exact section, simplified by Gemini, checked against the source text and cached.
2. **Key moments:** numbered contact sheets of the clip's frames go to Gemini (3.6 Flash first, then 3.5 Flash and
   3.5 Flash-Lite as fallbacks), and each moment is re-checked on zoomed crops.
3. **Captions and markers:** Gemini writes the captions; frames only ever come from detection. Jev (TypeSafe) boxes
   the action for the markers.
4. **Video:** the rule card, the slow replay with pauses and a summary card are rendered into one MP4.

## What is where

| Path | What it is |
|---|---|
| [`V9/`](V9/) | The app that runs online: Flask page, pipeline, per-sport rules and prompts, tests. **Details in [`V9/README.md`](V9/README.md)** |
| [`render.yaml`](render.yaml) | Deploys `V9/` to Render's free plan |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | The design the build follows |
| `videos/` | Source clips used while developing |
| `tests/` | Early experiments (contact sheets, Jev, Gemma), kept for reference |

Earlier versions (V1 to V8) are in the git history.

## Run it locally

From `V9/`, with Python 3.12, ffmpeg and a `GEMINI_API_KEY` in the project's `.env`:

```
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5002. Unit tests: `pip install pytest`, then `python -m pytest tests -q`.

## AI tools used

Gemini 3.6 Flash, 3.5 Flash and 3.5 Flash-Lite (moment detection), Gemini 3.1 Flash-Lite (rule simplification and
captions), Jev by TypeSafe (markers), and Claude Code (helped build, test and deploy).
