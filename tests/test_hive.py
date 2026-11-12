import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from hive import agents, cli, config, db, feeds, llm

FIXTURES = Path(__file__).parent / "fixtures"


def make_cfg():
    cfg = config.load("does-not-exist.json")
    cfg["backend"] = "mock"
    cfg["feeds"] = [
        {"name": "rss", "url": str(FIXTURES / "sample_rss.xml")},
        {"name": "atom", "url": str(FIXTURES / "sample_atom.xml")},
        {"name": "broken", "url": str(FIXTURES / "missing.xml")},
    ]
    return cfg


class FeedTests(unittest.TestCase):
    def test_rss_and_atom(self):
        rss = feeds.fetch(str(FIXTURES / "sample_rss.xml"))
        atom = feeds.fetch(str(FIXTURES / "sample_atom.xml"))
        self.assertEqual(len(rss), 3)
        self.assertNotIn("<p>", rss[0]["summary"])
        self.assertEqual(atom[0]["url"], "https://example.com/atom/1")


class ScoreTests(unittest.TestCase):
    def test_bounds(self):
        self.assertEqual(agents.total_score({k: 5 for k in agents.WEIGHTS}), 100.0)
        self.assertEqual(agents.total_score({k: 1 for k in agents.WEIGHTS}), 0.0)
        self.assertEqual(agents.total_score({"demand": "junk", "fit": 99}), agents.total_score({"fit": 5}))


class JsonTests(unittest.TestCase):
    def test_extracts_json_from_chatter(self):
        class Chatty:
            def complete(self, system, prompt):
                return 'Sure! Here it is:\n{"relevant": false}\nHope that helps.'
        self.assertEqual(llm.ask_json(Chatty(), "", ""), {"relevant": False})

    def test_raises_without_json(self):
        class Silent:
            def complete(self, system, prompt):
                return "no json here"
        with self.assertRaises(llm.BackendError):
            llm.ask_json(Silent(), "", "")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.cfg = make_cfg()
        self.backend = llm.Mock()

    def tearDown(self):
        self.conn.close()

    def test_full_run_and_human_gate(self):
        self.assertEqual(agents.gather(self.conn, self.cfg), 4)
        self.assertEqual(agents.gather(self.conn, self.cfg), 0)  # no duplicates
        self.assertEqual(agents.scout(self.conn, self.backend, self.cfg), 3)  # park post rejected
        self.assertEqual(agents.analyze(self.conn, self.backend, self.cfg), 3)
        self.assertEqual(agents.build(self.conn, self.backend, self.cfg), 3)

        offer = self.conn.execute("SELECT * FROM offers ORDER BY id LIMIT 1").fetchone()
        self.assertEqual(offer["status"], "pending")
        self.assertEqual(len(json.loads(offer["deliverables"])), 3)

        self.assertTrue(agents.review(self.conn, offer["id"], "approved", "looks good"))
        self.assertFalse(agents.review(self.conn, offer["id"], "rejected"))  # already decided

        log = [r["message"] for r in self.conn.execute("SELECT message FROM events")]
        self.assertTrue(any("broken: failed" in m for m in log))

    def test_low_scores_are_parked(self):
        self.cfg["min_score"] = 101
        agents.gather(self.conn, self.cfg)
        agents.scout(self.conn, self.backend, self.cfg)
        agents.analyze(self.conn, self.backend, self.cfg)
        self.assertEqual(agents.build(self.conn, self.backend, self.cfg), 0)
        parked = self.conn.execute("SELECT COUNT(*) FROM opportunities WHERE status='parked'").fetchone()[0]
        self.assertEqual(parked, 3)


class UnreachableTests(unittest.TestCase):
    def test_run_stops_when_model_is_down(self):
        conn = db.connect(":memory:")
        cfg = make_cfg()
        agents.gather(conn, cfg)
        down = llm.Ollama("http://127.0.0.1:9", "none")
        with self.assertRaises(llm.Unreachable):
            agents.scout(conn, down, cfg)
        new = conn.execute("SELECT COUNT(*) FROM signals WHERE status='new'").fetchone()[0]
        self.assertEqual(new, 4)  # nothing was skipped
        conn.close()


class CliTests(unittest.TestCase):
    def test_cli_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path, db_path = Path(tmp) / "c.json", Path(tmp) / "h.db"
            base = ["--config", str(cfg_path), "--db", str(db_path)]
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.main(base + ["init"]), 0)
                data = json.loads(cfg_path.read_text())
                data["feeds"] = make_cfg()["feeds"][:2]
                cfg_path.write_text(json.dumps(data))
                self.assertEqual(cli.main(base + ["run", "--backend", "mock"]), 0)
                self.assertEqual(cli.main(base + ["queue"]), 0)
                self.assertEqual(cli.main(base + ["show", "1"]), 0)
                self.assertEqual(cli.main(base + ["approve", "1"]), 0)
                self.assertEqual(cli.main(base + ["report", "--out", str(Path(tmp) / "r.md")]), 0)
            self.assertIn("3 offers waiting", out.getvalue())
            self.assertIn("Offers approved | 1", (Path(tmp) / "r.md").read_text())


if __name__ == "__main__":
    unittest.main()
