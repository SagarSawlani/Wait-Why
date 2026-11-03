# V7 overnight results (3 November 2026)

## What changed from V6

| Change | Why |
|---|---|
| Detection tries `gemini-3.6-flash` first, then 3.5 Flash, 3.8, 3.5 Flash-Lite | 3.6 gave the best frames; 3.8 kept timing out and wasted a minute per call |
| Two-pass detection (`pipeline/detect.py`) | Long clips were sampled up to 29 frames apart. A second, finer pass now re-reads the stretch around the first answers, and is kept only if it finds at least as many moments |
| Tennis service fault prompt | It locked onto the start of the clip instead of the real serve |
| Cricket caption prompt | Titles no longer say "confirmed" or judge the call |

376 tests pass.

## Scored clips (truth checked by eye; within 5 frames counts)

| Run | Model that answered | Score |
|---|---|---|
| V6-style, one pass | 3.6 Flash | 11 / 14 |
| One pass, Raducanu fix | 3.6 Flash | Raducanu 2 / 2 (serve 61, landing 67) |
| One pass | 3.5 Flash-Lite | 12 / 14 |
| Two-pass, Burnley | 3.5 Flash-Lite | 3 / 3 (pass 293, attacker 312, flag 337) |

Same bowled clip on V1 to V5 with Flash-Lite: stumps 25 to 28 every time (truth 17). With 3.6: 16.
The old versions were not the problem; the model was.

## Frontend clips (17 of 19, two-pass, all on 3.5 Flash-Lite because 3.6 and 3.5 Flash were out of quota)

| Clip | Verdict |
|---|---|
| 1 Bowled (World Cup 2019) | Good: release, ball past bat, stumps 255 in the super slow-motion |
| 2 LBW (Tendulkar) | Partly: pitch 57 and pad 58 are one frame apart |
| 3 Run out | Good |
| 4 Front-foot no ball | Good |
| 5 Offside (Chelsea v Man Utd) | Partly: "flag" is a player raising his arm |
| 6 Offside (England v Scotland) | Partly: right team, pass unsure |
| 7 Red card | Good |
| 8 Second yellow | Partly: contact only, no card moment |
| 9 Penalty | Partly: contact only, no signal |
| 10 Traveling | Good, plausible |
| 11 Goaltending | Good, plausible |
| 13 Charging | Good |
| 14 Service fault | Close: landing about 4 frames late |
| 15 Ball out | Partly: shot right, landing early (111; 3.6 gets 118) |
| 16 Foot fault | Good |
| 17 Electronic review | Good |
| 19 Ball hits player | Partly: the hit itself was rejected |
| 12 Shot clock (Kobe tribute), 18 Code violation (spoken call) | No moments; rule card and plain replay only. These clips do not show what the decision needs |

Times were 30 to 110 seconds per clip on Flash-Lite. Two runs were cut by the PC losing power; those times are excluded.

## Not done

- 3.6 and 3.5 Flash were out of quota on all five keys after the first scored run, so the frontend clips have not been run on 3.6. Re-running clips 2, 5, 6, 15 and 19 on 3.6 after the daily reset (about 13:30 IST) is the next step.
- Other providers (Mistral, OpenRouter, NVIDIA, Cloudflare) were tested in another session and were far off the true frames, so they were not used.
- Captions still state a few things the frame cannot prove, such as "the batter is away from safety".

## One clip, three models (bowled, V7 at 480 px; truth release 4-6, stumps 17, bail 21)

| Model | Release | Stumps | Bails | Time |
|---|---|---|---|---|
| 3.6 Flash | 6 | 14 | 16 | 78.3 s (zoomed check overloaded, first guesses kept) |
| 3.5 Flash | 6 | 16 | 18 | 54.1 s (needed 4 tries to get past overload) |
| 3.5 Flash-Lite | 9 | 27 | 28 | 30.8 s |

3.8 Flash moved to the end of the order, since it rarely answers.
Full resolution to Gemini scored better on small-object moments in a test, but doubled run time and is not built in yet.
