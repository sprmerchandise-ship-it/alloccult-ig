#!/usr/bin/env python3
"""
One place every script talks to the language model.

Two providers; which one runs depends on the repo secret that is set
(or force one with the LLM_PROVIDER repo variable: "gemini" or "anthropic"):

  GEMINI_API_KEY     Google Gemini API, free tier (key from aistudio.google.com).
                     Used when set — it costs nothing. Picks the newest Flash
                     model the key can use; if its daily free quota runs out,
                     the request is finished on Flash-Lite.
  ANTHROPIC_API_KEY  Anthropic API (paid, per token).

(GitHub Models, used before, was retired by GitHub on 30 July 2026: every
request now gets a bare "OK" back.)

  ask_json(system, content, schema)  -> dict  (content: str or a list of blocks)
  ask_text(system, prompt)           -> str

Content blocks use the shape the scripts already build:
  {"type": "text", "text": ...}
  {"type": "image", "source": {"type": "base64", "media_type": ..., "data": ...}}

Free-tier limits shape the rest of the repo: requests are kept small (page
text capped at SOURCE_CHARS, low-detail images, 2 review rounds). Override
the models with the LLM_MODEL / LLM_FAST_MODEL repo variables
(Settings → Secrets and variables → Variables).
"""
import json, os, time, urllib.error, urllib.request

DEFAULTS = {   # (writing + vision reviews, image picks and other small calls)
    # Gemini: None = ask Google for the newest Flash / Flash-Lite this key can
    # use (Google closes older models to new keys, e.g. gemini-2.5-flash).
    "gemini": (None, None),
    "anthropic": ("claude-opus-5-5", "claude-haiku-5-5"),
}
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
GEMINI_ENDPOINT = GEMINI_BASE + "/chat/completions"
GEMINI_FALLBACK = ("gemini-3.8-flash", "gemini-3.8-flash-lite")   # if the model list can't be read
MAX_OUTPUT = 4000
SOURCE_CHARS = 12000          # archive page text sent with a prompt (~3,000 tokens)


def provider():
    p = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if p in DEFAULTS:
        return p
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


def available():
    return provider() is not None


def _model(fast):
    p = provider()
    if not p:
        raise RuntimeError("No AI provider: add a GEMINI_API_KEY (free) or ANTHROPIC_API_KEY "
                           "repo secret (Settings → Secrets and variables → Actions).")
    env = os.environ.get("LLM_FAST_MODEL" if fast else "LLM_MODEL")
    if env:
        return env
    if p == "gemini":
        return _gemini_pick(fast)
    return DEFAULTS[p][1 if fast else 0]


_GEMINI_MODELS = None


