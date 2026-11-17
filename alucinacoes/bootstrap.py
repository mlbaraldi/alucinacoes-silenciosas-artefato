"""Intervalo de confiança por bootstrap agrupado por tarefa.

Replica o procedimento registrado no manuscrito: agrupamento pela chave de
tarefa (``task_id``), reamostragem com reposição dos 433 grupos, razão entre
implementações silenciosas e total de implementações anotadas em cada réplica,
semente 20261115 e 200.000 réplicas.

Detalhes que precisam ser preservados para o resultado ser idêntico:

* o dicionário de grupos é construído na ordem do ``observations.jsonl``
  (mesma ordem do metadata de origem), e ``list(clusters)`` define a ordem das
  chaves entregue a ``random.Random.choice``;
* o quantil é o elemento de índice ``int(q * (len(values) - 1))`` da lista
  ordenada (piso, sem interpolação);
* a réplica usa ``random.Random(seed).choice`` sobre a lista de chaves, uma
  escolha por cluster.

Nenhum texto do modelo é gerado e nenhuma análise estática é reexecutada.
"""

from __future__ import annotations

import random
from typing import Any, Sequence

from .constants import (
    BOOTSTRAP_QUANTILE_RULE,
    BOOTSTRAP_QUANTILES,
    STATIC_PARSE_FAILED,
)
from .observations import Observation


class BootstrapError(ValueError):
    """Universo de clusters vazio ou parâmetros inválidos."""


def build_clusters(observations: Sequence[Observation]) -> dict[str, list[int]]:
    """Agrupa por tarefa na ordem de leitura, contando [silenciosas, total]."""

    clusters: dict[str, list[int]] = {}
    for obs in observations:
        if not obs.annotated:
            continue
        cluster = clusters.setdefault(obs.task_id, [0, 0])
        cluster[1] += 1
        if (
            obs.functional_pass
            and obs.static_parse_status != STATIC_PARSE_FAILED
            and obs.issue_count == 0
        ):
            cluster[0] += 1
    return clusters


def run_bootstrap(
    observations: Sequence[Observation],
    *,
    replicas: int,
    seed: int,
    quantiles: tuple[float, float] = BOOTSTRAP_QUANTILES,
) -> dict[str, Any]:
    """Executa o bootstrap e devolve contagens, quantis e razões."""

    if replicas < 1:
        raise BootstrapError("replicas deve ser positivo")
    if not (0 <= quantiles[0] < quantiles[1] <= 1):
        raise BootstrapError("quantis fora de (0, 1)")

    clusters = build_clusters(observations)
    if not clusters:
        raise BootstrapError("nenhuma tarefa anotada encontrada")

    keys = list(clusters)
    silent_total = sum(counts[0] for counts in clusters.values())
    implementation_total = sum(counts[1] for counts in clusters.values())

    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(replicas):
        silent = 0
        total = 0
        for _ in keys:
            group = clusters[rng.choice(keys)]
            silent += group[0]
            total += group[1]
        values.append(silent / total)
    values.sort()

    low = values[int(quantiles[0] * (len(values) - 1))]
    high = values[int(quantiles[1] * (len(values) - 1))]
    return {
        "seed": seed,
        "replicas": replicas,
        "quantiles": [quantiles[0], quantiles[1]],
        "quantile_rule": BOOTSTRAP_QUANTILE_RULE,
        "clusters": len(keys),
        "silent": silent_total,
        "total": implementation_total,
        "ci_low": round(low, 6),
        "ci_high": round(high, 6),
        "ci_low_pct": float(f"{low * 100:.1f}"),
        "ci_high_pct": float(f"{high * 100:.1f}"),
    }


def verify_bootstrap(result: dict[str, Any], expected: dict[str, Any]) -> None:
    """Confere o resultado do bootstrap contra os valores de referência."""

    diffs: list[str] = []
    for key, value in expected.items():
        if key == "notes":
            continue
        if key not in result:
            diffs.append(f"bootstrap.{key}: ausente no resultado")
            continue
        actual = result[key]
        if isinstance(value, float) and isinstance(actual, (int, float)):
            if abs(value - actual) > 0.05:
                diffs.append(f"bootstrap.{key}: esperado {value!r}, obtido {actual!r}")
        elif actual != value:
            diffs.append(f"bootstrap.{key}: esperado {value!r}, obtido {actual!r}")
    if diffs:
        raise BootstrapError(
            "divergência do bootstrap contra expected/metrics.json:\n- "
            + "\n- ".join(diffs)
        )
