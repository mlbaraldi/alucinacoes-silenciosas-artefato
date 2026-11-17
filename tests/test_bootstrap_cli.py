"""CLI do bootstrap: gabarito obrigatório no modo completo e modo parcial explícito."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

import support

SCRIPT = support.REPO_ROOT / "scripts" / "bootstrap_silent_ci.py"
_spec = importlib.util.spec_from_file_location("bootstrap_silent_ci", SCRIPT)
assert _spec is not None and _spec.loader is not None
bootstrap_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bootstrap_cli)


def _observations(count: int, *, silent: int = 0) -> list[dict]:
    rows = []
    for index in range(count):
        rows.append(
            support.observation_payload(
                row_id=index + 1,
                task_id=f"t{index}",
                types=["Algorithm"],
                functional_pass=index < silent,
                static_parse_status="parsed" if index < silent else "parse_failed",
            )
        )
    return rows


def _run(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = bootstrap_cli.main(arguments)
    return code, stdout.getvalue(), stderr.getvalue()


class BootstrapCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.input = support.write_observations(
            self.root / "observations.jsonl", _observations(10, silent=10)
        )
        self.output = self.root / "bootstrap.json"

    def _write_expected(self, bootstrap: dict | None) -> Path:
        payload = {"schema": "expected-metrics/1", "scope": "full_dataset"}
        if bootstrap is not None:
            payload["bootstrap"] = bootstrap
        path = self.root / "expected.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_modo_completo_exige_gabarito(self) -> None:
        code, _, stderr = _run(
            [
                "--input",
                str(self.input),
                "--output",
                str(self.output),
                "--expected",
                str(self.root / "ausente.json"),
            ]
        )
        self.assertEqual(code, 2)
        self.assertIn("exige o gabarito", stderr)
        self.assertFalse(self.output.exists())

    def test_modo_completo_recusa_gabarito_sem_secao(self) -> None:
        expected = self._write_expected(None)
        code, _, stderr = _run(
            [
                "--input",
                str(self.input),
                "--output",
                str(self.output),
                "--expected",
                str(expected),
            ]
        )
        self.assertEqual(code, 2)
        self.assertIn("bootstrap", stderr)
        self.assertFalse(self.output.exists())

    def test_modo_completo_recusa_gabarito_incompativel(self) -> None:
        expected = self._write_expected(
            {"seed": 1, "replicas": 10, "clusters": 1, "silent": 1, "total": 1}
        )
        code, _, stderr = _run(
            [
                "--input",
                str(self.input),
                "--output",
                str(self.output),
                "--expected",
                str(expected),
            ]
        )
        self.assertEqual(code, 2)
        self.assertIn("incompatível", stderr)

    def test_modo_completo_verifica_e_registra(self) -> None:
        expected = self._write_expected(
            {
                "seed": 20261115,
                "replicas": 200000,
                "clusters": 10,
                "silent": 10,
                "total": 10,
                "ci_low_pct": 100.0,
                "ci_high_pct": 100.0,
            }
        )
        code, stdout, _ = _run(
            [
                "--input",
                str(self.input),
                "--output",
                str(self.output),
                "--expected",
                str(expected),
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("modo=completo", stdout)
        self.assertIn("expected: OK", stdout)
        document = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(document["mode"], "completo")
        self.assertTrue(document["inputs"]["expected"]["verified"])
        self.assertEqual(document["parameters"], {"seed": 20261115, "replicas": 200000})
        self.assertIn("--seed 20261115 --replicas 200000", document["command"])

    def test_modo_parcial_sem_gabarito_e_declarado(self) -> None:
        code, stdout, _ = _run(
            [
                "--input",
                str(self.input),
                "--output",
                str(self.output),
                "--expected",
                str(self.root / "ausente.json"),
                "--replicas",
                "25",
                "--seed",
                "7",
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("modo=parcial", stdout)
        self.assertIn("PARCIAL", stdout)
        self.assertIn("NÃO comparado", stdout)
        document = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(document["mode"], "parcial")
        self.assertFalse(document["inputs"]["expected"]["verified"])
        self.assertEqual(document["parameters"], {"seed": 7, "replicas": 25})
        self.assertIn("--seed 7 --replicas 25", document["command"])
        self.assertEqual(document["result"]["clusters"], 10)

    def test_modo_parcial_compara_quando_gabarito_combina(self) -> None:
        expected = self._write_expected(
            {
                "seed": 7,
                "replicas": 25,
                "clusters": 10,
                "silent": 10,
                "total": 10,
                "ci_low_pct": 100.0,
                "ci_high_pct": 100.0,
            }
        )
        code, stdout, _ = _run(
            [
                "--input",
                str(self.input),
                "--output",
                str(self.output),
                "--expected",
                str(expected),
                "--replicas",
                "25",
                "--seed",
                "7",
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("modo=parcial", stdout)
        self.assertIn("expected: OK", stdout)
        self.assertTrue(
            json.loads(self.output.read_text(encoding="utf-8"))["inputs"]["expected"][
                "verified"
            ]
        )

    def test_divergencia_do_gabarito_falha(self) -> None:
        expected = self._write_expected(
            {
                "seed": 20261115,
                "replicas": 200000,
                "clusters": 10,
                "silent": 9,
                "total": 10,
                "ci_low_pct": 100.0,
                "ci_high_pct": 100.0,
            }
        )
        code, _, stderr = _run(
            [
                "--input",
                str(self.input),
                "--output",
                str(self.output),
                "--expected",
                str(expected),
            ]
        )
        self.assertEqual(code, 1)
        self.assertIn("silent", stderr)

    def test_saida_nao_pode_sobrescrever_entrada(self) -> None:
        original = self.input.read_text(encoding="utf-8")
        code, _, stderr = _run(
            [
                "--input",
                str(self.input),
                "--output",
                str(self.input),
                "--replicas",
                "5",
            ]
        )
        self.assertEqual(code, 2)
        self.assertIn("sobrescreveria", stderr)
        self.assertEqual(self.input.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