def _gemini_models():
    """Model ids this key can use, from Google's model list (cached)."""
    global _GEMINI_MODELS
    if _GEMINI_MODELS is None:
        req = urllib.request.Request(GEMINI_BASE + "/models",
                                     headers={"Authorization": f"Bearer {os.environ['GEMINI_API_KEY']}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode())
            _GEMINI_MODELS = [m["id"].removeprefix("models/") for m in data.get("data", [])]
        except (urllib.error.URLError, ValueError, KeyError) as e:
            print(f"  (couldn't list Gemini models: {e})")
            _GEMINI_MODELS = []
    return _GEMINI_MODELS


def _gemini_pick(fast):
    """Newest stable 'gemini-<version>-flash' (or '-flash-lite' when fast)."""
    import re
    want = re.compile(r"^gemini-(\d+(?:\.\d+)?)-flash" + ("-lite" if fast else "") + "$")
    found = [(float(m.group(1)), mid) for mid in _gemini_models() if (m := want.match(mid))]
    if found:
        return max(found)[1]
    return GEMINI_FALLBACK[1 if fast else 0]


MODEL = os.environ.get("LLM_MODEL") or None       # kept for callers that pass llm.MODEL
FAST_MODEL = "fast"                               # sentinel: _chat picks the provider's fast model


# ---------------------------------------------------------------- Gemini (OpenAI-compatible)

def _openai_blocks(content):
    if isinstance(content, str):
        return content
    out = []
    for b in content:
        if b["type"] == "image":
            src = b["source"]
            out.append({"type": "image_url", "image_url": {
                "url": f"data:{src['media_type']};base64,{src['data']}", "detail": "low"}})
        else:
            out.append({"type": "text", "text": b["text"]})
    return out


def _gemini_post(body):
    for attempt in range(6):
        req = urllib.request.Request(
            GEMINI_ENDPOINT, data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {os.environ['GEMINI_API_KEY']}",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                raw = r.read().decode(errors="replace")
            try:
                return json.loads(raw)
            except ValueError:
                raise RuntimeError(f"Gemini sent non-JSON (HTTP {r.status}): {raw[:300]!r}") from None
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            wait = int(e.headers.get("Retry-After") or 0) or 20 * (attempt + 1)
            # Per-minute limits clear quickly; a daily limit says to wait hours.
            if e.code == 400 and "reasoning" in detail.lower() and body.pop("reasoning_effort", None):
                print("  (model doesn't take reasoning_effort; retrying without it)")
                continue
            if e.code == 429 and wait <= 120 and attempt < 5:
                print(f"  (rate limited; waiting {wait}s)")
                time.sleep(wait)
                continue
            if e.code == 429:
                raise QuotaExceeded(f"Gemini daily limit reached for {body['model']}: {detail}") from None
            if e.code >= 500 and attempt < 3:
                time.sleep(10 * (attempt + 1))
                continue
            raise RuntimeError(f"Gemini error {e.code}: {detail}") from None
        except (TimeoutError, urllib.error.URLError) as e:
            if attempt < 2:                       # a slow or dropped answer: ask again
                print(f"  (no answer from Gemini: {e}; retrying)")
                time.sleep(15)
                continue
            raise RuntimeError(f"Gemini did not answer: {e}") from None
    raise RuntimeError("Gemini: still rate limited after retries")


class QuotaExceeded(RuntimeError):
    pass


def _gemini_chat(system, content, model, max_tokens, schema):
    # Thinking tokens count against max_tokens on Gemini's thinking models, so
    # leave room, and keep thinking light: these are writing tasks, not puzzles.
    body = {"model": model, "max_tokens": max(max_tokens, 16000),
            "reasoning_effort": os.environ.get("LLM_REASONING") or "low",
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": _openai_blocks(content)}]}
    if schema:
        body["response_format"] = {"type": "json_schema", "json_schema": {
            "name": "answer", "strict": True, "schema": schema}}
    try:
        choice = _gemini_post(body)["choices"][0]
    except QuotaExceeded as e:
        lite = _model(True)
        if model == lite:
            raise
        # The strong model's free daily quota is small; finish on Flash-Lite.
        print(f"  ({e.args[0][:80]}… — using {lite} instead)")
        body["model"] = lite
        choice = _gemini_post(body)["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError("The model's answer was cut off (max_tokens)")
    if choice.get("finish_reason") == "content_filter":
        raise RuntimeError("The model declined (content filter)")
    return (choice["message"].get("content") or "").strip()


# ---------------------------------------------------------------- Anthropic

_client = None


def _anthropic_chat(system, content, model, max_tokens, schema):
    global _client
    import anthropic
    if _client is None:
        _client = anthropic.Anthropic()
    kwargs = {}
    if schema:
        kwargs["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
    msg = _client.messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": content}], **kwargs)
    if msg.stop_reason == "refusal":
        raise RuntimeError("The model declined (refusal)")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("The model's answer was cut off (max_tokens)")
    return "".join(b.text for b in msg.content if b.type == "text").strip()


# ---------------------------------------------------------------- public

def _chat(system, content, model, max_tokens, schema=None):
    fast = model == FAST_MODEL
    model = _model(fast) if (fast or not model) else model
    if provider() == "anthropic":
        return _anthropic_chat(system, content, model, max(max_tokens, 16000), schema)
    return _gemini_chat(system, content, model, max_tokens, schema)


def _parse(raw):
    raw = raw.replace("```json", "").replace("```", "")
    return json.loads(raw[raw.find("{"):raw.rfind("}") + 1])


def ask_json(system, content, schema=None, model=None, max_tokens=MAX_OUTPUT):
    """A JSON object back. With a schema the reply is held to it (structured
    outputs); if the model rejects that, the schema goes in the prompt."""
    if schema:
        try:
            return _parse(_chat(system, content, model, max_tokens, schema))
        except RuntimeError as e:
            if "error 400" not in str(e):
                raise
        note = "\n\nReply with one JSON object matching this schema:\n" + json.dumps(schema)
        content = content + note if isinstance(content, str) else \
            content + [{"type": "text", "text": note}]
    else:
        note = "\n\nReply with one JSON object only."
        content = content + note if isinstance(content, str) else \
            content + [{"type": "text", "text": note}]
    return _parse(_chat(system, content, model, max_tokens))


def ask_text(system, prompt, model=None, max_tokens=MAX_OUTPUT):
    return _chat(system, prompt, model, max_tokens)
