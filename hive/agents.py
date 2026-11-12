"""The workers. Each agent reads one stage from the database and writes the next.

    signals --Scout--> opportunities --Analyst--> scores --Builder--> offers --You--> approved

Nothing leaves the hive without a human approving it.
"""

import json

from hive import db, feeds
from hive.llm import BackendError, Unreachable, ask_json

SCOUT_SYSTEM = """ROLE: SCOUT for Alyos Hive, a one-person business where AI agents do the work and a human checks every result.
Read one public post. Decide whether it shows a real problem someone would pay to have solved,
and whether AI agents (research, writing, coding, automation, data analysis, design) could deliver the solution.
Reject: hype, news with no buyer, requests needing physical presence, licensed professions, anything illegal or deceptive.
Allowed offer_type values: {offer_types}.
Answer with JSON only:
{{"relevant": true|false, "title": "short name of the opportunity", "problem": "one sentence",
  "buyer": "who pays", "offer_type": "one allowed value", "evidence": "quote or fact from the post"}}"""

ANALYST_SYSTEM = """ROLE: ANALYST for Alyos Hive. Score one opportunity from 1 (bad) to 5 (good) on each criterion:
- demand: how clearly people ask and would pay for this
- competition: 5 = few good alternatives, 1 = crowded with cheap or free options
- cost: 5 = near-zero cost to deliver, 1 = expensive tools or long build
- fit: how well AI agents plus one human reviewer can deliver it to a high standard{edges}
- speed: 5 = sellable within a week, 1 = months away
Be strict. Most opportunities should score 2-3. Answer with JSON only:
{{"demand": n, "competition": n, "cost": n, "fit": n, "speed": n, "rationale": "two sentences"}}"""

BUILDER_SYSTEM = """ROLE: BUILDER for Alyos Hive. Draft one sellable offer for this opportunity.
Allowed channels: {channels}. Price in USD, realistic for the channel. Promise only what AI agents
plus one human reviewer can deliver. No income claims, no fake reviews, no guarantees.
Answer with JSON only:
{{"channel": "one allowed value", "title": "listing title under 80 characters", "pitch": "two or three sentences",
  "deliverables": ["item", "item"], "price_usd": number}}"""

WEIGHTS = {"demand": 0.30, "competition": 0.20, "cost": 0.15, "fit": 0.15, "speed": 0.20}


def _clamp(value):
    try:
        return max(1, min(5, int(round(float(value)))))
    except (TypeError, ValueError):
        return 1


def total_score(scores):
    """Weighted 1-5 scores mapped onto 0-100."""
    weighted = sum(_clamp(scores.get(k)) * w for k, w in WEIGHTS.items())
    return round((weighted - 1) / 4 * 100, 1)


def gather(conn, cfg):
    """Pull every configured feed into the signals table."""
    added = 0
    for feed in cfg["feeds"]:
        try:
            items = feeds.fetch(feed["url"])
        except Exception as e:  # one broken feed must not stop the run
            db.log(conn, "gather", f"{feed['name']}: failed ({e})")
            continue
        new = sum(db.add_signal(conn, feed["name"], i["title"], i["url"], i["summary"]) for i in items)
        db.log(conn, "gather", f"{feed['name']}: {len(items)} items, {new} new")
        added += new
    return added


def scout(conn, backend, cfg, limit=None):
    system = SCOUT_SYSTEM.format(offer_types=", ".join(cfg["offer_types"]))
    rows = conn.execute("SELECT * FROM signals WHERE status = 'new' ORDER BY id LIMIT ?",
                        (limit or cfg["max_per_run"],)).fetchall()
    found = 0
    for s in rows:
        prompt = f"SOURCE: {s['source']}\nTITLE: {s['title']}\nURL: {s['url']}\nTEXT: {s['summary']}"
        try:
            out = ask_json(backend, system, prompt)
        except Unreachable:
            raise
        except BackendError as e:
            db.log(conn, "scout", f"signal {s['id']}: {e}")
            continue
        if out.get("relevant"):
            offer_type = out.get("offer_type") if out.get("offer_type") in cfg["offer_types"] else "service"
            conn.execute(
                "INSERT INTO opportunities (signal_id, title, problem, buyer, offer_type, evidence, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (s["id"], str(out.get("title") or s["title"])[:200], out.get("problem"), out.get("buyer"),
                 offer_type, out.get("evidence"), db.now()),
            )
            found += 1
        conn.execute("UPDATE signals SET status = 'scouted' WHERE id = ?", (s["id"],))
        conn.commit()
    db.log(conn, "scout", f"read {len(rows)} signals, found {found} opportunities")
    return found


