# Why this decision? — V2

Upload a clip of an umpire's decision. You get back a video with the rule explained, a 0.5x replay, and a pause
with a caption at each key moment.

## Run it

From `C:\dream11_project\V2`, with `.venv` active:

```
python app.py
```

Open http://127.0.0.1:5000. It reads the API key from the project's existing `.env`.

Unit tests (no real clips, no API calls): `python -m pytest tests -q`

## How one clip is processed

| Stage | File | What happens |
|---|---|---|
| Normalize | `pipeline/normalize.py` | Keeps a compliant clip untouched. Otherwise encodes once to H.264, yuv420p, constant frame rate |
| Event | `sports/<sport>/events.py` | Reads one ball from a Cricsheet file, or uses the decision chosen on the page |
| Rule | `pipeline/rules.py` | Looks up the Law by exact mapping, simplifies it with an LLM, validates citations, caches |
| Moments | `pipeline/detect.py` | Sends numbered contact sheets to Gemini and validates the frames |
| Captions | `pipeline/plan.py` | The LLM writes the words. Frames come only from detection |
| Video | `pipeline/render.py` | Renders the rule card, slow replay with pauses, and end card |

Each run is saved in `jobs/<id>/`: `clip.mp4`, `event.json`, `rule.json`, `detections.json`, `plan.json`, `output.mp4`.

## Change things here

- `sports/cricket/decisions.py`: every decision and every prompt. Add one entry to add a decision.
- `config.py`: models, fallback order, pause length, slow-motion speed.

Models: detection tries `gemini-3.8-flash` twice, then `gemini-3.6-flash` once, then `gemini-3.5-flash-lite` once.
Rule and caption text uses `gemini-3.1-flash-lite`.

## Using Cricsheet

1. Find the match at https://cricsheet.org/matches/ and download its JSON.
2. Add it on the page, with the innings and the scorecard's over.ball, like `12.3`.
3. Leave the decision on "Take it from Cricsheet", or choose one to double-check the ball.

Cricsheet records scores, not every call. Choose short run, dead ball, not out or play suspended yourself.
All Cricsheet no-balls read as a general no ball, so choose front foot or height if you know which it was.
A live version would replace this step with a live feed writing the same event JSON.

## Limits

- Timing is usually within 1 to 2 frames, because every 2nd frame is sent (more on longer clips).
- The output video has no sound.
- No spotlight boxes yet: `highlight` in `plan.json` is left empty for the Jev step.
- Limited-overs wides, bouncer limits and DRS come from competition rules, not the Laws, so V1 cannot quote them.
- Laws: 2022 edition for matches before 1 October 2026, and the 2026 edition otherwise.
