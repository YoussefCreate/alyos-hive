"""Markdown report of what the hive has found and what is waiting for you."""

import json
from datetime import date


def _count(conn, sql):
    return conn.execute(sql).fetchone()[0]


def markdown(conn):
    pending_n = _count(conn, "SELECT COUNT(*) FROM offers WHERE status = 'pending'")
    approved_n = _count(conn, "SELECT COUNT(*) FROM offers WHERE status = 'approved'")
    lines = [f"# Hive report, {date.today().isoformat()}", ""]
    lines += [
        "| Stage | Count |", "|---|---|",
        f"| Signals read | {_count(conn, 'SELECT COUNT(*) FROM signals')} |",
        f"| Opportunities found | {_count(conn, 'SELECT COUNT(*) FROM opportunities')} |",
        f"| Scored | {_count(conn, 'SELECT COUNT(*) FROM scores')} |",
        f"| Offers waiting for review | {pending_n} |",
        f"| Offers approved | {approved_n} |",
        "",
        "## Top opportunities", "",
        "| Score | Type | Opportunity | Buyer |", "|---|---|---|---|",
    ]
    for r in conn.execute(
        "SELECT o.title, o.offer_type, o.buyer, s.total FROM opportunities o"
        " JOIN scores s ON s.opportunity_id = o.id ORDER BY s.total DESC LIMIT 10"
    ):
        lines.append(f"| {r['total']:.0f} | {r['offer_type']} | {r['title']} | {r['buyer'] or ''} |")

    lines += ["", "## Waiting for your review", ""]
    pending = conn.execute("SELECT * FROM offers WHERE status = 'pending' ORDER BY id").fetchall()
    if not pending:
        lines.append("Nothing waiting.")
    for o in pending:
        price = f"${o['price_usd']:.0f}" if o["price_usd"] is not None else "no price"
        lines += [f"### #{o['id']} {o['title']}", f"{o['channel']} · {price}", "", o["pitch"] or "", ""]
        lines += [f"- {d}" for d in json.loads(o["deliverables"] or "[]")]
        lines += ["", f"Approve: `python -m hive approve {o['id']}` · Reject: `python -m hive reject {o['id']}`", ""]
    return "\n".join(lines) + "\n"
