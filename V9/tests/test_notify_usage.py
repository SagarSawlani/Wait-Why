import datetime, json
import app as web
import usage_report
from pipeline import llm, notify

UTC = datetime.timezone.utc


def test_quota_alert_goes_once_per_model_and_quota_day(monkeypatch):
    monkeypatch.setenv("NOTIFY_URL", "https://ntfy.sh/test-topic")
    monkeypatch.setenv("NOTIFY_EMAIL", "me@example.com")
    monkeypatch.setenv("GEMINI_API_KEY", "abcdefXYZ123")
    monkeypatch.setattr(notify, "_sent", set())
    sent = []
    send = lambda url, message, headers: sent.append((url, message, headers))
    first = datetime.datetime(2026, 11, 3, 21, 0, tzinfo=UTC)            # 02:30 IST, 13:00 Pacific
    assert notify.quota_reached("gemini-3.6-flash", first, send)
    assert not notify.quota_reached("gemini-3.6-flash", first + datetime.timedelta(hours=1), send)   # same day
    assert not notify.quota_reached("gemini-3.5-flash", first, send)    # not watched
    assert notify.quota_reached("gemini-3.6-flash", first + datetime.timedelta(hours=12), send)      # next day
    import time
    time.sleep(0.2)
    url, message, headers = sent[0]
    assert url.endswith("test-topic") and headers["Email"] == "me@example.com"
    assert "02:30 IST" in message and "XYZ123" in message and "abcdef" not in message
    assert "13:30 IST" in message   # midnight Pacific in November


def test_no_alert_without_a_url(monkeypatch):
    monkeypatch.delenv("NOTIFY_URL", raising=False)
    monkeypatch.setattr(notify, "_sent", set())
    assert not notify.quota_reached("gemini-3.6-flash")


def test_a_quota_error_from_gemini_triggers_the_alert(monkeypatch):
    called = []
    monkeypatch.setattr(llm, "RETRY_WAIT", 0)
    monkeypatch.setattr(notify, "quota_reached", lambda model: called.append(model))

    def refuse(model, system, contents):
        raise RuntimeError("429 RESOURCE_EXHAUSTED. You exceeded your current quota")
    monkeypatch.setattr(llm, "_call_with_limit", refuse)
    try:
        llm.generate([("gemini-3.6-flash", 1)], "s", ["p"])
    except RuntimeError:
        pass
    assert called == ["gemini-3.6-flash"]


def test_busy_errors_do_not_alert():
    assert not notify.is_quota_error(RuntimeError("503 UNAVAILABLE. high demand"))
    assert notify.is_quota_error(RuntimeError("429 RESOURCE_EXHAUSTED"))


def test_usage_lines_are_json_the_report_can_read(capsys):
    web.log_usage("run", job="abc", visitor="v1", sport="cricket", decision="lbw", clip="library 2")
    line = capsys.readouterr().out.strip()
    assert line.startswith("USAGE ")
    record = usage_report.parse("  " + line)
    assert record["event"] == "run" and record["sport"] == "cricket" and record["at"].endswith("Z")


def test_report_counts_visitors_runs_and_outcomes():
    rows = [{"event": "page", "visitor": "a", "at": "2026-11-03T20:00:00Z"},
            {"event": "page", "visitor": "a", "at": "2026-11-03T20:01:00Z"},
            {"event": "login", "visitor": "b", "at": "2026-11-03T20:02:00Z"},
            {"event": "run", "sport": "cricket", "decision": "lbw", "clip": "library 2", "at": "2026-11-03T20:03:00Z"},
            {"event": "run", "sport": "tennis", "decision": "ball_out", "clip": "upload", "at": "2026-11-03T20:10:00Z"},
            {"event": "result", "outcome": "done", "seconds": 120, "model": "gemini-3.6-flash"},
            {"event": "result", "outcome": "failed", "seconds": 80},
            {"event": "refused", "reason": "limit"}]
    text = "\n".join(usage_report.summary(rows))
    assert "Page views:        2" in text and "Visitors:          2" in text
    assert "Runs started:      2" in text and "1 done, 1 failed" in text and "Refused (limits):  1" in text
    assert "cricket / lbw" in text and "upload" in text and "2026-11-04" in text   # 01:33 IST
