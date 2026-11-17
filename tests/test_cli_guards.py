"""Guardas de caminho das CLIs: nenhuma saída pode sobrescrever insumo ou gabarito."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

import support

from alucinacoes.manifest import sha256_file


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        name, support.REPO_ROOT / "scripts" / filename
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extract_cli = _load("extract_observations_cli", "extract_observations.py")
analyze_cli = _load("analyze_observations_cli", "analyze_observations.py")


def _run(module, arguments: list[str]) -> tuple[int, str]:
    stderr = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
        code = module.main(arguments)
    return code, stderr.getvalue()


class ExtractPathGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.artifacts = support.write_artifacts(
            self.root / "artifacts",
            support.default_metadata(),
            [],
            support.default_log(),
        )

    def test_recusa_saida_sobre_metadata(self) -> None:
        metadata = self.artifacts / "metadata.jsonl"
        before = sha256_file(metadata)
        code, stderr = _run(
            extract_cli,
            [
                "--artifacts",
                str(self.artifacts),
                "--output",
                str(metadata),
                "--manifest",
                str(self.root / "manifest.json"),
            ],
        )
        self.assertEqual(code, 2)
        self.assertIn("sobrescreveria", stderr)
        self.assertEqual(sha256_file(metadata), before)

    def test_recusa_saida_dentro_do_diretorio_de_artefatos(self) -> None:
        code, stderr = _run(
            extract_cli,
            [
                "--artifacts",
                str(self.artifacts),
                "--output",
                str(self.artifacts / "observations.jsonl"),
                "--manifest",
                str(self.root / "manifest.json"),
            ],
        )
        self.assertEqual(code, 2)
        self.assertIn("somente leitura", stderr)
        self.assertFalse((self.artifacts / "observations.jsonl").exists())

    def test_recusa_output_e_manifest_no_mesmo_arquivo(self) -> None:
        target = self.root / "saida.jsonl"
        code, stderr = _run(
            extract_cli,
            [
                "--artifacts",
                str(self.artifacts),
                "--output",
                str(target),
                "--manifest",
                str(target),
            ],
        )
        self.assertEqual(code, 2)
        self.assertIn("mesmo arquivo", stderr)
        self.assertFalse(target.exists())


class AnalyzePathGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.input = support.write_observations(
            self.root / "obs.jsonl",
            [
                support.observation_payload(
                    row_id=1, task_id="t1", types=["Algorithm"]
                )
            ],
        )

    def test_recusa_output_sobre_gabarito(self) -> None:
        expected = self.root / "gabarito" / "metrics.json"
        expected.parent.mkdir()
        expected.write_text(json.dumps({"schema": "expected-metrics/1"}), "utf-8")
        before = sha256_file(expected)
        code, stderr = _run(
            analyze_cli,
            [
                "--input",
                str(self.input),
                "--output",
                str(expected.parent),
                "--expected",
                str(expected),
            ],
        )
        self.assertEqual(code, 2)
        self.assertIn("metrics.json", stderr)
        self.assertEqual(sha256_file(expected), before)
        self.assertFalse((expected.parent / "gate_cross_corpus.csv").exists())

    def test_recusa_output_sobre_entrada(self) -> None:
        code, stderr = _run(
            analyze_cli,
            [
                "--input",
                str(self.input),
                "--output",
                str(self.input),
                "--skip-expected",
            ],
        )
        self.assertEqual(code, 2)
        self.assertIn("--output não é diretório", stderr)

    def test_nao_toca_no_gabarito_do_repositorio(self) -> None:
        expected = support.REPO_ROOT / "expected" / "metrics.json"
        before = sha256_file(expected)
        _run(
            analyze_cli,
            [
                "--input",
                str(self.input),
                "--output",
                str(self.root / "saida"),
                "--skip-expected",
            ],
        )
        self.assertEqual(sha256_file(expected), before)


class AnalyzeExpectedGateTest(unittest.TestCase):
    """O gabarito é validado e comparado antes de qualquer escrita."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.input = support.write_observations(
            self.root / "obs.jsonl",
            [
                support.observation_payload(
                    row_id=1, task_id="t1", types=["Algorithm"]
                )
            ],
        )
        self.output = self.root / "saida"

    def _expected_variant(self, *, mutate=None, scope: str = "unverified") -> Path:
        payload = json.loads(
            (support.REPO_ROOT / "expected" / "metrics.json").read_text(
                encoding="utf-8"
            )
        )
        payload["scope"] = scope
        if mutate is not None:
            mutate(payload)
        path = self.root / "expected.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _assert_nada_escrito(self) -> None:
        self.assertFalse(self.output.exists())

    def test_gabarito_vazio_e_recusado_sem_escrever(self) -> None:
        expected = self.root / "vazio.json"
        expected.write_text("{}", encoding="utf-8")
        code, stderr = _run(
            analyze_cli,
            [
                "--input",
                str(self.input),
                "--output",
                str(self.output),
                "--expected",
                str(expected),
            ],
        )
        self.assertEqual(code, 2)
        self.assertIn("gabarito inválido", stderr)
        self._assert_nada_escrito()

    def test_gabarito_ilegivel_e_recusado_sem_escrever(self) -> None:
        expected = self.root / "quebrado.json"
        expected.write_text("{ nao é json", encoding="utf-8")
        code, stderr = _run(
            analyze_cli,
            [
                "--input",
                str(self.input),
                "--output",
                str(self.output),
                "--expected",
                str(expected),
            ],
        )
        self.assertEqual(code, 2)
        self.assertIn("ilegível", stderr)
        self._assert_nada_escrito()

    def test_divergencia_de_contador_nao_deixa_saida(self) -> None:
        def mutate(payload: dict) -> None:
            payload["metrics"]["counts"]["gate_none"] += 1

        code, stderr = _run(
            analyze_cli,
            [
                "--input",
                str(self.input),
                "--output",
                str(self.output),
                "--expected",
                str(self._expected_variant(mutate=mutate)),
            ],
        )
        self.assertEqual(code, 1)
        self.assertIn("gate_none", stderr)
        self._assert_nada_escrito()

    def test_escopo_divergente_nao_deixa_saida(self) -> None:
        code, stderr = _run(
            analyze_cli,
            [
                "--input",
                str(self.input),
                "--output",
                str(self.output),
                "--expected",
                str(self._expected_variant(scope="full_dataset")),
            ],
        )
        self.assertEqual(code, 2)
        self.assertIn("escopo", stderr)
        self._assert_nada_escrito()


if __name__ == "__main__":
    unittest.main()
