# Alyos Hive

**AI agents find work worth selling, score it and draft the offer. A human approves every one.**

Alyos Hive is an open-source "bee hive" of AI workers for one-person businesses. The agents read public posts where people ask for help, decide which ones are real paid problems, score them strictly and draft a ready-to-list offer. Nothing is published, sent or sold until you approve it.

It runs on your own computer with free local models ([Ollama](https://ollama.com)) or with Claude through the Anthropic API. It needs only Python, with no packages to install.

```
 feeds ──► Gather ──► Scout ──► Analyst ──► Builder ──► YOU ──► Fiverr / Gumroad / direct
          (signals)  (is this   (score     (draft      (approve
                      a paid     0-100)     the offer)  or reject)
                      problem?)
```

## Quick start

```bash
git clone https://github.com/YoussefCreate/alyos-hive.git
cd alyos-hive
python -m hive init                  # creates hive.config.json and hive.db
python -m hive run --backend mock    # dry run with no model, to see the flow
```

Then with a real model:

```bash
ollama pull llama3.1:8b
python -m hive run                   # uses Ollama by default
python -m hive queue                 # offers waiting for you
python -m hive show 1                # full detail and the source post
python -m hive approve 1             # or: python -m hive reject 1 --note "too crowded"
python -m hive report                # markdown summary in reports/
```

To use Claude instead, set `ANTHROPIC_API_KEY` and run `python -m hive run --backend anthropic`.

Windows users: see [docs/SETUP-WINDOWS.md](docs/SETUP-WINDOWS.md).

## The workers

| Agent | Reads | Writes | Job |
|---|---|---|---|
| **Gather** | RSS/Atom feeds in the config | `signals` | Collects new public posts, skipping duplicates |
| **Scout** | new signals | `opportunities` | Keeps only real problems someone would pay to solve that AI can deliver |
| **Analyst** | new opportunities | `scores` | Scores demand, competition, cost, fit and speed from 1 to 5; weighted total 0-100 |
| **Builder** | scores above `min_score` | `offers` | Drafts title, pitch, deliverables and price for a channel |
| **You** | pending offers | approved/rejected | The only path out of the hive |

Everything lives in one SQLite file (`hive.db`), so you can open it with any SQLite viewer, or Excel through an ODBC driver.

## Offer types

The hive sorts every opportunity into one of five offer types. See [docs/OFFERS.md](docs/OFFERS.md).

`kit` · `service` · `agent` · `data_product` · `learning`

## Configuration

`hive.config.json` is created by `init`. The fields you will touch most:

| Field | Default | Meaning |
|---|---|---|
| `backend` | `ollama` | `ollama`, `anthropic` or `mock` |
| `ollama.model` | `llama3.1:8b` | Any model you have pulled |
| `anthropic.model` | `claude-haiku-5-5` | Any Claude model ID |
| `feeds` | Ask HN, r/smallbusiness, r/Entrepreneur, r/nocode | Add any RSS or Atom feed |
| `min_score` | `60` | Offers are only drafted above this score |
| `channels` | fiverr, gumroad, direct | Where offers will be listed |
| `operator_edges` | empty | Optional: your strengths, used in the fit score |

## Running inside Claude

The [`skills/`](skills/) folder holds the same three roles as Claude skills, so scheduled Claude agents can do the scouting, scoring and drafting with the same rules as this code.

## Principles

- **Human approval for everything that leaves the hive.** The code has no publish button by design.
- **No income promises.** The hive finds and drafts; whether an offer sells is for the market to decide. Track real sales, not drafts.
- **Honest offers only.** The agents are told to reject deceptive work and never to write fake reviews or guarantees.
- **Local first.** Runs offline with Ollama; your data stays in your folder.

## AI-IWC

This repository merges Alyos Hive with AI-IWC, the earlier local multi-agent system. The AI-IWC code will be added in [`ai-iwc/`](ai-iwc/).

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md). Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT © 2026 Youssef Hammami / Alyos Alliance LLC
