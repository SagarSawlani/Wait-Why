# Why this decision? — V4

Upload a clip of an official's decision in cricket, football, basketball or tennis. You get back a video with the rule explained, a 0.5x replay, and a pause
with a caption at each key moment.

## Run it

From `C:\dream11_project\V4`, with `.venv` active:

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
| Check | `pipeline/verify.py` | Re-checks each moment on zoomed crops, then keeps, moves or removes it |
| Captions | `pipeline/plan.py` | The LLM writes the words. Frames come only from detection |
| Video | `pipeline/render.py` | Renders the rule card, slow replay with pauses, and end card |

Each run is saved in `jobs/<id>/`: `clip.mp4`, `event.json`, `rule.json`, `detections.json`, `plan.json`, `output.mp4`.

## Change things here

- `sports/cricket/decisions.py`: every decision and every prompt. Add one entry to add a decision.
- `config.py`: models, fallback order, pause length, slow-motion speed.

Models: detection and the zoomed check try `gemini-3.5-flash-lite` twice. 3.8 and 3.6 are skipped for now.
Rule and caption text uses `gemini-3.1-flash-lite`.

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
- No spotlight boxes yet: `highlight` in `plan.json` is left empty for the Jev step.
- Basketball and tennis have passed unit tests only, with no real clip yet.
- Limited-overs wides, bouncer limits and DRS come from competition rules, not the Laws, so V1 cannot quote them.
- Laws: 2022 edition for matches before 1 October 2026, and the 2026 edition otherwise.
