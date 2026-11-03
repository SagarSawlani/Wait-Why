"""Gemini calls with a fallback chain. Every model is tried as many times as config says, in order."""
import json, queue, threading, time
import config
from pipeline import notify

RETRY_WAIT = 6   # seconds between attempts
_client = None


def parse_json(text):
    text = (text or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON in reply: {text[:200]}")
    return json.loads(text[start:end + 1])


def image(path):
    """A JPEG file as a request part. Sending the bytes avoids the SDK decoding the picture into memory
    and encoding it again, which it does for a PIL image."""
    from google.genai import types
    with open(path, "rb") as f:
        return types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")


def _call(model, system, contents):
    global _client
    from google import genai
    from google.genai import types
    if _client is None:
        # reads GEMINI_API_KEY from the environment; the timeout here is in milliseconds
        _client = genai.Client(http_options=types.HttpOptions(timeout=config.CALL_TIMEOUT * 1000))
    resp = _client.models.generate_content(
        model=model, contents=contents,
        config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json"))
    return resp.text


def _call_with_limit(model, system, contents):
    """Gives up after CALL_TIMEOUT even if the request never returns. The call runs in a daemon
    thread, because a stuck network call cannot be cancelled, only abandoned."""
    box = queue.Queue(1)

    def work():
        try:
            box.put((_call(model, system, contents), None))
        except Exception as e:
            box.put((None, e))

    threading.Thread(target=work, daemon=True).start()
    try:
        text, error = box.get(timeout=config.CALL_TIMEOUT)
    except queue.Empty:
        raise TimeoutError(f"no reply after {config.CALL_TIMEOUT} seconds")
    if error:
        raise error
    return text


def generate(chain, system, contents, check=None):
    """Returns (data, model). check(data) raises to reject a reply, which counts as a failed attempt."""
    errors = []
    for model, tries in chain:
        for attempt in range(tries):
            try:
                data = parse_json(_call_with_limit(model, system, contents))
                if check:
                    check(data)
                return data, model
            except Exception as e:
                if notify.is_quota_error(e):
                    notify.quota_reached(model)
                errors.append(f"{model} attempt {attempt + 1}: {str(e)[:160]}")
                print("  " + errors[-1])
                time.sleep(RETRY_WAIT)
    raise RuntimeError("all models failed. " + " | ".join(errors))
