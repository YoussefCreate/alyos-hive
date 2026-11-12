"""Configuration: a plain JSON file so it is easy to edit on any machine."""

import copy
import json
from pathlib import Path

OFFER_TYPES = [
    "kit",            # automation kits, templates, n8n workflows
    "service",        # fixed-price AI-built service, checked by a human
    "agent",          # ready-made agent or Claude skill
    "data_product",   # datasets, reports, dashboards
    "learning",       # AI learning products for small firms
]

DEFAULTS = {
    "backend": "ollama",  # ollama | anthropic | mock
    "ollama": {"host": "http://localhost:11434", "model": "llama3.1:8b"},
    "anthropic": {"model": "claude-haiku-5-5", "max_tokens": 1200},
    "feeds": [
        {"name": "Ask HN", "url": "https://hnrss.org/ask"},
        {"name": "r/smallbusiness", "url": "https://www.reddit.com/r/smallbusiness/new/.rss"},
        {"name": "r/Entrepreneur", "url": "https://www.reddit.com/r/Entrepreneur/new/.rss"},
        {"name": "r/nocode", "url": "https://www.reddit.com/r/nocode/new/.rss"},
    ],
    "offer_types": OFFER_TYPES,
    "channels": ["fiverr", "gumroad", "direct"],
    "min_score": 60,
    "max_per_run": 20,
    "operator_edges": [],
}


def load(path):
    path = Path(path)
    cfg = copy.deepcopy(DEFAULTS)
    if path.exists():
        with path.open(encoding="utf-8") as f:
            user = json.load(f)
        for key, value in user.items():
            if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                cfg[key].update(value)
            else:
                cfg[key] = value
    return cfg


def write_default(path):
    path = Path(path)
    if path.exists():
        return False
    with path.open("w", encoding="utf-8") as f:
        json.dump(DEFAULTS, f, indent=2)
        f.write("\n")
    return True
