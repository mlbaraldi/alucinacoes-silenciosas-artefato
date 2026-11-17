"""Extração: observações derivadas, manifesto e recusas fail-closed."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import support

from alucinacoes.constants import FULL_DATASET_INPUTS
from alucinacoes.extraction import (
    ExtractionError,
    extract_observations,
    write_extraction,
)
from alucinacoes.manifest import resolve_scope
from alucinacoes.observations import load_observations


class ExtractionHappyPathTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.artifacts = support.write_artifacts(
            self.root / "artifacts",
            support.default_metadata(),
            [
                support.issue("i1", support.default_metadata()[2]),
                support.issue("i2", support.default_metadata()[2], sonar_type="BUG"),
            ],
            support.default_log(),
        )
        self.result = extract_observations(self.artifacts)

    def test_preserva_ordem_e_row_id_do_metadata(self) -> None:
        self.assertEqual([obs.row_id for obs in self.result.observations], [1, 2, 3, 4])
        self.assertEqual(
            [obs.task_id for obs in self.result.observations], ["t1", "t1", "t2", "t3"]
        )

    def test_normaliza_desfechos_e_estado_de_parsing(self) -> None:
        first, second, third, fourth = self.result.observations
        self.assertIs(first.functional_pass, True)
        self.assertIs(second.functional_pass, True)
        self.assertIs(third.functional_pass, False)
        self.assertIs(fourth.functional_pass, False)
        self.assertEqual(fourth.static_parse_status, "parse_failed")
        self.assertEqual(third.static_parse_status, "parsed")

    def test_contagens_de_issue_por_implementacao(self) -> None:
        self.assertEqual(
            [obs.issue_count for obs in self.result.observations], [0, 0, 2, 0]
        )

    def test_tipos_deduplicados_e_contagens_de_anotacao(self) -> None:
        first = self.result.observations[0]
        self.assertEqual(first.types, ("Algorithm", "Behavior Conflicting"))
        self.assertEqual(first.categories, ("K", "R"))
        self.assertEqual(first.annotation_count, 3)
        self.assertEqual(
            first.type_annotations,
            {"Algorithm": 1, "Behavior Conflicting": 2},
        )
        self.assertTrue(first.annotated)
        self.assertFalse(self.result.observations[2].annotated)

    def test_sumario_do_corpus(self) -> None:
        self.assertEqual(
            self.result.summary,
            {
                "rows": 4,
                "annotated_rows": 3,
                "task_clusters": 2,
                "annotations": 5,
                "type_associations": 4,
                "category_associations": 4,
                "multi_type_implementations": 1,
                "multi_category_implementations": 1,
                "max_issues_per_parsed_annotated": 0,
                "max_issues_per_parsed_corpus": 2,
                "issues": 2,
                "parse_failures": 1,
            },
        )
        # row 1 tem Behavior (R) + Algorithm (K): duas categorias, sem colapso
        self.assertEqual(
            self.result.manifest["counts"]["same_category_collapse_pairs"], 0
        )
        # a única implementação anotada com issues é a row 3? não: row 3 não é
        # anotada, por isso o máximo anotado é 0 e o do corpus é 2
        self.assertEqual(
            self.result.manifest["counts"]["max_issues_per_parsed_annotated"], 0
        )

    def test_manifesto_registra_hashes_sem_caminho_absoluto(self) -> None:
        manifest = self.result.manifest
        self.assertEqual(manifest["schema"], "manifest/1")
        self.assertEqual(manifest["observation_schema"], "observations/1")
        self.assertEqual(manifest["scope"], "unverified")
        self.assertIn("não afirma", manifest["scope_basis"])
        self.assertEqual(
            [item["file"] for item in manifest["inputs"]],
            ["metadata.jsonl", "mapped_issues.json", "sonar_scan.log"],
        )
        for item in manifest["inputs"]:
            self.assertEqual(len(item["sha256"]), 64)
            self.assertGreater(item["size_bytes"], 0)
        serialized = json.dumps(manifest, ensure_ascii=False)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("/home/", serialized)
        self.assertNotIn(str(self.artifacts), serialized)

    def test_escrita_e_releitura_do_jsonl(self) -> None:
        output = self.root / "out" / "observations.jsonl"
        manifest_path = self.root / "out" / "manifest.json"
        manifest = write_extraction(
            self.result, output_path=output, manifest_path=manifest_path
        )
        self.assertEqual(manifest["outputs"][0]["records"], 4)
        self.assertEqual(len(manifest["outputs"][0]["sha256"]), 64)
        reloaded = load_observations(output)
        self.assertEqual(
            [obs.as_dict() for obs in reloaded],
            [obs.as_dict() for obs in self.result.observations],
        )
        self.assertTrue(manifest_path.is_file())


class ExtractionFailClosedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _extract(self, metadata, issues=None, log=None):
        artifacts = support.write_artifacts(
            self.root / "artifacts",
            metadata,
            issues if issues is not None else [],
            log if log is not None else "INFO: sem falhas\n" + support.success_tail(),
        )
        return extract_observations(artifacts)

    def test_recusa_tipo_desconhecido(self) -> None:
        metadata = support.default_metadata()
        metadata[0]["code_labels"] = [support.label("Tipo Inventado")]
        with self.assertRaises(ExtractionError):
            self._extract(metadata)

    def test_recusa_anotacao_sem_tipo(self) -> None:
        metadata = support.default_metadata()
        metadata[0]["code_labels"] = [{"factors": ["x"]}]
        with self.assertRaises(ExtractionError):
            self._extract(metadata)

    def test_recusa_status_desconhecido(self) -> None:
        metadata = support.default_metadata()
        metadata[1]["evaluation_result"] = {"status": "error"}
        with self.assertRaises(ExtractionError):
            self._extract(metadata)

    def test_recusa_is_pass_nao_booleano(self) -> None:
        metadata = support.default_metadata()
        metadata[0]["evaluation_result"] = {"is_pass": "true"}
        with self.assertRaises(ExtractionError):
            self._extract(metadata)

    def test_recusa_row_number_duplicado(self) -> None:
        metadata = support.default_metadata()
        metadata[1]["row_number"] = 1
        with self.assertRaises(ExtractionError):
            self._extract(metadata)

    def test_recusa_row_number_fora_de_ordem(self) -> None:
        metadata = support.default_metadata()
        metadata[0]["row_number"], metadata[1]["row_number"] = 2, 1
        with self.assertRaises(ExtractionError):
            self._extract(metadata)

    def test_recusa_row_number_nao_denso(self) -> None:
        metadata = support.default_metadata()
        metadata[0]["row_number"] = 10
        with self.assertRaises(ExtractionError):
            self._extract(metadata)

    def test_recusa_source_file_duplicado(self) -> None:
        metadata = support.default_metadata()
        metadata[1]["source_file"] = metadata[0]["source_file"]
        with self.assertRaises(ExtractionError):
            self._extract(metadata)

    def test_recusa_source_file_absoluto(self) -> None:
        metadata = support.default_metadata()
        metadata[0]["source_file"] = "/home/user/src/a.py"
        with self.assertRaises(ExtractionError):
            self._extract(metadata)

    def test_recusa_extensao_incongruente_com_benchmark(self) -> None:
        metadata = support.default_metadata()
        metadata[0]["source_file"] = "src/HumanEval/gpt-4/0001_task.java"
        with self.assertRaises(ExtractionError):
            self._extract(metadata)

    def test_recusa_modelo_ou_dataset_desconhecido(self) -> None:
        metadata = support.default_metadata()
        metadata[0]["model"] = "llama-99"
        with self.assertRaises(ExtractionError):
            self._extract(metadata)
        metadata = support.default_metadata()
        metadata[0]["dataset"] = "CEGo"
        with self.assertRaises(ExtractionError):
            self._extract(metadata)

    def test_recusa_issue_de_fonte_inexistente(self) -> None:
        orphan = dict(support.default_metadata()[2])
        orphan["source_file"] = "src/CEJava/codellama-7b/9999_ghost.java"
        with self.assertRaises(ExtractionError):
            self._extract(
                support.default_metadata(), [support.issue("i1", orphan)]
            )

    def test_recusa_issue_com_metadados_divergentes(self) -> None:
        row = support.default_metadata()[2]
        for field, value in (("row_number", 99), ("model", "gpt-4"), ("dataset", "HumanEval")):
            with self.subTest(field=field):
                bad_issue = support.issue("i1", row)
                bad_issue[field] = value
                with self.assertRaises(ExtractionError):
                    self._extract(support.default_metadata(), [bad_issue])

    def test_recusa_issue_key_duplicada(self) -> None:
        row = support.default_metadata()[2]
        with self.assertRaises(ExtractionError):
            self._extract(
                support.default_metadata(),
                [support.issue("i1", row), support.issue("i1", row)],
            )

    def test_recusa_sonar_type_desconhecido(self) -> None:
        row = support.default_metadata()[2]
        with self.assertRaises(ExtractionError):
            self._extract(
                support.default_metadata(), [support.issue("i1", row, sonar_type="X")]
            )

    def test_recusa_fonte_com_parsing_falho_e_issue(self) -> None:
        row = support.default_metadata()[2]
        with self.assertRaises(ExtractionError):
            self._extract(
                support.default_metadata(),
                [support.issue("i1", row)],
                "ERROR: Unable to parse file: %s\n" % row["source_file"]
                + support.success_tail(),
            )

    def test_recusa_falha_de_parsing_fora_do_metadata(self) -> None:
        with self.assertRaises(ExtractionError):
            self._extract(
                support.default_metadata(),
                [],
                "ERROR: Unable to parse file: src/CEJava/x/0000_ghost.java\n"
                + support.success_tail(),
            )

    def test_recusa_log_com_caminho_absoluto(self) -> None:
        with self.assertRaises(ExtractionError):
            self._extract(
                support.default_metadata(),
                [],
                "ERROR: Unable to parse file: /usr/src/x.py\n"
                + support.success_tail(),
            )

    def test_escopo_nao_vem_do_nome_do_diretorio(self) -> None:
        metadata = support.default_metadata()
        artifacts = support.write_artifacts(
            self.root / "full_dataset" / "artifacts",
            metadata,
            [],
            support.default_log(),
        )
        result = extract_observations(artifacts)
        self.assertEqual(result.manifest["scope"], "unverified")
        self.assertIn("não afirma", result.manifest["scope_basis"])

    def test_escopo_full_dataset_so_com_os_tres_hashes_do_pin(self) -> None:
        scope, basis = resolve_scope(dict(FULL_DATASET_INPUTS))
        self.assertEqual(scope, "full_dataset")
        self.assertIn("pin", basis)
        mutated = dict(FULL_DATASET_INPUTS)
        mutated["metadata.jsonl"] = "0" * 64
        self.assertEqual(resolve_scope(mutated)[0], "unverified")
        self.assertEqual(resolve_scope({})[0], "unverified")

    def test_recusa_desfecho_funcional_ausente_ou_indeterminado(self) -> None:
        for evaluation in (None, {}, {"error": "compile error"}):
            with self.subTest(evaluation=evaluation):
                metadata = support.default_metadata()
                metadata[1]["evaluation_result"] = evaluation
                with self.assertRaises(ExtractionError):
                    self._extract(metadata)
        metadata = support.default_metadata()
        metadata[3]["evaluation_result"] = None  # linha com parsing falho
        with self.assertRaises(ExtractionError):
            self._extract(metadata)

    def test_recusa_log_sem_evidencia_de_sucesso(self) -> None:
        with self.assertRaises(ExtractionError) as caught:
            self._extract(
                support.default_metadata(), [], "INFO: Indexing files...\n"
            )
        self.assertIn("evidência", str(caught.exception))

    def test_allowlist_nao_projeta_conteudo_de_codigo(self) -> None:
        metadata = support.default_metadata()
        metadata[0]["conflict-content"] = "public class Vazamento { }"
        metadata[0]["evaluation_result"]["error_detail_message"] = (
            "ByteVector.java:347: error: cannot find symbol"
        )
        metadata[0]["project"] = "hasor-master"
        metadata[0]["code_labels"][0]["hallucination-type-other"] = (
            "代码一致性冲突-无法执行到的代码片段"
        )
        metadata[0]["code_labels"][0]["factors"] = ["Model-related Causes"]
        issues = []
        row_for_issue = support.default_metadata()[2]
        issue = support.issue("i1", row_for_issue)
        issue["message"] = 'Remove this useless assignment to "!unknown!".'
        issues.append(issue)

        result = self._extract(
            metadata, issues, "INFO: sem falhas\n" + support.success_tail()
        )
        serialized = json.dumps(
            [obs.as_dict() for obs in result.observations], ensure_ascii=False
        )
        for forbidden in (
            "Vazamento",
            "public class",
            "ByteVector",
            "cannot find symbol",
            "hasor-master",
            "代码一致性冲突",
            "Model-related Causes",
            "useless assignment",
            "conflict-content",
            "hallucination-type-other",
            "error_detail_message",
        ):
            self.assertNotIn(forbidden, serialized)
        ignored = result.manifest["inputs"][0]["fields_ignored"]
        self.assertIn("conflict-content", ignored)
        self.assertIn("project", ignored)
        self.assertEqual(
            result.manifest["inputs"][0]["fields_used"],
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

    def test_recusa_task_id_fora_do_padrao_opaco(self) -> None:
        for bad in ("tarefa com espaco", "task{1}", "a;b", "x" * 65, ""):
            with self.subTest(task_id=bad):
                metadata = support.default_metadata()
                metadata[0]["_id"] = bad
                with self.assertRaises(ExtractionError):
                    self._extract(metadata)

    def test_recusa_metadata_vazio(self) -> None:
        with self.assertRaises(ExtractionError):
            self._extract([])


if __name__ == "__main__":
    unittest.main()
