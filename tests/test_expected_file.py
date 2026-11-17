"""Integridade dos valores de referência (independente de qualquer execução)."""

from __future__ import annotations

import json
import unittest

import support

from alucinacoes.constants import HALLUCINATION_TYPES
from alucinacoes.metrics import TABLE_KEY_FIELDS

EXPECTED_PATH = support.REPO_ROOT / "expected" / "metrics.json"
TABLE8_STATES = ("functional_only_n", "static_only_n", "both_n", "none_n", "inconclusive_n")


class ExpectedFileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
        cls.metrics = cls.payload["metrics"]
        cls.tables = cls.metrics["tables"]

    def test_estrutura_minima(self) -> None:
        self.assertEqual(self.payload["schema"], "expected-metrics/1")
        self.assertEqual(self.payload["scope"], "full_dataset")
        self.assertIn("counts", self.metrics)
        self.assertIn("bootstrap", self.payload)

    def test_tabelas_conhecidas_e_chaves_unicas(self) -> None:
        unknown = set(self.tables) - set(TABLE_KEY_FIELDS)
        self.assertEqual(unknown, set())
        for name, rows in self.tables.items():
            keys = [tuple(row.get(field) for field in TABLE_KEY_FIELDS[name]) for row in rows]
            self.assertEqual(len(keys), len(set(keys)), f"chave repetida em {name}")
            for key in keys:
                self.assertNotIn(None, key, f"chave incompleta em {name}")

    def test_tabela_8_soma_estados_por_linha_e_total(self) -> None:
        rows = self.tables["gate_states_by_model_benchmark"]
        for row in rows:
            total = sum(row[field] for field in TABLE8_STATES)
            self.assertEqual(total, row["total_n"], row)
        totals = [row for row in rows if row["model"] == "TOTAL"]
        self.assertEqual(len(totals), 1)
        total_row = totals[0]
        counts = self.metrics["counts"]
        self.assertEqual(
            total_row["functional_only_n"], counts["gate_functional_only"]
        )
        self.assertEqual(total_row["static_only_n"], counts["gate_static_only"])
        self.assertEqual(total_row["both_n"], counts["gate_both"])
        self.assertEqual(total_row["none_n"], counts["gate_none"])
        self.assertEqual(total_row["inconclusive_n"], counts["gate_inconclusive"])
        self.assertEqual(total_row["total_n"], counts["annotated_rows"])

    def test_agregados_por_modelo_e_benchmark_sao_somas_da_tabela_8(self) -> None:
        rows = self.tables["gate_states_by_model_benchmark"]
        for field in ("model", "benchmark"):
            groups: dict[str, list[int]] = {}
            for row in rows:
                if row["model"] == "TOTAL":
                    continue
                groups.setdefault(row[field], ([0] * len(TABLE8_STATES)))
                for index, state in enumerate(TABLE8_STATES):
                    groups[row[field]][index] += row[state]
            table_name = (
                "gate_states_by_model" if field == "model" else "gate_states_by_benchmark"
            )
            for expected_row in self.tables[table_name]:
                key = expected_row[field]
                self.assertIn(key, groups)
                for index, state in enumerate(TABLE8_STATES):
                    self.assertEqual(
                        expected_row[state],
                        groups[key][index],
                        f"{table_name}[{key}].{state}",
                    )

    def test_composicoes_e_categorias_fecham(self) -> None:
        counts = self.metrics["counts"]
        types = self.tables["type_composition_silent"]
        annotated_rows = [row for row in types if row["type"] not in (
            "TOTAL (associações de tipo)",
            "Implementações únicas",
        )]
        self.assertEqual(
            sum(row["annotated_n"] for row in annotated_rows),
            counts["type_associations"],
        )
        self.assertEqual(
            sum(row["silent_n"] for row in annotated_rows),
            counts["silent_type_associations"],
        )
        categories = self.tables["categories_summary"]
        self.assertEqual(
            sum(row["annotated_n"] for row in categories if row["category_code"] != "TOTAL"),
            counts["category_associations"],
        )
        self.assertEqual(
            sum(row["silent_n"] for row in categories if row["category_code"] != "TOTAL"),
            counts["silent_category_associations"],
        )

    def test_estados_de_gate_somam_cerca_de_100_por_cento(self) -> None:
        for row in self.tables["gate_states_by_type"]:
            total = sum(row[f"{prefix}_pct"] for prefix in (
                "functional_only",
                "static_only",
                "both",
                "none",
                "inconclusive",
            ))
            self.assertLessEqual(abs(total - 100.0), 0.5, row["type"])

    def test_taxonomia_completa_sem_excluded_desc(self) -> None:
        rows = {
            row["type"]: row
            for row in self.tables["type_composition_silent"]
            if row["type"] not in ("TOTAL (associações de tipo)", "Implementações únicas")
        }
        self.assertEqual(set(rows), set(HALLUCINATION_TYPES))
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows["Common Sense"]["annotated_n"], 3)
        self.assertEqual(rows["Inconsistent Libraries"]["annotated_n"], 2)
        self.assertEqual(rows["Common Sense"]["silent_n"], 0)
        self.assertEqual(rows["Inconsistent Libraries"]["silent_n"], 0)

    def test_contadores_de_sobreposicao_conferem(self) -> None:
        counts = self.metrics["counts"]
        self.assertEqual(counts["multi_type_implementations"], 53)
        self.assertEqual(counts["multi_category_implementations"], 47)
        self.assertEqual(counts["same_category_collapse_pairs"], 6)
        self.assertEqual(
            counts["category_associations"],
            counts["type_associations"] - counts["same_category_collapse_pairs"],
        )
        self.assertGreaterEqual(counts["multi_type_implementations"], 1)

    def test_maximo_de_issues_e_o_das_anotadas(self) -> None:
        # 14 é o máximo das 1.090 anotadas parseadas (Figura 4 do manuscrito);
        # o máximo do corpus é exposto nas métricas, não neste gabarito.
        self.assertEqual(self.metrics["parse_histogram"]["max"], 14)

    def test_histograma_e_bootstrap_batem_com_contadores(self) -> None:
        histogram = self.metrics["parse_histogram"]
        self.assertEqual(sum(histogram["counts"]), histogram["total"])
        self.assertEqual(
            histogram["total"], self.metrics["counts"]["annotated_parsed"]
        )
        bootstrap = self.payload["bootstrap"]
        self.assertEqual(bootstrap["clusters"], self.metrics["counts"]["task_clusters"])
        self.assertEqual(bootstrap["silent"], self.metrics["counts"]["silent_implementations"])
        self.assertEqual(bootstrap["total"], self.metrics["counts"]["annotated_rows"])
        self.assertEqual(bootstrap["replicas"], 200000)
        self.assertEqual(bootstrap["seed"], 20261115)


if __name__ == "__main__":
    unittest.main()
