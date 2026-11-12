"""Command line: python -m hive <command>."""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from hive import __version__, agents, config, db, llm, report


def _open(args):
    cfg = config.load(args.config)
    args.conn = db.connect(args.db)
    return cfg, args.conn


def cmd_init(args):
    created = config.write_default(args.config)
    db.connect(args.db).close()
    print(f"{'Created' if created else 'Kept existing'} {args.config}; database ready at {args.db}.")
    print("Next: edit the config if you like, then run `python -m hive run`.")


def cmd_gather(args):
    cfg, conn = _open(args)
    print(f"{agents.gather(conn, cfg)} new signals.")


def _stage(fn, label):
    def run(args):
        cfg, conn = _open(args)
        backend = llm.make(cfg, args.backend)
        print(f"{fn(conn, backend, cfg, args.limit)} {label}.")
    return run


def cmd_run(args):
    cfg, conn = _open(args)
    backend = llm.make(cfg, args.backend)
    if not args.skip_gather:
        print(f"Gather:  {agents.gather(conn, cfg)} new signals")
    print(f"Scout:   {agents.scout(conn, backend, cfg, args.limit)} opportunities")
    print(f"Analyst: {agents.analyze(conn, backend, cfg, args.limit)} scored")
    print(f"Builder: {agents.build(conn, backend, cfg, args.limit)} offers drafted")
    pending = conn.execute("SELECT COUNT(*) FROM offers WHERE status = 'pending'").fetchone()[0]
    print(f"\n{pending} offers waiting for you. See them with `python -m hive queue`.")


def cmd_queue(args):
    _, conn = _open(args)
    rows = conn.execute("SELECT * FROM offers WHERE status = 'pending' ORDER BY id").fetchall()
    if not rows:
        print("Nothing waiting for review.")
    for o in rows:
        price = f"${o['price_usd']:.0f}" if o["price_usd"] is not None else "-"
        print(f"#{o['id']:<4} {o['channel']:<8} {price:>6}  {o['title']}")


def cmd_show(args):
    _, conn = _open(args)
    o = conn.execute(
        "SELECT f.*, p.problem, p.buyer, p.evidence, s.total, s.rationale, g.url FROM offers f"
        " JOIN opportunities p ON p.id = f.opportunity_id LEFT JOIN scores s ON s.opportunity_id = p.id"
        " LEFT JOIN signals g ON g.id = p.signal_id WHERE f.id = ?", (args.id,)).fetchone()
    if not o:
        print(f"No offer #{args.id}.")
        return 1
    print(f"#{o['id']} {o['title']}  [{o['status']}]")
    print(f"Channel: {o['channel']}   Price: {o['price_usd']}   Score: {o['total']}")
    print(f"\nPitch: {o['pitch']}\nDeliverables:")
    for d in json.loads(o["deliverables"] or "[]"):
        print(f"  - {d}")
    print(f"\nProblem: {o['problem']}\nBuyer: {o['buyer']}\nEvidence: {o['evidence']}")
    print(f"Analyst: {o['rationale']}\nSource: {o['url']}")


def _decide(decision):
    def run(args):
        _, conn = _open(args)
        if agents.review(conn, args.id, decision, args.note):
            print(f"Offer #{args.id} {decision}.")
        else:
            print(f"Offer #{args.id} is not waiting for review.")
            return 1
    return run


def cmd_report(args):
    _, conn = _open(args)
    text = report.markdown(conn)
    out = Path(args.out or f"reports/{date.today().isoformat()}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"Report written to {out}.")


def cmd_log(args):
    _, conn = _open(args)
    for e in conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (args.n,)).fetchall()[::-1]:
        print(f"{e['ts']}  {e['agent']:<8} {e['message']}")


def build_parser():
    p = argparse.ArgumentParser(prog="hive", description="Alyos Hive: AI agents find and draft offers; you approve.")
    p.add_argument("--version", action="version", version=f"alyos-hive {__version__}")
    p.add_argument("--config", default="hive.config.json")
    p.add_argument("--db", default="hive.db")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create config and database").set_defaults(fn=cmd_init)
    sub.add_parser("gather", help="read all feeds").set_defaults(fn=cmd_gather)
    for name, fn, label, help_ in [
        ("scout", agents.scout, "opportunities found", "find opportunities in new signals"),
        ("analyze", agents.analyze, "opportunities scored", "score new opportunities"),
        ("build", agents.build, "offers drafted", "draft offers for high scores"),
    ]:
        s = sub.add_parser(name, help=help_)
        s.add_argument("--backend", choices=["ollama", "anthropic", "mock"])
        s.add_argument("--limit", type=int)
        s.set_defaults(fn=_stage(fn, label))

    r = sub.add_parser("run", help="gather, scout, analyze and build in one go")
    r.add_argument("--backend", choices=["ollama", "anthropic", "mock"])
    r.add_argument("--limit", type=int)
    r.add_argument("--skip-gather", action="store_true")
    r.set_defaults(fn=cmd_run)

    sub.add_parser("queue", help="offers waiting for review").set_defaults(fn=cmd_queue)
    s = sub.add_parser("show", help="full detail of one offer")
    s.add_argument("id", type=int)
    s.set_defaults(fn=cmd_show)
    for name, decision in [("approve", "approved"), ("reject", "rejected")]:
        s = sub.add_parser(name, help=f"{name} an offer")
        s.add_argument("id", type=int)
        s.add_argument("--note")
        s.set_defaults(fn=_decide(decision))

    s = sub.add_parser("report", help="write a markdown report")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_report)
    s = sub.add_parser("log", help="recent agent activity")
    s.add_argument("-n", type=int, default=30)
    s.set_defaults(fn=cmd_log)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args) or 0
    except llm.BackendError as e:
        print(f"Model backend error: {e}", file=sys.stderr)
        print("Tip: start Ollama, set ANTHROPIC_API_KEY, or try --backend mock.", file=sys.stderr)
        return 2
    finally:
        if getattr(args, "conn", None) is not None:
            args.conn.close()
