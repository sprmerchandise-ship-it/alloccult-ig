#!/usr/bin/env python3
"""
One place every script talks to the language model: GitHub Models (free).

Runs inside GitHub Actions on the built-in GITHUB_TOKEN — the workflow needs
`permissions: models: read`. Locally, export GITHUB_TOKEN=<a PAT with the
"Models" permission>.

  ask_json(system, content, schema)  -> dict  (content: str or a list of blocks)
  ask_text(system, prompt)           -> str

Content blocks use the shape the scripts already build:
  {"type": "text", "text": ...}
  {"type": "image", "source": {"type": "base64", "media_type": ..., "data": ...}}

Free-tier limits shape the rest of the repo: about 8,000 input / 4,000 output
tokens per request, ~50 requests a day on the strong models and ~150 on the
small ones, ~10–15 a minute. Images go in low detail (~85 tokens each) and
page text is capped at SOURCE_CHARS. Override the models with the LLM_MODEL /
LLM_FAST_MODEL repo variables (Settings → Secrets and variables → Variables).
"""
import json, os, time, urllib.error, urllib.request

ENDPOINT = "https://models.github.ai/inference/chat/completions"
MODEL = os.environ.get("LLM_MODEL") or "openai/gpt-4.1"              # writing + vision reviews
FAST_MODEL = os.environ.get("LLM_FAST_MODEL") or "openai/gpt-4.1-mini"  # image picks, captions
MAX_OUTPUT = 4000
SOURCE_CHARS = 12000          # archive page text sent with a prompt (~3,000 tokens)


def available():
    return bool(os.environ.get("GITHUB_TOKEN"))


def _blocks(content):
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


def _post(body):
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                 "Content-Type": "application/json",
                 "Accept": "application/vnd.github+json",       # as GitHub's docs send it
                 "X-GitHub-Api-Version": "2022-11-28"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                raw = r.read().decode(errors="replace")
                try:
                    return json.loads(raw)
                except ValueError:
                    if attempt < 2:                       # an empty reply now and then
                        print(f"  (empty/non-JSON reply, HTTP {r.status}; retrying)")
                        time.sleep(10)
                        continue
                    raise RuntimeError(
                        f"GitHub Models sent non-JSON (HTTP {r.status}, "
                        f"{r.headers.get('Content-Type')}): {raw[:300]!r}") from None
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            wait = int(e.headers.get("Retry-After") or 0) or 20 * (attempt + 1)
            # Per-minute limits clear quickly; a daily limit says to wait hours.
            if e.code == 429 and wait <= 120 and attempt < 5:
                print(f"  (rate limited; waiting {wait}s)")
                time.sleep(wait)
                continue
            if e.code >= 500 and attempt < 3:
                time.sleep(10 * (attempt + 1))
                continue
            raise RuntimeError(f"GitHub Models error {e.code}: {detail}") from None
    raise RuntimeError("GitHub Models: still rate limited after retries")


def _chat(system, content, model, max_tokens, response_format=None):
    body = {"model": model or MODEL, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": _blocks(content)}]}
    if response_format:
        body["response_format"] = response_format
    choice = _post(body)["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError("The model's answer was cut off (max_tokens)")
    if choice.get("finish_reason") == "content_filter":
        raise RuntimeError("The model declined (content filter)")
    return (choice["message"].get("content") or "").strip()


def _parse(raw):
    raw = raw.replace("```json", "").replace("```", "")
    return json.loads(raw[raw.find("{"):raw.rfind("}") + 1])


def ask_json(system, content, schema=None, model=None, max_tokens=MAX_OUTPUT):
    """A JSON object back. With a schema the reply is held to it (structured
    outputs); if the model doesn't support that, the schema goes in the prompt."""
    if schema:
        try:
            fmt = {"type": "json_schema",
                   "json_schema": {"name": "answer", "strict": True, "schema": schema}}
            return _parse(_chat(system, content, model, max_tokens, fmt))
        except RuntimeError as e:
            if "error 400" not in str(e):
                raise
            note = "\n\nReply with one JSON object matching this schema:\n" + json.dumps(schema)
            content = content + note if isinstance(content, str) else \
                content + [{"type": "text", "text": note}]
    return _parse(_chat(system, content, model, max_tokens, {"type": "json_object"}))


def ask_text(system, prompt, model=None, max_tokens=MAX_OUTPUT):
    return _chat(system, prompt, model, max_tokens)
