# Project context: "Why this decision?" — AI umpire decision explainer

Handoff notes from a long planning and experimentation chat. Read this before changing anything.

## 1. The assignment

- Brief: "Build one AI-powered artifact that solves a real problem fans face during a live sports match."
  Evaluators care more about the problem, the fan understanding and the solution than about polish.
- Submission: (1) a link to the working artifact, (2) a note of max 200 words covering: what fan problem,
  how the solution helps, which AI tools were used.
- Plan agreed with the evaluator side (email drafted): submit a recorded walkthrough of the full system
  running locally, plus a deployed link built from precomputed/static outputs, plus a README saying
  clearly what is live and what is precomputed.
- Constraint: **free tools only** (free API tiers, free Kaggle/Colab GPUs, free hosting).

## 2. The product idea

Fans see an umpire's decision but not the reason. When a decision happens, a **"Why this decision?"**
button appears. Pressing it:
1. shows a short plain-language explanation of the rule (e.g. what "bowled" means),
2. replays the delivery at **0.5x**, auto-pausing at each key moment (ball released, batter misses,
   stumps hit, bail flies), with synced caption text and soft visual highlights (spotlight circles).

Cricket first (Test-match broadcast clips from YouTube, behind-the-bowler camera), but the system must
be designed to work for **multiple sports**: only the inputs (event data, rulebook, detection prompts)
are sport-specific; the planner and the player are generic.

## 3. Architecture (agreed design)

**`ARCHITECTURE.md` is the final version and wins over this section where they differ.** Gemini 3.8 Flash is
the main timing LLM. Jev is postponed until spotlight boxes.

**Stage 1: inputs**
- 1.1 Video: one frozen clip per decision, H.264, 8-bit yuv420p, **constant frame rate** (keep the
  source fps, check with ffprobe that r_frame_rate == avg_frame_rate). No separate playback proxy
  (prototype). Once a clip is final it is never re-encoded, or all frame numbers shift.
  **Frame numbers are 0-based everywhere.**
- 1.2 Match event data: a normalized, sport-agnostic event JSON (event_id, sport, event_type, subtype,
  outcome, status, actors[], context{format,date,competition}, details{}, source). Source for cricket:
  Cricsheet (deterministic adapter code, not an LLM). Other sports: StatsBomb (football), etc.
  Event data is the trigger and source of names; it never contains geometry.
- 1.3 Rules: official rulebook (MCC Laws of Cricket 2017 Code 3rd Ed. 2022 for current clips; new
  edition takes effect Oct 2026) -> parse by section -> **deterministic lookup** by
  (sport, event_type, subtype, format, date) with semantic search only as fallback -> LLM simplifies
  the retrieved text (beginner/standard/expert) with schema output incl. conditions + evidence needed
  -> validate -> **cache**. No hand-written rule cards, no fine-tuning (fine-tuning = later, tone only).

**Stage 2: moment detection** (the part being tested now, see section 4)

**Planner:** LLM turns event + cached rule explanation + detected key frames into a JSON plan:
ordered steps, each with frame, caption text, highlight (box/target), style. AI narrates and organizes;
frames/positions come from detection, never invented by the LLM. Low-confidence evidence -> overlay
skipped, text still shown (graceful degradation).

**Player (not built yet):** HTML5 video at playbackRate 0.5, requestVideoFrameCallback for frame-accurate
sync, auto-pause at each key moment, caption, soft spotlight (padded circle, not tight rectangles),
timeline bar with moment markers, "Why this decision?" button. Reads one plan file per clip.

**Deployment:** precompute everything offline; deploy only the static player + clips + plan JSONs
(e.g. Vercel/Netlify). Label in the UI and README that analysis is precomputed. Keep API keys server-side
only if any live call is added.

## 4. Experiments so far and what they showed

Main test clip: `C:\dream11_project\videos\clip.mp4` (1080p, 25 fps, ~50 frames, Test match, bowled).
**Ground truth (user verified): ball hits stumps at frame 17 (about to hit at 16, clearly hit at 18);
bail first visible in the air at frame 21 (batter hides stumps at impact). Camera cut / zoom jump ~frame 24.**
Release and ball-at-batter truth frames were never written down (release is ~4-6 by all methods).

| Approach | Result |
|---|---|
| Hand-written pixel heuristics (motion in stump ROI, pose "wrist above nose", COCO YOLO "sports ball") | Failed: camera zoom/pan breaks fixed ROI, pose picked wrong people, ball detections were noise |
| SIFT homography camera compensation | Partial: box stays on stumps through the zoom but distorts; broad motion hump, not a hit spike |
| Fine-tuned YOLO (Roboflow datasets exist for stumps/ball/crease/players) | Considered; no dataset has "stumps broken". Parked |
| FPVShotDetection dataset (KumailAbb, IEEE Access 2025) | Relevant view, but user decided not useful; no license file |
| **Gemini on numbered contact sheets (every 2nd frame)** | **Best.** Stumps hit 16/18 (1 frame from truth), release 6 stable, found cut at 24 once. One of 3 repeat runs drifted ~10 frames late, caused by footage after the camera cut -> fix: trim clip at first cut |
| Jev (TypeSafe) bounding boxes | Good for people (batter, bowler), rough for stumps, bad for arm/ball/bail (false bail box) |
| Jev choice question on a grid (frame numbers as options) | Failed, even with 640px cells: said "none" for stumps, picked first cell for absent release |
| Jev per-frame yes/no scan (full frame) | Release: clean step at frame 5. Ball past bat: vague ramp. Stumps: never flipped |
| Jev per-frame on crops around actor | Stumps: real step at 20-21 (= bail visible, not the hit). Release got worse. Bat: noise |

