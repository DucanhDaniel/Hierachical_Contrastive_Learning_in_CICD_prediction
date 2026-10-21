"""Evaluator isolation and provenance tests; production gold rules are untouched."""
import json
import io
import builtins
import shutil
import uuid
from contextlib import contextmanager
import unittest
from pathlib import Path
from unittest.mock import patch

from project3.crawl.gold_labels import gold_label, diagnostic_text
from project3.pipeline.rule_eval import Decision, Output, apply_q3, main, trace
import re


@contextmanager
def fixture_directory(area):
    # tempfile's Windows private ACL is inaccessible under the managed sandbox.
    directory = (area / ("test_eval_" + uuid.uuid4().hex)).resolve()
    if not directory.is_relative_to(area.resolve()):
        raise ValueError("Fixture escapes test area")
    directory.mkdir()
    try:
        yield directory
    finally:
        shutil.rmtree(directory)


class RuleEvalTest(unittest.TestCase):
    def test_trace_matches_original_and_tracks_deciding_job(self):
        cases = [
            ["You have 1 Checkstyle violation", "Could not find artifact x:y:jar:1"],
            ["There are test failures", "Could not find artifact x:y:jar:1"],
            ["No space left on device", "There are test failures"],
            ["Could not resolve dependencies\nHTTP 403\nCould not find artifact x:y:jar:1"],
            ["Could not resolve dependencies\nFailed to read artifact descriptor"],
            ["Missing 'x:y' dependency on the classpath"],
            ["[ERROR] Used undeclared dependencies found:"],
            ["No signal", "COMPILATION ERROR"],
        ]
        for jobs in cases:
            with self.subTest(jobs=jobs):
                d = trace([diagnostic_text(t) for t in jobs])
                self.assertEqual((d.label, d.evidence), gold_label(jobs))
        self.assertEqual(trace(cases[-1]).job, 1)

    def test_q3_only_overrides_deciding_job(self):
        rules = [({"id": "q3", "label": "dependency"}, re.compile("NoSuchMethodError"))]
        self.assertEqual(apply_q3(Decision("compile", job=0), ["javac", "NoSuchMethodError"], rules).label, "compile")
        self.assertEqual(apply_q3(Decision("test", job=1), ["javac", "NoSuchMethodError"], rules).label, "dependency")
        for label in ("lint", "infra", "buildconfig", "flaky", "dependency"):
            self.assertEqual(apply_q3(Decision(label, job=0), ["NoSuchMethodError"], rules).label, label)
        self.assertEqual(apply_q3(Decision("?"), ["NoSuchMethodError"], rules).label, "dependency")

    def test_output_rejects_protected_and_existing_directories(self):
        for path in ("data/processed", "data/validate", "data/crawl_pr", "data/dataset", "data/human_labels", "src", "data/rule_eval"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                Output(path)
        with self.assertRaises(FileExistsError):
            Output("data/rule_eval/scope_r1_20261018.csv")

    def test_full_run_writes_only_inside_output(self):
        area = Path("data/rule_eval")
        area.mkdir(exist_ok=True, parents=True)
        with fixture_directory(area) as tmp:
            fixture = Path(tmp)
            log = fixture / "input.txt"
            log.write_text("There are test failures\nCaused by: java.lang.NoSuchMethodError: x.y", encoding="utf-8")
            proposed = fixture / "proposal.json"
            proposed.write_text(json.dumps({"rules": [{"id":"q3", "label":"dependency", "regex":"Caused by: java.lang.NoSuchMethodError", "layer":"q3_override"}]}), encoding="utf-8")
            before = {p.name:p.read_bytes() for p in fixture.iterdir() if p.is_file()}
            row = {"repo":"fixture/repo", "run_id":"1", "root":"data/crawl_pr"}
            run = {"id":1,"head_sha":"abc","event":"push","name":"Build","conclusion":"failure"}
            job = {"id":1,"name":"test","conclusion":"failure"}
            output = fixture / "audit"
            real_open, real_io_open = builtins.open, io.open

            def checked_open(original):
                def check(path, mode="r", *args, **kwargs):
                    if isinstance(path, (str, Path)) and any(c in mode for c in "wax+"):
                        self.assertTrue(Path(path).resolve().is_relative_to(output.resolve()), f"Write outside audit: {path}")
                    return original(path, mode, *args, **kwargs)
                return check

            with patch("project3.pipeline.rule_eval.iter_scope", return_value=iter([(row,run,[job],[(job,log)],[])])), patch("project3.pipeline.rule_eval.human_references", return_value={}), patch("builtins.open", side_effect=checked_open(real_open)), patch("io.open", side_effect=checked_open(real_io_open)):
                main(Path("data/rule_eval/scope_r1_20261018.csv"), proposed, output)
            after = {p.name:p.read_bytes() for p in fixture.iterdir() if p.is_file()}
            self.assertEqual(before, after)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["parity_errors"], 0)
            self.assertEqual(summary["run_matrix"]["baseline_to_q3|test|dependency"], 1)
            writer = object.__new__(Output)
            writer.root = output.resolve()
            with self.assertRaises(ValueError):
                writer.path("../input.txt")
            self.assertTrue((output / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
