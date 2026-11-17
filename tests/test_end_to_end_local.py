"""Integração local com os artefatos reais (opcional).

Requer a variável de ambiente ``ALUCINACOES_ARTIFACTS_DIR`` apontando para o
diretório ``analysis/sonarqube/full_dataset/artifacts`` de origem. Fora desse
caso, os testes são ignorados: o artefato não depende de rede nem de dados
privados para a suíte principal.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

import support

from alucinacoes.bootstrap import run_bootstrap
from alucinacoes.extraction import extract_observations, write_extraction
from alucinacoes.metrics import compute_metrics
from alucinacoes.observations import load_observations

ARTIFACTS_ENV = "ALUCINACOES_ARTIFACTS_DIR"

EXIF_METADATA = "f9335b54afcf2f0d23c37b2c3dc1fe0f0bf34b1a5fa1d49fc84422cb5e73113b"
EXIF_ISSUES = "c050343ec432246ddfbf66d6cd9965f117634aa75eef9488be40b398fa290544"
EXIF_SCAN = "61667575081b6b56bf5435cceb41c7b633870738ade7aa14eb6fef5afb8975e4"


def _artifacts_dir() -> Path | None:
    value = os.environ.get(ARTIFACTS_ENV)
    if not value:
        return None
    path = Path(value)
    required = ("metadata.jsonl", "mapped_issues.json", "sonar_scan.log")
    if not all((path / name).is_file() for name in required):
        return None
    return path


@unittest.skipUnless(
    _artifacts_dir() is not None,
    f"defina {ARTIFACTS_ENV} para rodar a integração com os artefatos reais",
)
class RealArtifactsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.result = extract_observations(_artifacts_dir())
        cls.output = cls.root / "observations.jsonl"
        write_extraction(
            cls.result,
            output_path=cls.output,
            manifest_path=cls.root / "manifest.json",
        )
        cls.observations = load_observations(cls.output)
        cls.metrics = compute_metrics(cls.observations)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_contadores_do_gabarito(self) -> None:
        counts = self.metrics["counts"]
        self.assertEqual(counts["rows"], 3120)
        self.assertEqual(counts["annotated_rows"], 1134)
        self.assertEqual(counts["task_clusters"], 433)
        self.assertEqual(counts["annotations"], 1212)
        self.assertEqual(counts["type_associations"], 1187)
        self.assertEqual(counts["category_associations"], 1181)
        self.assertEqual(counts["gate_none"], 25)
        self.assertEqual(counts["silent_type_associations"], 26)
        self.assertEqual(counts["silent_top4_type_associations"], 22)
        self.assertEqual(self.metrics["parse_histogram"]["counts"], [711, 250, 66, 42, 21])

    def test_bootstrap_em_modo_reduzido_mantem_universo(self) -> None:
        result = run_bootstrap(self.observations, replicas=20, seed=20261115)
        self.assertEqual(result["clusters"], 433)
        self.assertEqual(result["silent"], 25)
        self.assertEqual(result["total"], 1134)

    def test_observacoes_nao_expoem_codigo_mensagem_ou_caminho(self) -> None:
        text = self.output.read_text(encoding="utf-8")
        forbidden = (
            "src/",
            "/home",
            "/tmp",
            "message",
            "prompt",
            "generation",
            "conflict-content",
            "hallucination-type-other",
            "public class",
            "System.arraycopy",
            "代码",
        )
        for token in forbidden:
            self.assertNotIn(token, text)
        fields = set(json.loads(text.splitlines()[0]))
        self.assertEqual(fields, set(support.observation_payload(row_id=1).keys()))

    def test_manifesto_declara_allowlist_e_pin_upstream(self) -> None:
        manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        metadata_input = next(
            item for item in manifest["inputs"] if item["role"] == "metadata"
        )
        self.assertEqual(
            metadata_input["fields_used"],
            [
                "row_number",
                "_id",
                "model",
                "dataset",
                "source_file",
                "code_labels",
                "evaluation_result",
            ],
        )
        self.assertEqual(
            set(metadata_input["fields_ignored"]),
            {"generation_line_offset", "index_within_model", "project"},
        )
        upstream = manifest["source_dataset"]["upstream"]
        self.assertEqual(
            upstream["revision"], "c15a328c90b2046c5751e16b79eb00ddbeace7b1"
        )
        self.assertEqual(
            upstream["result_sha256"],
            "b2f7d2087a6789c7dd89a7a22fb937083f1784f1df97a3a69595b74179c84bfc",
        )
        self.assertFalse(upstream["used_as_input"])
        self.assertEqual(manifest["scope"], "full_dataset")
        self.assertIn("pin", manifest["scope_basis"])
        recorded = {
            item["file"]: item["sha256"] for item in manifest["inputs"]
        }
        self.assertEqual(recorded["metadata.jsonl"], EXIF_METADATA)
        self.assertEqual(recorded["mapped_issues.json"], EXIF_ISSUES)
        self.assertEqual(recorded["sonar_scan.log"], EXIF_SCAN)

    def test_verify_offline_relata_verificacao_parcial(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "verify_offline_e2e", support.REPO_ROOT / "scripts" / "verify_offline.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            code = module.main(
                [
                    "--artifacts",
                    str(_artifacts_dir()),
                    "--workdir",
                    str(self.root / "verificacao"),
                    "--skip-bootstrap",
                ]
            )
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("PARCIAL", output)
        self.assertIn("bootstrap não executado", output)
        self.assertNotIn("verificação offline completa", output)

    def test_ordem_do_metadata_e_preservada(self) -> None:
        with (_artifacts_dir() / "metadata.jsonl").open(encoding="utf-8") as handle:
            expected_ids = [
                json.loads(line)["row_number"] for line in handle if line.strip()
            ]
        self.assertEqual([obs.row_id for obs in self.observations], expected_ids)


if __name__ == "__main__":
    unittest.main()
