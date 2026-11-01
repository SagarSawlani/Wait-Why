# "Why this decision?" — final architecture

Everything runs offline and is saved to files. The deployed site is a static player that reads those files.
Sport-specific: event adapter, rulebook, moment spec. Generic: everything else.
Frame numbers are 0-based and are the source of truth; timestamp = frame / fps.

## 1. Input layer

### 1.1 Video
1. Cut one clip per decision from the match video, starting before the run-up and ending after the signal.
2. ffprobe: codec, pixel format, r_frame_rate, avg_frame_rate, frame count.
3. If the clip is already H.264 + yuv420p + constant frame rate, keep it as it is.
   Otherwise re-encode **once**, fixing all three in the same ffmpeg command. Keep the source fps.
4. Re-check with ffprobe, then freeze. A frozen clip is never re-encoded.

Output: `clips/<clip_id>.mp4`, `clips/<clip_id>.meta.json` (fps, frames, width, height, duration).

### 1.2 Event data
1. Structured source (Cricsheet, StatsBomb) -> deterministic adapter.
2. Unstructured source -> schema-constrained LLM extraction. Later, only for sports with no structured data.
3. Validator: schema and allowed values. A failure stops that clip; nothing is guessed.

Output: `events/<event_id>.json` (event_id, sport, event_type, subtype, outcome, status, actors[],
context{format,date,competition}, details{}, source). Never contains geometry or timestamps.

### 1.3 Rules
1. Parse the official rulebook by section, one parsed copy per edition.
2. Choose the edition from sport and match date.
3. Lookup: exact mapping (sport, event_type, subtype, format) -> section. Semantic search only on a miss.
4. LLM simplifies the retrieved text (beginner/standard/expert) with schema output.
5. Validator: schema, and the cited section must be one of the retrieved sections.
   Failure: retry once, then show the official text unsimplified.
6. Cache by (sport, event_type, subtype, edition, level). Each key costs one LLM call, ever.

Output: `rules/<cache_key>.json` (section, summary by level, conditions[], evidence_needed[]).

### 1.4 Case manifest
Joins the three inputs, because Cricsheet has no video timestamps and cannot find a clip by itself.

```json
{"clip_id": "clip", "event_id": "...", "source_match": "...", "innings": 1, "over": 12, "ball": 3}
```

Written by hand per clip for the prototype.

## 2. Moment detection

Input: frozen clip + event + moment spec.

Moment spec: `moments/<sport>_<event_type>.json` lists the moments to find, each with a plain definition.
Example: cricket bowled -> release, ball_at_batter, stumps_hit, stumps_disturbed_visible, umpire_signal.
Football offside -> pass_played, flag_raised, referee_signal. Adding a sport adds a file, not code.
Draft these with an LLM from evidence_needed, then save and review them.

Steps:
1. Contact sheets (every 2nd frame, numbered, all frames including after cuts).
2. Gemini 3.8 Flash, 3 runs, median per moment.
3. Validator: frame printed on a cell, moments in time order, confidence recorded.
4. Moments that event logic gives are derived, not detected (bat miss = stumps_hit - 1 for bowled).

Fallback (later): gemini-3.8-flash fails twice -> first fallback once -> second fallback once. Never mix
models inside one median. Record the model used in the result.

Output: `detections/<clip_id>.json` (moment, frame, timestamp, confidence, evidence, model).

## 3. Planner

Input: event + rule explanation + detections. LLM writes the captions and organises the steps.
Frames come only from detections; the validator rejects a plan with any other frame.
A low-confidence moment keeps its caption and loses its highlight.

Output: `plans/<clip_id>.json` (clip, fps, rule summary, steps[{frame, title, caption, highlight|null}]).

## 4. Player

Static HTML5 page reading one plan per clip: "Why this decision?" button -> rule summary -> replay at 0.5x
-> pause at each step with its caption -> timeline with moment markers. requestVideoFrameCallback for sync.
Label the analysis as precomputed.

## 5. Later

- Jev spotlight boxes: fills `highlight` in the plan. Plan and player already allow null, so nothing else changes.
- Fallback chain, LLM event extraction, second sport.