def analyze(conn, backend, cfg, limit=None):
    edges = cfg.get("operator_edges") or []
    edge_text = f"\n  (the human reviewer is strong in: {', '.join(edges)})" if edges else ""
    system = ANALYST_SYSTEM.format(edges=edge_text)
    rows = conn.execute("SELECT * FROM opportunities WHERE status = 'new' ORDER BY id LIMIT ?",
                        (limit or cfg["max_per_run"],)).fetchall()
    for o in rows:
        prompt = (f"TITLE: {o['title']}\nPROBLEM: {o['problem']}\nBUYER: {o['buyer']}\n"
                  f"OFFER TYPE: {o['offer_type']}\nEVIDENCE: {o['evidence']}")
        try:
            out = ask_json(backend, system, prompt)
        except Unreachable:
            raise
        except BackendError as e:
            db.log(conn, "analyst", f"opportunity {o['id']}: {e}")
            continue
        parts = {k: _clamp(out.get(k)) for k in WEIGHTS}
        conn.execute(
            "INSERT OR REPLACE INTO scores (opportunity_id, demand, competition, cost, fit, speed, total, rationale)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (o["id"], *parts.values(), total_score(parts), out.get("rationale")),
        )
        conn.execute("UPDATE opportunities SET status = 'scored' WHERE id = ?", (o["id"],))
        conn.commit()
    db.log(conn, "analyst", f"scored {len(rows)} opportunities")
    return len(rows)


def build(conn, backend, cfg, limit=None):
    system = BUILDER_SYSTEM.format(channels=", ".join(cfg["channels"]))
    rows = conn.execute(
        "SELECT o.*, s.total, s.rationale FROM opportunities o JOIN scores s ON s.opportunity_id = o.id"
        " WHERE o.status = 'scored' ORDER BY s.total DESC LIMIT ?",
        (limit or cfg["max_per_run"],),
    ).fetchall()
    built = 0
    for o in rows:
        if o["total"] < cfg["min_score"]:
            conn.execute("UPDATE opportunities SET status = 'parked' WHERE id = ?", (o["id"],))
            conn.commit()
            continue
        prompt = (f"TITLE: {o['title']}\nPROBLEM: {o['problem']}\nBUYER: {o['buyer']}\n"
                  f"OFFER TYPE: {o['offer_type']}\nANALYST: {o['rationale']}")
        try:
            out = ask_json(backend, system, prompt)
        except Unreachable:
            raise
        except BackendError as e:
            db.log(conn, "builder", f"opportunity {o['id']}: {e}")
            continue
        channel = out.get("channel") if out.get("channel") in cfg["channels"] else cfg["channels"][0]
        try:
            price = float(out.get("price_usd"))
        except (TypeError, ValueError):
            price = None
        conn.execute(
            "INSERT INTO offers (opportunity_id, channel, title, pitch, deliverables, price_usd, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (o["id"], channel, str(out.get("title") or o["title"])[:120], out.get("pitch"),
             json.dumps(out.get("deliverables") or []), price, db.now()),
        )
        conn.execute("UPDATE opportunities SET status = 'built' WHERE id = ?", (o["id"],))
        conn.commit()
        built += 1
    db.log(conn, "builder", f"drafted {built} offers")
    return built


def review(conn, offer_id, decision, note=None):
    """The human gate. decision is 'approved' or 'rejected'."""
    cur = conn.execute(
        "UPDATE offers SET status = ?, reviewed_at = ?, note = ? WHERE id = ? AND status = 'pending'",
        (decision, db.now(), note, offer_id),
    )
    conn.commit()
    if cur.rowcount:
        db.log(conn, "human", f"offer {offer_id} {decision}")
    return cur.rowcount == 1
