"""Sends a phone (and optionally e-mail) alert through ntfy.sh when a watched Gemini model runs out of quota.

Setup: install the free ntfy app, subscribe to a long random topic, and set on the host
  NOTIFY_URL=https://ntfy.sh/<that topic>      (required; no alerts without it)
  NOTIFY_EMAIL=you@example.com                (optional; ntfy also e-mails the alert)
  NOTIFY_MODELS=gemini-3.6-flash              (optional; comma-separated models to watch)
One alert per model per quota day: the free quota resets at midnight Pacific time. Nothing secret is sent."""
import datetime, os, threading
from zoneinfo import ZoneInfo
import requests

PACIFIC, IST = ZoneInfo("America/Los_Angeles"), ZoneInfo("Asia/Kolkata")
_sent, _lock = set(), threading.Lock()


def watched():
    return {m.strip() for m in os.environ.get("NOTIFY_MODELS", "gemini-3.6-flash").split(",") if m.strip()}


def is_quota_error(error):
    text = str(error)
    return "429" in text and "RESOURCE_EXHAUSTED" in text


def next_reset(now=None):
    """When the free quota comes back: the next midnight in Pacific time, as a time in IST."""
    now = (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(PACIFIC)
    midnight = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(IST)


def quota_reached(model, now=None, send=None):
    """Called on every quota error. Alerts once per model and quota day; returns True if an alert went out."""
    url = os.environ.get("NOTIFY_URL", "").strip()
    if not url or model not in watched():
        return False
    now = now or datetime.datetime.now(datetime.timezone.utc)
    day = (model, now.astimezone(PACIFIC).date())
    with _lock:
        if day in _sent:
            return False
        _sent.add(day)
    key = os.environ.get("GEMINI_API_KEY", "")
    message = (f"{model} reached its free quota at {now.astimezone(IST):%H:%M} IST"
               f"{f' (key ending {key[-6:]})' if key else ''}. Runs now use the next model in the order. "
               f"The quota comes back at about {next_reset(now):%H:%M} IST.")
    headers = {"Title": "Wait, Why?: Gemini quota reached", "Tags": "warning"}
    if os.environ.get("NOTIFY_EMAIL", "").strip():
        headers["Email"] = os.environ["NOTIFY_EMAIL"].strip()
    # in the background, so a slow alert never delays the run
    threading.Thread(target=send or _post, args=(url, message, headers), daemon=True).start()
    return True


def _post(url, message, headers):
    try:
        requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=15)
        print(f"  alert sent: {message}")
    except requests.RequestException as e:
        print(f"  alert failed: {str(e)[:120]}")
