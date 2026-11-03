# Why this decision? — V7

Upload a clip of an official's decision in cricket, football, basketball or tennis. You get back a video with the rule explained, a 0.5x replay, and a pause
with a caption at each key moment.

## Run it

From `C:\dream11_project\V6`, with `.venv` active:

```
python app.py
```

Open http://127.0.0.1:5001. It reads the API key from the project's existing `.env`.

Unit tests (no real clips, no API calls): `python -m pytest tests -q`

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
| Video | `pipeline/render.py` | Renders the rule card, slow replay with pauses, and end card. The replay runs from 3 s before the first moment to 2 s after the last, and the caption bar moves to the top when a marker is low in the frame |

Each run is saved in `jobs/<id>/`: `clip.mp4`, `event.json`, `rule.json`, `detections.json`, `plan.json`, `markers.json`, `output.mp4`.

## Change things here

- `sports/cricket/decisions.py`: every decision and every prompt. Add one entry to add a decision.
- `config.py`: models, fallback order, pause length, slow-motion speed.

Models: detection and the zoomed check try `gemini-3.6-flash` twice, `gemini-3.5-flash` twice, `gemini-3.5-flash-lite` once, then `gemini-3.8-flash`, which is often overloaded.
Rule and caption text uses `gemini-3.1-flash-lite`.

## The clip table

"Select from here" lists the clips in `library.json`. Each entry has a YouTube ID, the start and end in seconds, the sport,
a description and a decision key from that sport's `decisions.py`. `file` is optional: the MP4's path inside `videos/`.

The YouTube link plays only that section, inside the table. The run uses a local MP4. If there is none, selecting the clip
cuts that section with `yt-dlp` (and ffmpeg) into `videos/library/`, once, so it then stays the same frozen clip.

## Using Cricsheet

1. Find the match at https://cricsheet.org/matches/ and download its JSON.
2. Add it on the page, with the innings and the scorecard's over.ball, like `12.3`.
3. Leave the decision on "Take it from Cricsheet", or choose one to double-check the ball.

Cricsheet records scores, not every call. Choose short run, dead ball, not out or play suspended yourself.
All Cricsheet no-balls read as a general no ball, so choose front foot or height if you know which it was.
A live version would replace this step with a live feed writing the same event JSON.

## Sports

| Sport | Rulebook | Match data |
|---|---|---|
| Cricket | MCC Laws of Cricket | Cricsheet, optional |
| Football | IFAB Laws of the Game | StatsBomb, optional |
| Basketball | NBA Official Playing Rules 2026-27 | None yet: choose the decision on the page |
| Tennis | Rules of Tennis 2026, from Tennis Canada's Rules of the Court | None yet: choose the decision on the page |

To add a sport, add `sports/<sport>/` with `decisions.py`, `events.py`, `laws.py` and its parsed rulebook, then add it
to `SPORTS` in `app.py` and to the list on the page. `sports/shared.py` gives a new sport its prompts.

Basketball uses NBA rules, so FIBA games can differ. Tennis calls are often only spoken or electronic, so `call`
can be missing, and the ball is small, so landing frames are the weakest part.

## Limits

- Timing is usually within 1 to 2 frames, because every 2nd frame is sent (more on longer clips).
- The output video has no sound.
- Markers show only during a pause, because a box fits one frame. They need `TYPESAFE_API_KEY`; without it the video has none.
- Basketball and tennis have passed unit tests only, with no real clip yet.
- Limited-overs wides, bouncer limits and DRS come from competition rules, not the Laws, so V1 cannot quote them.
- Laws: 2022 edition for matches before 1 October 2026, and the 2026 edition otherwise.