**Decisions taken:**
- **Gemini is the timing layer** (contact sheets, every 2nd frame, median of runs). All frames now go in,
  including after camera cuts, so post-cut moments are kept; this risks the late drift seen in repeat runs.
- Jev is only for spotlight boxes on large objects (people, roughly stumps), optionally to confirm release.
- "Bat misses ball" can be **derived** for bowled: stumps_hit - 1 (ball covers ~1.5 m/frame at 25 fps).
- Don't detect what event logic already gives. Don't depend on a perfect ball track; ball path is a bonus.
- Frame-perfect accuracy is NOT required (0.5x replay with pauses); ~1-2 frames is fine.

## 5. Scripts in `C:\dream11_project\tests` (Windows, PowerShell, venv `.venv`)

- `gemini_keyframes.py` — **current main script.** For each video (file(s) or folder): extracts all
  frames to `<out>/<clip>/frames/00000.jpg`, detects hard cuts (HSV histogram correlation, `--cut_thr`
  default 0.6), keeps a segment (`--segment first|longest|none`, default none = all frames), builds contact sheets
  (`--step 2`, `--cols 4`, `--per_sheet 12`, `--cell_w 480`), calls the model with a system prompt,
  `--runs` (default 1) with median + time-order check, writes `result.json`, `gemini_raw.json`,
  `keyframes.jpg` (strip of chosen frames) and `<out>/summary.csv`. Optional `--manifest manifest.json`
  with per-clip `event` hint and `truth` frames. Moments: release, ball_at_batter, bat_contact_or_miss
  (+ outcome), stumps_hit, stumps_disturbed_visible, umpire_signal, plus camera_cuts and decision_guess.
  (Bounce was removed: model could not find it.)
- `list_models.py` — lists models the GEMINI_API_KEY can call (`python list_models.py gemma`).
- `gemini_repeat.py` — runs the Gemini sheet prompt N times to measure stability (older; superseded).
- `jev_boxes.py`, `jev_scan.py`, `jev_grid.py`, `jev_crop_scan.py` — Jev experiments (see section 4).
  Jev API notes: POST https://api.typesafe.ai/v1/systemone, header `TypeSafe-Danger-Zone-Images: true`,
  images as `assets` (base64, format jpg) referenced in `state`; models `jev-1.14.0`, `jev-preview`.
  noul answer = `answers[name]["noul"]` (probability). choice `criteria` must be a **dict**
  option->description. Box returns top/bottom/left/right fractions. **Max image size ~1280 px**
  (1600 rejected). Box always returns a box, so pair with a presence question.
- Older: `stage2_test1.py`, `stage2_camera.py`, `preview_roi.py`, `make_sheets.py`, `ask_gemini.py`.

Env vars: `GEMINI_API_KEY`, `TYPESAFE_API_KEY` (set per terminal: `$env:GEMINI_API_KEY="..."`).

## 6. Models and free limits (as of Nov 2026, check AI Studio rate-limit page)

Available to the user's key include gemini-3.8-flash, 3.7/3.6/3.5-flash, 3.1-flash-lite, 2.5-flash/pro,
gemma-4-31b-it, gemma-4-26b-a4b-it. Reported free limits: Gemini 3.x Flash ~5 RPM / **20 requests/day**;
3.1 Flash-Lite ~500/day; **Gemma 4 ~15 RPM / 1,500/day**. Limits are per Google Cloud project; daily
reset at midnight Pacific (13:30 IST after Nov 1). Free-tier content may be used by Google.
Other free options considered: Qwen3-VL (small size, Kaggle/Colab), TimeLens-8B (temporal grounding).

## 7. Where things stand right now

- **`V6/` is the main version; see `V6/README.md`. New work goes there.** It runs on port 5001. V1 to V5 are no longer in the working folder; their committed code is in git.
- **`V2/` is the multi-sport build: `sports/<sport>/` holds all sport-specific code.** V1 stays as the cricket demo.
- **`V1/` is the demo build; see `V1/README.md`.** Flask page + pipeline, 24 umpire decisions in `V1/decisions.py`.
  The user supplies and tests all real clips. Do not process videos in `videos/` or run end-to-end tests.
  Older notes below are history.

- **Gemma dropped.** `gemma_probe.py` on gemma-4-26b-a4b-it: text worked, but every image request failed
  with `400 INVALID_ARGUMENT` (any size, 1-3 images, either order, inline or Files API), so it cannot read
  contact sheets through this API with this key. gemma-4-31b-it failed `gemini_keyframes.py` the same way,
  and returned `500 INTERNAL` on plain text.
- **TimeLens-8B / Qwen3-VL parked.** The laptop has no dedicated GPU (Iris Xe, 16 GB RAM), so they would
  need Kaggle, and they are unlikely to beat Gemini on exact frames.
- Next steps:
  1. Run `gemini_keyframes.py` on several clips (bowled + a wide + one more type) and check
     `keyframes.jpg` / `summary.csv`.
  2. Define the plan JSON format (moments + captions + highlight targets/boxes).
  3. Build the player page (0.5x, pauses, captions, spotlights, timeline, button).
  4. Rule explanation pipeline (rulebook retrieval + LLM simplification, cached).
  5. README with live-vs-precomputed table, demo recording, 200-word note.

## 8. Working preferences

- The user runs code himself and pastes output back; explain what a script does and how to judge results.
- User wants automated, dynamic, multi-sport approaches, not per-clip manual work or brittle hand rules.
- Free tools only. Keep explanations concrete; be honest about what failed.
