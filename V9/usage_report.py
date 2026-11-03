"""How much the online app was used, from the USAGE lines it writes to Render's log.
Run: python usage_report.py [days]   (default 7; Render keeps logs for a limited time on the free plan)
Needs RENDER_API_KEY in the environment. Prints totals; nothing is changed on Render."""
import collections, datetime, json, os, statistics, sys
import requests

SERVICE = os.environ.get("RENDER_SERVICE_ID", "srv-dbl0ol61egvs7398ejlg")
OWNER = os.environ.get("RENDER_OWNER_ID", "tea-dbl08nui0phs73bff79g")
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def fetch(days):
    """Every USAGE record in the last `days` days, oldest first."""
    key = os.environ.get("RENDER_API_KEY")
    if not key:
        raise SystemExit("set RENDER_API_KEY first")
    end = datetime.datetime.now(datetime.timezone.utc)
    start = end - datetime.timedelta(days=days)
    records, seen = [], set()
    while True:
        res = requests.get("https://api.render.com/v1/logs", timeout=30,
                           headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
                           params={"ownerId": OWNER, "resource": SERVICE, "type": "app", "text": "USAGE",
                                   "limit": 100, "startTime": start.isoformat(), "endTime": end.isoformat()})
        res.raise_for_status()
        page = res.json()
        for line in page.get("logs", []):
            if line.get("id") in seen:
                continue
            seen.add(line.get("id"))
            record = parse(line.get("message", ""))
            if record:
                records.append(record)
        if not page.get("hasMore"):
            break
        end = datetime.datetime.fromisoformat(page["nextEndTime"].replace("Z", "+00:00"))
    return sorted(records, key=lambda r: r.get("at", ""))


def parse(message):
    text = message.strip()
    if not text.startswith("USAGE "):
        return None
    try:
        return json.loads(text[len("USAGE "):])
    except ValueError:
        return None


def summary(records):
    """The report as a list of lines."""
    by = collections.defaultdict(list)
    for r in records:
        by[r.get("event")].append(r)
    runs, results = by["run"], by["result"]
    done = [r for r in results if r.get("outcome") == "done"]
    times = [r["seconds"] for r in done if isinstance(r.get("seconds"), (int, float))]
    lines = [f"Page views:        {len(by['page'])}",
             f"Visitors:          {len({r.get('visitor') for r in by['page'] + by['login'] if r.get('visitor')})}",
             f"Logins:            {len(by['login'])}",
             f"Runs started:      {len(runs)}",
             f"Runs finished:     {len(done)} done, {len(results) - len(done)} failed",
             f"Refused (limits):  {len(by['refused'])}"]
    if times:
        lines.append(f"Run time (done):   median {statistics.median(times):.0f} s, fastest {min(times)} s, slowest {max(times)} s")

    def table(title, counter):
        if counter:
            lines.append("")
            lines.append(title)
            lines.extend(f"  {count:4d}  {name}" for name, count in counter.most_common())

    table("Runs by sport and decision", collections.Counter(f"{r.get('sport')} / {r.get('decision')}" for r in runs))
    table("Clip source", collections.Counter("library clip" if str(r.get("clip", "")).startswith("library") else "upload"
                                             for r in runs))
    table("Model behind the final moments", collections.Counter(r["model"] for r in results if r.get("model")))
    table("Runs per day (IST)", collections.Counter(day_ist(r.get("at", "")) for r in runs))
    return lines


def day_ist(stamp):
    try:
        return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(IST).strftime("%Y-%m-%d")
    except ValueError:
        return "unknown"


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    records = fetch(days)
    print(f"Usage in the last {days} days ({len(records)} records)\n")
    print("\n".join(summary(records)))
