"""Model backends. Standard library only, so it runs on a fresh Windows Python."""

import json
import os
import re
import urllib.error
import urllib.request


class BackendError(RuntimeError):
    pass


class Unreachable(BackendError):
    """The model server or API cannot be reached; stop the run instead of skipping items."""


def _post(url, payload, headers, timeout=180):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise BackendError(f"HTTP {e.code} from {url}: {body}") from e
    except urllib.error.URLError as e:
        raise Unreachable(f"Cannot reach {url}: {e.reason}") from e


class Ollama:
    """Local models through Ollama (https://ollama.com)."""

    def __init__(self, host, model):
        self.host = host.rstrip("/")
        self.model = model

    def complete(self, system, prompt):
        out = _post(
            f"{self.host}/api/chat",
            {
                "model": self.model,
                "stream": False,
                "format": "json",
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            },
            {},
        )
        return out["message"]["content"]


class Anthropic:
    """Claude through the Anthropic API. Needs ANTHROPIC_API_KEY in the environment."""

    def __init__(self, model, max_tokens=1200):
        self.key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.key:
            raise BackendError("Set ANTHROPIC_API_KEY to use the anthropic backend.")
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, system, prompt):
        out = _post(
            "https://api.anthropic.com/v1/messages",
            {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
            {"x-api-key": self.key, "anthropic-version": "2023-06-01"},
        )
        return "".join(block.get("text", "") for block in out.get("content", []))


class Mock:
    """Deterministic answers with no model at all, for tests and a first dry run."""

    DEMAND_WORDS = ("need", "looking for", "help", "struggl", "how do", "anyone", "recommend", "tool")

    def complete(self, system, prompt):
        text = prompt.lower()
        title = prompt.split("TITLE:", 1)[-1].split("\n", 1)[0].strip()[:90] or "Untitled"
        if "ROLE: SCOUT" in system:
            if any(w in text for w in self.DEMAND_WORDS):
                return json.dumps({
                    "relevant": True,
                    "title": f"Solve: {title}",
                    "problem": "Owner describes a recurring manual task they want handled.",
                    "buyer": "small business owner",
                    "offer_type": "service",
                    "evidence": "The post asks directly for a solution.",
                })
            return json.dumps({"relevant": False})
        if "ROLE: ANALYST" in system:
            return json.dumps({"demand": 4, "competition": 3, "cost": 4, "fit": 4, "speed": 4,
                               "rationale": "Clear ask, buildable with AI in under a day."})
        if "ROLE: BUILDER" in system:
            return json.dumps({
                "channel": "fiverr",
                "title": f"I will {title[:60].lower()} with an AI workflow",
                "pitch": "A working setup delivered in 48 hours, tested by a human before handover.",
                "deliverables": ["Working workflow", "Setup guide", "One revision"],
                "price_usd": 75,
            })
        return "{}"


def make(cfg, override=None):
    name = override or cfg["backend"]
    if name == "ollama":
        return Ollama(cfg["ollama"]["host"], cfg["ollama"]["model"])
    if name == "anthropic":
        return Anthropic(cfg["anthropic"]["model"], cfg["anthropic"].get("max_tokens", 1200))
    if name == "mock":
        return Mock()
    raise BackendError(f"Unknown backend '{name}'. Use ollama, anthropic or mock.")


def ask_json(backend, system, prompt, retries=1):
    """Call the model and return the first JSON object in its answer."""
    last = ""
    for _ in range(retries + 1):
        last = backend.complete(system, prompt)
        match = re.search(r"\{.*\}", last, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        prompt += "\n\nReply with one valid JSON object only."
    raise BackendError(f"Model did not return JSON. Last answer: {last[:300]}")
