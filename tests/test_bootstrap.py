"""Bootstrap agrupado: clusters, reprodutibilidade e quantil por piso."""

from __future__ import annotations

import random
import unittest

import support

from alucinacoes.bootstrap import (
    BootstrapError,
    build_clusters,
    run_bootstrap,
    verify_bootstrap,
)


def reference_bootstrap(clusters, replicas, seed):
    """Leitura direta do contrato, escrita de forma independente do módulo.

    Serve como oráculo: mesma ordem de chaves, mesmo gerador, mesmo índice de
    quantil (piso, sem interpolação).
    """

    keys = list(clusters)
    rng = random.Random(seed)
    values = []
    for _ in range(replicas):
        silent = 0
        total = 0
        for _ in keys:
            group = clusters[rng.choice(keys)]
            silent += group[0]
            total += group[1]
        values.append(silent / total)
    values.sort()
    return values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))]


class BuildClustersTest(unittest.TestCase):
    def test_apenas_anotadas_e_regra_de_silencio(self) -> None:
        observations = [
            support.make_observation(row_id=1, task_id="t1"),
            support.make_observation(row_id=2, task_id="t1", issue_count=1),
            support.make_observation(row_id=3, task_id="t2", functional_pass=False),
            support.make_observation(
                row_id=4, task_id="t2", static_parse_status="parse_failed"
            ),
            support.make_observation(row_id=5, task_id="t3", types=["Algorithm"]),
            support.make_observation(
                row_id=6,
                task_id="t3",
                functional_pass=False,
                types=["Algorithm"],
            ),
            support.make_observation(
                row_id=7, task_id="t4", static_parse_status="parse_failed", types=["Algorithm"]
            ),
        ]
        clusters = build_clusters(observations)
        self.assertEqual(list(clusters), ["t3", "t4"])
        self.assertEqual(clusters["t3"], [1, 2])
        self.assertEqual(clusters["t4"], [0, 1])

    def test_universo_vazio(self) -> None:
        observations = [support.make_observation(row_id=1, task_id="t1")]
        self.assertEqual(build_clusters(observations), {})


class RunBootstrapTest(unittest.TestCase):
    def setUp(self) -> None:
        self.observations = [
            support.make_observation(row_id=index + 1, task_id=f"t{index}", types=["Algorithm"])
            for index in range(10)
        ]

    def test_corresponde_ao_oraculo_do_contrato(self) -> None:
        result = run_bootstrap(self.observations, replicas=500, seed=20261115)
        expected_low, expected_high = reference_bootstrap(
            build_clusters(self.observations), 500, 20261115
        )
        self.assertAlmostEqual(result["ci_low"], expected_low, places=6)
        self.assertAlmostEqual(result["ci_high"], expected_high, places=6)
        self.assertEqual(result["clusters"], 10)
        self.assertEqual(result["silent"], 10)
        self.assertEqual(result["total"], 10)

    def test_reprodutivel_com_a_mesma_semente(self) -> None:
        first = run_bootstrap(self.observations, replicas=50, seed=7)
        second = run_bootstrap(self.observations, replicas=50, seed=7)
        self.assertEqual(first, second)

    def test_golden_quantil_por_piso(self) -> None:
        # Valores do procedimento registrado (oráculo independente acima)
        # para 10 clusters de 10 implementações, um deles com 5 silenciosas.
        observations = []
        row_id = 1
        for index in range(9):
            for _ in range(10):
                observations.append(
                    support.make_observation(
                        row_id=row_id,
                        task_id=f"t{index}",
                        functional_pass=False,
                        types=["Algorithm"],
                    )
                )
                row_id += 1
        for _ in range(5):
            observations.append(
                support.make_observation(row_id=row_id, task_id="t9", types=["Algorithm"])
            )
            row_id += 1
        for _ in range(5):
            observations.append(
                support.make_observation(
                    row_id=row_id,
                    task_id="t9",
                    static_parse_status="parse_failed",
                    types=["Algorithm"],
                )
            )
            row_id += 1

        result = run_bootstrap(observations, replicas=500, seed=20261115)
        self.assertEqual(result["clusters"], 10)
        self.assertEqual(result["silent"], 5)
        self.assertEqual(result["total"], 100)
        self.assertEqual(result["ci_low"], 0.0)
        self.assertEqual(result["ci_high"], 0.15)

    def test_parametros_invalidos(self) -> None:
        with self.assertRaises(BootstrapError):
            run_bootstrap(self.observations, replicas=0, seed=1)
        with self.assertRaises(BootstrapError):
            run_bootstrap([], replicas=10, seed=1)

    def test_registra_regra_do_quantil(self) -> None:
        result = run_bootstrap(self.observations, replicas=5, seed=1)
        self.assertEqual(result["quantile_rule"], "values[int(q*(len(values)-1))]")
        self.assertEqual(result["quantiles"], [0.025, 0.975])


class VerifyBootstrapTest(unittest.TestCase):
    def test_aceita_gabarito_igual_e_ignora_notas(self) -> None:
        result = {"clusters": 433, "silent": 25, "total": 1134, "ci_low_pct": 1.3}
        verify_bootstrap(
            result,
            {
                "clusters": 433,
                "silent": 25,
                "total": 1134,
                "ci_low_pct": 1.3,
                "notes": "texto",
            },
        )

    def test_recusa_divergencia(self) -> None:
        with self.assertRaises(BootstrapError):
            verify_bootstrap({"clusters": 432}, {"clusters": 433})


if __name__ == "__main__":
    unittest.main()
