# Wait, Why?

**An AI explainer for officials' decisions in live sport.** A fan sees the umpire's finger go up, the offside flag,
the charge call, the "out" from the line judge, but not the reason. Give **Wait, Why?** a clip of the call and it
returns a short video that explains it for a beginner:

1. **The rule, in plain words**, taken from the official rulebook and cited by section.
2. **The moment again at half speed**, pausing at each key point (ball released, ball hits the pad, umpire signals),
   with a caption saying what happens and a marker on the action.

It works for **cricket, football, basketball and tennis**: 75 decisions in all, from LBW and no balls to offside,
charging, foot faults and electronic line calls.

**Live app:** https://wait-why.onrender.com (password-protected; the password is shared with evaluators
separately). Everything runs live: each clip is analysed when you press the button, nothing is precomputed. A run
takes about 2 to 4 minutes on the free server.

---

## Contents

- [The problem](#the-problem)
- [How a fan uses it](#how-a-fan-uses-it)
- [System architecture](#system-architecture)
- [The pipeline, stage by stage](#the-pipeline-stage-by-stage)
- [Sports and decisions](#sports-and-decisions)
- [Repository layout](#repository-layout)
- [Run it locally](#run-it-locally)
- [Limits](#limits)
- [Future plans](#future-plans)
- [AI tools used](#ai-tools-used)

---

## The problem

Officials' calls decide matches, but broadcasts show the outcome, not the reasoning. Replays loop the moment without
saying which rule applies or what to look for, and the rules themselves are long legal texts. Newer fans can't tell
why a batter was out LBW, why a goal was ruled offside or why a dunk became a charge, so the call feels arbitrary and
they lose trust in it.

## How a fan uses it

1. Open the app and log in.
2. **Add the clip:** upload an MP4, or press **Select from here** and pick one of 19 ready clips. Each clip can be
   previewed with **Watch** before choosing.
3. **Sport** and **decision:** pick the sport and the call (or, for cricket and football, let the match data name it).
4. Press **Explain this decision** and keep the page open. Progress shows stage by stage.
5. The result plays on the page and can be downloaded: a rule card, the slowed replay with pauses and captions, and
   a summary card.

---

## System architecture

```mermaid
flowchart TD
    U([Fan's browser]) -->|clip + sport + decision| W[Flask web app<br/>login, limits, upload checks]
    W --> N[1. Normalize<br/>H.264, constant frame rate, frozen once]
    N --> E[2. Event<br/>the decision, or a ball from Cricsheet / StatsBomb]
    E --> R[3. Rule<br/>exact lookup in the official rulebook]
    R -->|cached per decision| RS[Gemini 3.1 Flash-Lite<br/>simplifies for beginners, citations checked]
    N --> D[4. Find key moments<br/>numbered contact sheets of the frames]
    D --> G1[Gemini 3.6 Flash<br/>falls back to 3.5 Flash, then 3.5 Flash-Lite]
    G1 --> V[5. Zoomed check<br/>crops around each moment]
    V --> J1[Jev by TypeSafe<br/>boxes the person or object]
    V --> G2[Gemini 3.5 Flash-Lite<br/>keeps, moves or drops each moment]
    G2 --> P[6. Captions<br/>Gemini writes the words; frames come only from detection]
    RS --> P
    P --> M[7. Markers<br/>Jev places a ring, arrow or feet marker]
    M --> O[8. Render<br/>rule card, 0.5x replay with pauses, summary card]
    O -->|MP4| U
```

**Two rules hold everywhere:**

- **The AI never invents a frame or a citation.** Gemini may only answer with a frame number printed on the images it
  was sent, and the rule text may only cite sections that were actually retrieved. Anything else is rejected.
- **Every stage fails gently.** If the rule can't be simplified, the official text is shown. If the zoomed check
  fails, the first answers stand. If captions fail, plain labels are used. If a marker isn't confident, there is no
  marker. The fan still gets a replay.

Only the inputs are sport-specific: each sport has its own folder with its decisions, prompts, rulebook and marker
targets (`V9/sports/<sport>/`). The pipeline, the web app and the renderer are shared.

---

## The pipeline, stage by stage

| # | Stage | What happens | Code |
|---|---|---|---|
| 1 | **Normalize** | A clip already in H.264, yuv420p, constant frame rate is kept untouched; otherwise it is re-encoded **once** and then frozen. Frame numbers (0-based) depend on this clip, so it is never encoded again. | `pipeline/normalize.py` |
| 2 | **Event** | The decision chosen on the page, or one ball read from a Cricsheet file (cricket) or one event from StatsBomb / SoccerNet data (football), turned into the same sport-neutral event record. | `sports/<sport>/events.py` |
| 3 | **Rule** | The decision maps to exact sections of the official rulebook (the edition picked by match date). Gemini 3.1 Flash-Lite rewrites them for beginners as a summary, conditions and exceptions; each citation is checked against the retrieved sections. One AI call per decision ever, then cached. | `pipeline/rules.py` |
| 4 | **Find key moments** | The clip's frames are laid out as numbered contact sheets (4 × 3 frames, every 2nd frame, more on long clips). Gemini names the frame of each moment the decision needs (for LBW: release, ball pitches, ball hits pad, appeal, umpire's signal). Long clips get a second, finer pass around the first answers. Moments the logic can work out are derived, not detected (bat misses ball = stumps hit − 1 for bowled). | `pipeline/detect.py` |
| 5 | **Zoomed check** | For each moment, 7 frames around the answer are cropped around the person or object (boxed by Jev) and enlarged. Gemini keeps, moves or removes the moment. | `pipeline/verify.py` |
| 6 | **Captions** | Gemini writes a title and caption for each moment from the event, the rule and the detections. Frames only ever come from detection; any frame the model writes is ignored. | `pipeline/plan.py` |
| 7 | **Markers** | Jev boxes what each moment is about (the bowler, the pad, the referee, the server's feet). A marker is drawn only when Jev's own presence score is high enough. | `pipeline/spotlight.py` |
| 8 | **Render** | ffmpeg builds the MP4: rule card, the replay at 0.5x from 3 s before the first moment to 2 s after the last, a 3 s pause with caption and marker at each moment, a timeline with moment dots, and a summary card. | `pipeline/render.py` |

**Model order.** Each AI step has its own model list, set on the host without code changes:

| Step | Models, in order | Setting |
|---|---|---|
| Find key moments, pass 1 | Gemini 3.6 Flash → 3.5 Flash → 3.5 Flash-Lite | `DETECT_MODELS_PASS1` |
| Find key moments, pass 2 | Gemini 3.5 Flash-Lite | `DETECT_MODELS_PASS2` |
| Zoomed check | Gemini 3.5 Flash-Lite | `CHECK_MODELS` |
| Rule text, captions | Gemini 3.1 Flash-Lite → 3.5 Flash-Lite | `TEXT_CHAIN` in `config.py` |

A busy or out-of-quota model moves the step to the next one, so a run doesn't fail because one model is unavailable.

---

## Sports and decisions

| Sport | Rulebook | Decisions | Examples |
|---|---|---|---|
| Cricket | MCC Laws of Cricket (2022 and 2026 editions, picked by match date) | 24 | Bowled, LBW, run out, stumped, no ball (front foot), wide, DRS review |
| Football | IFAB Laws of the Game 2026/27 | 16 | Goal, offside, penalty, handball, second yellow, VAR check |
| Basketball | NBA Official Playing Rules 2026-27 | 21 | Traveling, goaltending, charging, blocking foul, shot clock |
| Tennis | Rules of Tennis 2026 | 14 | Service fault, foot fault, ball out, electronic line review |

Match data is optional: Cricsheet for cricket, StatsBomb or SoccerNet for football. Adding a sport means adding a
folder under `V9/sports/` with its decisions, rulebook and prompts; the rest of the system is unchanged.

---

## Repository layout

| Path | What it is |
|---|---|
| [`V9/`](V9/) | The app: web page, pipeline, sports, tests. **Setup and settings in [`V9/README.md`](V9/README.md)** |
| `V9/app.py` | Web app: login, limits, upload checks, jobs, temporary files, usage lines, keep-awake |
| `V9/pipeline/` | The eight stages above, plus `frames.py` (reads frames as needed) and `notify.py` (quota alert) |
| `V9/sports/<sport>/` | Per sport: decisions and prompts, event adapters, rulebook (original PDF + parsed sections), marker targets |
| `V9/clips/` | The 19 library clips packed with the app |
| `V9/tests/` | 418 unit tests (no real clips, no AI calls) |
| [`render.yaml`](render.yaml) | Deploys `V9/` to Render's free plan |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | The original design the build followed |
| `videos/` | Source clips used while developing |
| `tests/` | Early experiments (pixel rules, Jev, Gemini contact sheets), kept for reference |

## Run it locally

You need Python 3.12, ffmpeg, and a `GEMINI_API_KEY` in a `.env` file next to `V9/` (optionally `TYPESAFE_API_KEY`
for markers). From `V9/`:

```
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5002. Locally there is no password and no limits, and job folders are kept. Unit tests:
`pip install pytest`, then `python -m pytest tests -q`.

## Limits

- **Free-tier speed:** a run takes about 2 to 4 minutes, mostly waiting for Gemini. Busy periods add time.
- **Free quota:** Gemini 3.6 Flash allows about 20 requests a day per Google project; after that runs use the
  fallback models, with rougher timing. The quota resets at about 13:30 IST.
- **Timing:** usually within 1 to 2 frames on clear footage; tiny or hidden things (the ball, a bail behind the batter,
  a tennis ball's landing) are the weakest.
- **What the clip doesn't show, the app can't explain:** a spoken call or a decision made off camera gets the rule
  card and a plain replay.
- **No sound** in the output video.

## Future plans

**Build an annotated dataset of officials' decisions, then train a computer-vision model for the timing.**

Today a large vision model (Gemini) finds the key moments. It works, but it depends on a free daily quota, waits on
busy servers, and is weakest on small things like the ball or a bail. A model trained for this one job would be
faster, cheaper and could run without an outside service.

1. **Collect clips of decisions** across the four sports, matched to match data (Cricsheet, StatsBomb) so each clip
   already knows its decision, players and time.
2. **Annotate them:** for each clip, the frame of every key moment (release, ball pitches, ball hits pad, stumps hit,
   flag raised, umpire's signal) and boxes for the objects that matter (ball, stumps, bails, players, officials). The
   app's own runs give a head start: its Gemini answers become draft labels that annotators correct, instead of
   labelling from scratch.
3. **Train a computer-vision model:** an event-spotting model that names the frame of each moment, and an object
   detector for the ball, stumps and officials, which also places the markers.
4. **Measure it** against the hand-checked frames (how many frames off, how often a moment is missed) and put it in
   front of Gemini in the pipeline: the trained model times the moments, Gemini stays for the rule text and captions
   and as the fallback.

The result would be a faster, quota-free explainer, and a labelled dataset of officials' decisions that does not
exist publicly today.

## AI tools used

- **Gemini 3.6 Flash, 3.5 Flash, 3.5 Flash-Lite** (Google): find and check the key moments in the video.
- **Gemini 3.1 Flash-Lite** (Google): simplifies the official rules and writes the captions.
- **Jev** (TypeSafe): locates people and objects for the zoomed check and the markers.
- **Claude Code** (Anthropic): helped build, test and deploy the system.
