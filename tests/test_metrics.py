"""Métricas: definições de estado, denominadores, dedup e histograma."""

from __future__ import annotations

import unittest

import support

import json

from alucinacoes.metrics import (
    MetricMismatch,
    compute_metrics,
    percent,
    validate_expected,
    verify_expected,
)


def fixture_observations():
    return [
        support.make_observation(
            row_id=1,
            task_id="t1",
            dataset="CEJava",
            model="gpt-4",
            functional_pass=True,
            types=["Behavior Conflicting", "Data Conflicting"],
        ),
        support.make_observation(
            row_id=2,
            task_id="t2",
            dataset="CEJava",
            model="codellama-7b",
            functional_pass=True,
            issue_count=2,
            types=["Library/Project"],
        ),
        support.make_observation(
            row_id=3,
            task_id="t3",
            dataset="CEPython",
            model="deepseek-r1",
            functional_pass=False,
            types=["Undefined Variables"],
        ),
        support.make_observation(
            row_id=4,
            task_id="t4",
            dataset="CEPython",
            model="deepseek-coder-1.3b",
            functional_pass=False,
            issue_count=1,
            types=["Algorithm"],
        ),
        support.make_observation(
            row_id=5,
            task_id="t5",
            dataset="HumanEval",
            model="gpt-4",
            functional_pass=False,
            static_parse_status="parse_failed",
            types=["Algorithm"],
        ),
        support.make_observation(
            row_id=6,
            task_id="t6",
            dataset="HumanEval",
            model="codellama-7b",
            functional_pass=True,
            static_parse_status="parse_failed",
            types=["Algorithm"],
        ),
        support.make_observation(
            row_id=7,
            task_id="t7",
            dataset="CEJava",
            model="gpt-4",
            functional_pass=True,
        ),
        support.make_observation(
            row_id=8,
            task_id="t8",
            dataset="CEPython",
            model="gpt-4",
            functional_pass=False,
            types=["Fragmented Logics"],
        ),
        support.make_observation(
            row_id=9,
            task_id="t9",
            dataset="CEJava",
            model="deepseek-r1",
            functional_pass=False,
            static_parse_status="parse_failed",
            types=["Data Conflicting"],
        ),
    ]


class PercentTest(unittest.TestCase):
    def test_arredondamento_half_up_com_uma_casa(self) -> None:
        self.assertEqual(percent(711, 1090), 65.2)
        self.assertEqual(percent(470, 1181), 39.8)
        self.assertEqual(percent(1, 16), 6.3)
        self.assertEqual(percent(1, 800), 0.1)
        self.assertEqual(percent(25, 1134), 2.2)

    def test_denominador_nulo_levanta(self) -> None:
        with self.assertRaises(ValueError):
            percent(0, 0)


class ComputeMetricsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metrics = compute_metrics(fixture_observations())
        cls.tables = cls.metrics["tables"]

    def test_cinco_estados_e_denominador_anotado(self) -> None:
        counts = self.metrics["counts"]
        self.assertEqual(counts["annotated_rows"], 8)
        self.assertEqual(counts["gate_none"], 1)
        self.assertEqual(counts["gate_static_only"], 1)
        self.assertEqual(counts["gate_functional_only"], 2)
        self.assertEqual(counts["gate_both"], 1)
        self.assertEqual(counts["gate_inconclusive"], 3)
        states = self.metrics["gate_states"]
        self.assertEqual(states["none"]["pct_of_annotated"], 12.5)
        self.assertEqual(states["inconclusive"]["pct_of_annotated"], 37.5)

    def test_contagens_de_anotacao_tipo_e_categoria(self) -> None:
        counts = self.metrics["counts"]
        self.assertEqual(counts["annotations"], 9)
        self.assertEqual(counts["type_associations"], 9)
        self.assertEqual(counts["category_associations"], 8)
        self.assertEqual(counts["task_clusters"], 8)

    def test_contagens_de_sobreposicao_e_maximo_de_issues(self) -> None:
        counts = self.metrics["counts"]
        self.assertEqual(counts["multi_type_implementations"], 1)
        self.assertEqual(counts["multi_category_implementations"], 0)
        self.assertEqual(counts["same_category_collapse_pairs"], 1)
        self.assertEqual(counts["max_issues_per_parsed_annotated"], 2)
        self.assertEqual(counts["max_issues_per_parsed_corpus"], 2)

    def test_categoria_deduplica_na_mesma_implementacao(self) -> None:
        categories = {
            row["category_code"]: row for row in self.tables["categories_summary"]
        }
        self.assertEqual(categories["R"]["annotated_n"], 2)
        self.assertEqual(categories["C"]["annotated_n"], 2)
        self.assertEqual(categories["K"]["annotated_n"], 4)
        self.assertEqual(categories["R"]["silent_n"], 1)
        self.assertEqual(categories["TOTAL"]["annotated_n"], 8)
        self.assertEqual(categories["TOTAL"]["silent_n"], 1)

    def test_sem_issue_usa_denominador_parseado(self) -> None:
        rows = {row["type"]: row for row in self.tables["types_static_summary"]}
        data_conflicting = rows["Data Conflicting"]
        self.assertEqual(data_conflicting["annotated_n"], 2)
        self.assertEqual(data_conflicting["parsed_n"], 1)
        self.assertEqual(data_conflicting["without_issue_n"], 1)
        self.assertEqual(data_conflicting["without_issue_pct_of_parsed"], 100.0)
        self.assertEqual(data_conflicting["without_issue_pct_of_annotated"], 50.0)
        self.assertEqual(data_conflicting["reproved_pct_of_annotated"], 50.0)
        self.assertEqual(data_conflicting["none_n"], 1)
        algorithm = rows["Algorithm"]
        self.assertEqual(algorithm["parsed_n"], 1)
        self.assertEqual(algorithm["reproved_pct_of_annotated"], 66.7)

    def test_cruzamento_corpus_e_anotado(self) -> None:
        rows = {
            (row["population"], row["stratum"]): row
            for row in self.tables["gate_cross_corpus"]
        }
        pass_row = rows[("annotated", "functional_pass")]
        self.assertEqual(
            (pass_row["with_issues"], pass_row["without_issues"], pass_row["inconclusive"]),
            (1, 1, 1),
        )
        self.assertEqual(pass_row["pct_with_issues_of_total"], 33.3)
        self.assertEqual(pass_row["pct_with_issues_of_parsed"], 50.0)
        total_row = rows[("annotated", "total")]
        self.assertEqual(total_row["pct_with_issues_of_total"], 25.0)
        self.assertEqual(total_row["pct_with_issues_of_parsed"], 40.0)
        corpus_pass = rows[("corpus", "functional_pass")]
        self.assertEqual(corpus_pass["without_issues"], 2)
        self.assertEqual(corpus_pass["pct_with_issues_of_parsed"], 33.3)

    def test_histograma_com_faixas_do_manuscrito(self) -> None:
        histogram = self.metrics["parse_histogram"]
        self.assertEqual(histogram["labels"], ["0", "1", "2", "3-4", "5+"])
        self.assertEqual(histogram["counts"], [3, 1, 1, 0, 0])
        self.assertEqual(histogram["total"], 5)
        self.assertEqual(histogram["max"], 2)
        rows = {row["bin_label"]: row for row in self.tables["parse_histogram"]}
        self.assertEqual(rows["0"]["implementations_n"], 3)
        self.assertEqual(rows["0"]["pct_of_parsed"], 60.0)
        self.assertIsNone(rows["5+"]["issues_max"])

    def test_coocorrencia_e_silenciosas(self) -> None:
        rows = {
            (row["type_a"], row["type_b"]): row
            for row in self.tables["type_cooccurrence"]
        }
        pair = rows[("Behavior Conflicting", "Data Conflicting")]
        self.assertEqual(pair["annotated_n"], 1)
        self.assertEqual(pair["silent_n"], 1)
        self.assertEqual(self.metrics["cooccurrence"]["max_annotated_pair"]["annotated_n"], 1)
        counts = self.metrics["counts"]
        self.assertEqual(counts["silent_implementations"], 1)
        self.assertEqual(counts["silent_type_associations"], 2)
        self.assertEqual(counts["silent_category_associations"], 1)
        self.assertEqual(counts["silent_top4_type_associations"], 2)
        self.assertTrue(
            any(
                "Common Sense" in row
                for row in self.metrics["cooccurrence"]["types_without_annotated_cooccurrence"]
            )
        )

    def test_tabela_por_tipo_usa_implementacoes_anotadas(self) -> None:
        rows = {row["type"]: row for row in self.tables["gate_states_by_type"]}
        data_conflicting = rows["Data Conflicting"]
        self.assertEqual(data_conflicting["total_n"], 2)
        self.assertEqual(data_conflicting["none_n"], 1)
        self.assertEqual(data_conflicting["inconclusive_n"], 1)
        self.assertEqual(data_conflicting["none_pct"], 50.0)

    def test_prevalencia_por_benchmark_e_modelo(self) -> None:
        rows = {
            (row["benchmark"], row["model"]): row
            for row in self.tables["prevalence_by_benchmark_model"]
        }
        cejava_gpt4 = rows[("CEJava", "gpt-4")]
        self.assertEqual(cejava_gpt4["implementations_n"], 2)
        self.assertEqual(cejava_gpt4["annotated_n"], 1)
        self.assertEqual(cejava_gpt4["annotated_pct"], 50.0)


