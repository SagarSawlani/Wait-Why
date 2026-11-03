"""Runs all the stages for one job and saves each result in the job folder.
params: sport, decision, level, date, format, notes, match_path, innings, over_ball, start, end"""
import ctypes, ctypes.util, gc, json, os, time
import config
import sports
from pipeline import detect, normalize, plan, render, rules, spotlight, verify

STAGES = ["Normalize video", "Read event", "Explain the rule", "Find key moments", "Check moments on zoomed crops", "Write captions", "Mark the action", "Render video"]


def save(job_dir, name, data):
    with open(os.path.join(job_dir, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def read_event(p):
    sport = p.get("sport", "cricket")
    events = sports.events(sport)
    if p.get("match_path"):
        match = events.load_match(p["match_path"])
        return events.from_source(match, p, p.get("decision") or None)
    if p.get("decision") not in sports.decisions(sport).DECISIONS:
        raise ValueError("choose a decision, or add a Cricsheet file with the innings and over.ball")
    return events.from_form(p["decision"], p.get("date", ""), p.get("format", ""), p.get("notes", ""))


def memory_mb():
    """This process's resident memory, plus its child processes (ffmpeg), in MB. Linux only, else 0."""
    total, pids = 0, [str(os.getpid())]
    try:
        with open(f"/proc/{os.getpid()}/task/{os.getpid()}/children") as f:
            pids += f.read().split()
    except OSError:
        return 0
    for pid in pids:
        try:
            with open(f"/proc/{pid}/status") as f:
                total += next((int(l.split()[1]) for l in f if l.startswith("VmRSS")), 0)
        except OSError:
            pass
    return total // 1024


def release_memory(stage):
    """Hands freed memory back to the system between stages. Python's allocator keeps it otherwise, and on a
    512 MB host what one stage left behind is what the next stage runs out of. Logs the memory in use."""
    if not config.LOW_MEMORY:
        return
    gc.collect()
    libc = ctypes.util.find_library("c")
    if libc:
        try:
            ctypes.CDLL(libc).malloc_trim(0)
        except (OSError, AttributeError):
            pass
    print(f"  memory before {stage}: {memory_mb()} MB")


def run_job(job_dir, params, progress=lambda stage: None):
    """progress(i) is called as stage i starts. Returns the path of the output video.
    Ends with one log line giving each stage's time and the total, whether the run worked or failed."""
    step, times = progress, []

    def progress(i):
        times.append((STAGES[i], time.monotonic()))
        release_memory(STAGES[i])
        step(i)

    start, outcome = time.monotonic(), "failed"
    try:
        out = stages(job_dir, params, progress)
        outcome = "done"
        return out
    finally:
        ends = [t for _, t in times[1:]] + [time.monotonic()]
        parts = ", ".join(f"{name} {end - began:.0f} s" for (name, began), end in zip(times, ends))
        print(f"  job {outcome} in {time.monotonic() - start:.0f} s: {parts}")


def stages(job_dir, params, progress):
    source = os.path.join(job_dir, "input.mp4")

    progress(0)
    meta = normalize.normalize(source, job_dir, params.get("start"), params.get("end"))

    progress(1)
    event = read_event(params)
    if params.get("notes"):
        event["details"]["notes"] = params["notes"]
    save(job_dir, "event.json", event)
    decision = event["subtype"]

    progress(2)
    date = params.get("date") or event["context"].get("date", "")
    sport = event["sport"]
    rule = rules.explain(decision, params.get("level", "beginner"), rules.edition_for(date, sport), sport)
    save(job_dir, "rule.json", rule)

    progress(3)
    found = detect.detect(os.path.join(job_dir, "clip.mp4"), decision, event, job_dir, meta["fps"])

    progress(4)
    found = verify.verify(os.path.join(job_dir, "clip.mp4"), decision, event, found, job_dir, meta["fps"])

    progress(5)
    replay = plan.build(decision, event, rule, found, meta["fps"])
    progress(6)
    replay = spotlight.mark(os.path.join(job_dir, "clip.mp4"), replay, sport, job_dir)
    save(job_dir, "plan.json", replay)

    progress(7)
    return render.render(os.path.join(job_dir, "clip.mp4"), replay, meta, os.path.join(job_dir, "output.mp4"))
