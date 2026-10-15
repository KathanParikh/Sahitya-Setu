"""The live QA evaluation's resume support, without any API call."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tests.helpers  # noqa: F401  (fake keys)
from evaluation import live_qa_eval as ev

IDS = ev.qa_case_ids()
FP = "fingerprint-a"


def result(answer="answer", llm_error=""):
    return {"answer": answer, "found": not llm_error, "rewrites_used": 0, "queries_tried": [],
            "citations": [], "trace": [], "llm_error": llm_error}


class FakeGuard:
    def __init__(self):
        self.calls, self.rate_limited, self.blocked = 0, 0, None


class Recorder:
    """Answer function: records which cases ran, can fail on one case, and
    snapshots the saved file at each call to prove progress was written.

    Several cases share a question (T1 and T2 run three times each), so the
    case id comes from the runner itself (see Base.run_part), not the text.
    """

    def __init__(self, out_path, block_at=None, guard=None):
        self.out_path, self.block_at, self.guard = out_path, block_at, guard
        self.ran, self.saved_before, self.current = [], [], None

    def __call__(self, question):
        case_id = self.current
        self.ran.append(case_id)
        saved = json.loads(self.out_path.read_text())["qa"]
        self.saved_before.append(sum(r["verdict"] in ev.COMPLETED for r in saved))
        if case_id == self.block_at:
            if self.guard is not None:
                self.guard.blocked = "daily quota exhausted: tokens per day (TPD)"
            return result(llm_error="groq quota exhausted, not retrying")
        return result()


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.out = self.dir / "live_qa_eval_qa.json"
        # The judging itself is tested elsewhere; here every completed case passes.
        patcher = mock.patch.object(ev, "judge", return_value=("PASS", {"stub": True}))
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_part(self, rec, guard=None, **kw):
        sleeps = []
        real = ev.run_qa_case

        def tracking(case, answer_fn, g):
            rec.current = case[0]
            return real(case, answer_fn, g)
        with mock.patch.object(ev, "run_qa_case", side_effect=tracking):
            rows = ev.run_qa_part(rec, guard or FakeGuard(), self.out, FP, sleep=sleeps.append, **kw)
        return rows, sleeps

    def saved(self):
        return json.loads(self.out.read_text())


class FreshRun(Base):
    def test_all_cases_run_in_order_and_progress_is_saved_after_each(self):
        rec = Recorder(self.out)
        rows, sleeps = self.run_part(rec)
        self.assertEqual(rec.ran, IDS)
        self.assertEqual(rec.saved_before, list(range(len(IDS))))  # one more saved per case
        self.assertEqual(ev.qa_summary(rows)["PASS"], len(IDS))
        self.assertEqual(self.saved()["meta"]["code_fingerprint"], FP)
        self.assertEqual(len(sleeps), len(IDS) - 1)  # paced between executed cases only


class QuotaInterruption(Base):
    def test_blocked_case_stops_the_run_and_nothing_after_it_runs(self):
        guard = FakeGuard()
        rec = Recorder(self.out, block_at=IDS[3], guard=guard)
        with mock.patch("builtins.print") as printed:
            rows, _ = self.run_part(rec, guard)
        self.assertEqual(rec.ran, IDS[:4])
        verdicts = {r["id"]: r["verdict"] for r in self.saved()["qa"]}
        self.assertEqual([verdicts[i] for i in IDS[:3]], ["PASS"] * 3)
        self.assertEqual(verdicts[IDS[3]], "BLOCKED")
        self.assertTrue(all(verdicts[i] == "NOT RUN" for i in IDS[4:]))
        summary = self.saved()["meta"]["summary"]
        self.assertEqual(summary["PASS"], 3)  # blocked and unrun cases are not passes
        self.assertEqual(summary["BLOCKED"] + summary["NOT RUN"], len(IDS) - 3)
        output = " ".join(str(c.args[0]) for c in printed.call_args_list)
        self.assertIn(f"First unfinished case: {IDS[3]}", output)
        self.assertIn(f"--part qa --qa-from {IDS[3]}", output)

    def test_guard_stops_at_once_on_a_daily_quota_429(self):
        class Provider:
            calls = 0

            def _complete(self, prompt, system, temperature):
                Provider.calls += 1
                exc = Exception("Rate limit reached ... on tokens per day (TPD): Limit 200000, Used 199758")
                exc.status_code = 429
                raise exc
        guard = ev.Guard(Provider)
        with self.assertRaises(Exception):
            Provider()._complete("p", None, 0)
        self.assertIn("daily quota", guard.blocked)
        with self.assertRaises(RuntimeError):  # refused without a request
            Provider()._complete("p", None, 0)
        self.assertEqual(Provider.calls, 1)

    def test_per_minute_429_is_left_to_the_paced_retry(self):
        class Provider:
            def _complete(self, prompt, system, temperature):
                exc = Exception("Rate limit reached ... on tokens per minute (TPM): Limit 8000")
                exc.status_code = 429
                raise exc
        guard = ev.Guard(Provider)
        with self.assertRaises(Exception):
            Provider()._complete("p", None, 0)
        self.assertIsNone(guard.blocked)
        self.assertEqual(guard.rate_limited, 1)

    def test_daily_quota_detection(self):
        self.assertTrue(ev.is_daily_quota("on tokens per day (TPD): Limit 200000"))
        self.assertTrue(ev.is_daily_quota("requests per day (RPD)"))
        self.assertTrue(ev.is_daily_quota("GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
        self.assertFalse(ev.is_daily_quota("on tokens per minute (TPM): Limit 8000"))


class Resume(Base):
    def interrupted_run(self, block_at):
        guard = FakeGuard()
        with mock.patch("builtins.print"):
            self.run_part(Recorder(self.out, block_at=block_at, guard=guard), guard)
        return ev.load_previous(self.out, FP)

    def test_resume_runs_only_unfinished_cases_from_the_start_point(self):
        previous = self.interrupted_run(IDS[3])
        rec = Recorder(self.out)
        with mock.patch("builtins.print"):
            rows, sleeps = self.run_part(rec, start_from=IDS[3], previous=previous)
        self.assertEqual(rec.ran, IDS[3:])
        self.assertEqual(ev.qa_summary(rows), {"PASS": len(IDS), "FAIL": 0, "BLOCKED": 0, "NOT RUN": 0})
        self.assertTrue(all(r.get("carried_over") for r in rows[:3]))
        self.assertEqual(len(sleeps), len(IDS[3:]) - 1)

    def test_completed_cases_after_the_start_point_are_not_rerun(self):
        previous = {IDS[5]: {"id": IDS[5], "verdict": "PASS"}, IDS[6]: {"id": IDS[6], "verdict": "FAIL"}}
        rec = Recorder(self.out)
        with mock.patch("builtins.print"):
            rows, _ = self.run_part(rec, start_from=IDS[2], previous=previous)
        self.assertNotIn(IDS[5], rec.ran)
        self.assertNotIn(IDS[6], rec.ran)
        verdicts = {r["id"]: r["verdict"] for r in rows}
        self.assertEqual(verdicts[IDS[6]], "FAIL")  # a carried FAIL stays a FAIL

    def test_unfinished_cases_before_the_start_point_stay_unfinished(self):
        previous = {IDS[0]: {"id": IDS[0], "verdict": "PASS"},
                    IDS[1]: {"id": IDS[1], "verdict": "BLOCKED", "error": "quota"}}
        rec = Recorder(self.out)
        with mock.patch("builtins.print"):
            rows, _ = self.run_part(rec, start_from=IDS[4], previous=previous)
        verdicts = {r["id"]: r["verdict"] for r in rows}
        self.assertEqual(verdicts[IDS[1]], "BLOCKED")
        self.assertEqual(verdicts[IDS[2]], "NOT RUN")
        self.assertEqual(ev.first_unfinished(rows), IDS[1])
        self.assertNotIn(IDS[1], rec.ran)

    def test_previous_results_from_other_code_are_refused(self):
        self.interrupted_run(IDS[2])
        with self.assertRaises(SystemExit) as cm:
            ev.load_previous(self.out, "fingerprint-b")
        self.assertIn("different code", str(cm.exception))

    def test_resume_without_previous_results_is_refused(self):
        with self.assertRaises(SystemExit):
            ev.load_previous(self.dir / "missing.json", FP)


class CaseIds(unittest.TestCase):
    def test_valid_ids_are_accepted(self):
        for case_id in IDS:
            ev.validate_qa_from(case_id)

    def test_invalid_id_fails_and_lists_the_valid_ones(self):
        with self.assertRaises(SystemExit) as cm:
            ev.validate_qa_from("T9-nope")
        self.assertIn("T9-nope", str(cm.exception))
        self.assertIn(IDS[0], str(cm.exception))

    def run_main(self, *argv, data_dir):
        with mock.patch.object(ev.config, "DATA_DIR", data_dir), \
             mock.patch.object(ev.llm_client, "get_llm", side_effect=AssertionError("API client created")), \
             mock.patch("sys.argv", ["live_qa_eval", *argv]):
            ev.main()

    def test_bad_id_fails_before_any_api_client_exists(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                self.run_main("--part", "qa", "--qa-from", "T9-nope", data_dir=Path(d))

    def test_qa_from_requires_part_qa(self):
        with tempfile.TemporaryDirectory() as d, mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                self.run_main("--part", "all", "--qa-from", IDS[0], data_dir=Path(d))

    def test_resume_from_other_code_fails_before_any_api_client_exists(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "eval" / "live_qa_eval_qa.json"
            out.parent.mkdir()
            out.write_text(json.dumps({"meta": {"code_fingerprint": "old"}, "qa": []}))
            with self.assertRaises(SystemExit):
                self.run_main("--part", "qa", "--qa-from", IDS[0], data_dir=Path(d))
            self.assertEqual(json.loads(out.read_text())["meta"]["code_fingerprint"], "old")


class Backups(unittest.TestCase):
    def test_backup_copies_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "live_qa_eval_qa.json"
            out.write_text('{"run": 1}')
            first = ev.backup_results(out)
            out.write_text('{"run": 2}')
            second = ev.backup_results(out)  # same second: must get a new name
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_text(), '{"run": 1}')
            self.assertEqual(second.read_text(), '{"run": 2}')
            self.assertEqual(out.read_text(), '{"run": 2}')  # original left in place

    def test_no_backup_when_there_is_nothing_to_preserve(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(ev.backup_results(Path(d) / "absent.json"))

    def test_main_backs_up_before_resuming(self):
        with tempfile.TemporaryDirectory() as d:
            eval_dir = Path(d) / "eval"
            eval_dir.mkdir()
            out = eval_dir / "live_qa_eval_qa.json"
            out.write_text(json.dumps({"meta": {"code_fingerprint": ev.code_fingerprint()},
                                       "qa": [{"id": IDS[0], "verdict": "PASS"}]}))
            before = out.read_text()
            with mock.patch.object(ev.config, "DATA_DIR", Path(d)), \
                 mock.patch.object(ev.llm_client, "get_llm", side_effect=RuntimeError("stop here")), \
                 mock.patch("sys.argv", ["x", "--part", "qa", "--qa-from", IDS[1]]), \
                 mock.patch("builtins.print"):
                with self.assertRaises(RuntimeError):
                    ev.main()
            backups = list(eval_dir.glob("live_qa_eval_qa.backup-*.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), before)


class Fingerprint(unittest.TestCase):
    def test_fingerprint_is_stable_and_tracks_settings(self):
        a = ev.code_fingerprint()
        self.assertEqual(a, ev.code_fingerprint())
        with mock.patch.object(ev.config, "GROQ_MODEL", "some-other-model"):
            self.assertNotEqual(a, ev.code_fingerprint())


if __name__ == "__main__":
    unittest.main()