class NoExcludedDescTest(unittest.TestCase):
    def test_tipos_de_excluded_desc_nao_sao_filtrados(self) -> None:
        observations = [
            support.make_observation(
                row_id=1,
                task_id="t1",
                dataset="CEJava",
                types=["Common Sense", "Inconsistent Libraries"],
            ),
            support.make_observation(
                row_id=2, task_id="t2", dataset="CEJava", types=["Common Sense"]
            ),
        ]
        metrics = compute_metrics(observations)
        rows = {row["type"]: row for row in metrics["tables"]["type_composition_silent"]}
        self.assertEqual(rows["Common Sense"]["annotated_n"], 2)
        self.assertEqual(rows["Common Sense"]["silent_n"], 2)
        self.assertEqual(rows["Inconsistent Libraries"]["annotated_n"], 1)
        self.assertEqual(rows["Inconsistent Libraries"]["silent_n"], 1)
        # t1 = K + C (duas categorias), t2 = K; sem exclusão de tipos
        self.assertEqual(metrics["counts"]["category_associations"], 3)
        categories = {
            row["category_code"]: row for row in metrics["tables"]["categories_summary"]
        }
        self.assertEqual(categories["K"]["annotated_n"], 2)
        self.assertEqual(categories["K"]["silent_n"], 2)
        self.assertEqual(categories["C"]["annotated_n"], 1)
        self.assertEqual(categories["C"]["silent_n"], 1)


class ValidateExpectedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.valid = json.loads(
            (support.REPO_ROOT / "expected" / "metrics.json").read_text(
                encoding="utf-8"
            )
        )

    def test_aceita_os_valores_de_referencia(self) -> None:
        validate_expected(self.valid)

    def test_recusa_arquivo_vazio(self) -> None:
        for payload in ({}, [], None, "texto"):
            with self.subTest(payload=payload):
                with self.assertRaises(MetricMismatch):
                    validate_expected(payload)

    def test_recusa_schema_ou_escopo_ausente(self) -> None:
        payload = json.loads(json.dumps(self.valid))
        del payload["schema"]
        with self.assertRaises(MetricMismatch):
            validate_expected(payload)
        payload = json.loads(json.dumps(self.valid))
        payload["schema"] = "outro/1"
        with self.assertRaises(MetricMismatch):
            validate_expected(payload)
        payload = json.loads(json.dumps(self.valid))
        payload["scope"] = ""
        with self.assertRaises(MetricMismatch):
            validate_expected(payload)

    def test_recusa_secoes_vazias(self) -> None:
        for section in ("counts", "gate_states", "tables"):
            payload = json.loads(json.dumps(self.valid))
            payload["metrics"][section] = {}
            with self.subTest(section=section):
                with self.assertRaises(MetricMismatch):
                    validate_expected(payload)
        payload = json.loads(json.dumps(self.valid))
        del payload["metrics"]
        with self.assertRaises(MetricMismatch):
            validate_expected(payload)

    def test_recusa_tabela_ausente_ou_vazia(self) -> None:
        payload = json.loads(json.dumps(self.valid))
        del payload["metrics"]["tables"]["types_static_summary"]
        with self.assertRaises(MetricMismatch):
            validate_expected(payload)
        payload = json.loads(json.dumps(self.valid))
        payload["metrics"]["tables"]["gate_cross_corpus"] = []
        with self.assertRaises(MetricMismatch):
            validate_expected(payload)

    def test_recusa_contador_obrigatorio_invalido(self) -> None:
        payload = json.loads(json.dumps(self.valid))
        payload["metrics"]["counts"]["gate_none"] = "2"
        with self.assertRaises(MetricMismatch):
            validate_expected(payload)
        payload = json.loads(json.dumps(self.valid))
        del payload["metrics"]["counts"]["task_clusters"]
        with self.assertRaises(MetricMismatch):
            validate_expected(payload)

    def test_recusa_estado_de_gate_faltante(self) -> None:
        payload = json.loads(json.dumps(self.valid))
        del payload["metrics"]["gate_states"]["none"]
        with self.assertRaises(MetricMismatch):
            validate_expected(payload)


class VerifyExpectedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.metrics = compute_metrics(fixture_observations())

    def test_aceita_gabarito_coerente(self) -> None:
        expected = {
            "counts": {"annotated_rows": 8, "gate_none": 1},
            "parse_histogram": {"counts": [3, 1, 1, 0, 0], "max": 2},
            "gate_states": {"none": {"n": 1, "pct_of_annotated": 12.5}},
            "tables": {
                "annotations_by_model": [
                    {"model": "gpt-4", "annotated_n": 3, "silent_n": 1}
                ]
            },
        }
        verify_expected(self.metrics, expected)

    def test_recusa_divergencia_numerica(self) -> None:
        expected = {"counts": {"gate_none": 2}}
        with self.assertRaises(MetricMismatch) as caught:
            verify_expected(self.metrics, expected)
        self.assertIn("gate_none", str(caught.exception))

    def test_recusa_linha_ausente_e_tabela_desconhecida(self) -> None:
        with self.assertRaises(MetricMismatch):
            verify_expected(
                self.metrics,
                {"tables": {"annotations_by_model": [{"model": "nao-existe"}]}},
            )
        with self.assertRaises(MetricMismatch):
            verify_expected(self.metrics, {"tables": {"tabela_inventada": []}})

    def test_tolera_diferenca_de_arredondamento(self) -> None:
        verify_expected(self.metrics, {"gate_states": {"none": {"pct_of_annotated": 12.53}}})


if __name__ == "__main__":
    unittest.main()
