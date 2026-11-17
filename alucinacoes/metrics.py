"""Métricas descritivas (Tabelas 1–8) e comparação com os valores de referência.

As métricas são derivadas apenas das observações mínimas. Cada tabela recebe um
nome semântico (não numérico) e é exportada como CSV e como lista de objetos no
JSON agregado.

Denominadores (ver docs/contrato-dados.md):

* percentuais "do corpus"/"do modelo"/"do benchmark" usam o total da própria
  população;
* "sem issue" usa apenas implementações com parsing concluído;
* "reprova" e "nenhum" usam todas as implementações anotadas da linha;
* percentuais de estado de gate usam as implementações anotadas da linha.
"""

from __future__ import annotations

import csv
import itertools
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .constants import (
    CATEGORIES,
    GATE_STATES as CANONICAL_GATE_STATES,
    SCHEMA_EXPECTED,
    CATEGORY_LABELS,
    DATASETS,
    GATE_STATE_LABELS,
    GATE_STATES,
    HALLUCINATION_TYPES,
    ISSUE_HISTOGRAM_BINS,
    MODELS,
    STATE_BOTH,
    STATE_FUNCTIONAL_ONLY,
    STATE_INCONCLUSIVE,
    STATE_NONE,
    STATE_STATIC_ONLY,
    STATIC_PARSE_FAILED,
)
from .observations import Observation

TOLERANCE = 0.05

TABLE_KEY_FIELDS: dict[str, tuple[str, ...]] = {
    "gate_cross_corpus": ("population", "stratum"),
    "annotations_by_model": ("model",),
    "annotations_by_benchmark": ("benchmark",),
    "prevalence_by_benchmark_model": ("benchmark", "model"),
    "gate_states_by_type": ("type",),
    "gate_states_by_model_benchmark": ("model", "benchmark"),
    "gate_states_by_model": ("model",),
    "gate_states_by_benchmark": ("benchmark",),
    "categories_summary": ("category_code",),
    "types_static_summary": ("type",),
    "type_composition_silent": ("type",),
    "type_silencing_rate": ("type",),
    "type_cooccurrence": ("type_a", "type_b"),
    "parse_histogram": ("bin_label",),
}

TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "gate_cross_corpus": (
        "population",
        "stratum",
        "with_issues",
        "without_issues",
        "inconclusive",
        "total",
        "pct_with_issues_of_total",
        "pct_with_issues_of_parsed",
    ),
    "annotations_by_model": (
        "model",
        "annotated_n",
        "annotated_pct",
        "silent_n",
        "silent_pct_of_model",
    ),
    "annotations_by_benchmark": (
        "benchmark",
        "implementations_n",
        "annotated_n",
        "annotated_pct",
        "silent_n",
        "silent_pct_of_benchmark",
    ),
    "prevalence_by_benchmark_model": (
        "benchmark",
        "model",
        "implementations_n",
        "annotated_n",
        "annotated_pct",
    ),
    "gate_states_by_type": (
        "type",
        "total_n",
        "functional_only_n",
        "functional_only_pct",
        "static_only_n",
        "static_only_pct",
        "both_n",
        "both_pct",
        "none_n",
        "none_pct",
        "inconclusive_n",
        "inconclusive_pct",
    ),
    "gate_states_by_model_benchmark": (
        "model",
        "benchmark",
        "functional_only_n",
        "static_only_n",
        "both_n",
        "none_n",
        "inconclusive_n",
        "total_n",
    ),
    "gate_states_by_model": (
        "model",
        "functional_only_n",
        "static_only_n",
        "both_n",
        "none_n",
        "inconclusive_n",
        "total_n",
    ),
    "gate_states_by_benchmark": (
        "benchmark",
        "functional_only_n",
        "static_only_n",
        "both_n",
        "none_n",
        "inconclusive_n",
        "total_n",
    ),
    "categories_summary": (
        "category_code",
        "category",
        "annotated_n",
        "annotated_pct",
        "silent_n",
        "silent_pct",
    ),
    "types_static_summary": (
        "type",
        "annotated_n",
        "parsed_n",
        "without_issue_n",
        "without_issue_pct_of_parsed",
        "without_issue_pct_of_annotated",
        "reproved_n",
        "reproved_pct_of_annotated",
        "none_n",
        "none_pct_of_annotated",
    ),
    "type_composition_silent": (
        "type",
        "annotated_n",
        "annotated_pct",
        "silent_n",
        "silent_pct",
    ),
    "type_silencing_rate": (
        "type",
        "silent_n",
        "annotated_n",
        "silencing_pct",
    ),
    "type_cooccurrence": (
        "type_a",
        "type_b",
        "annotated_n",
        "silent_n",
    ),
    "parse_histogram": (
        "bin_label",
        "issues_min",
        "issues_max",
        "implementations_n",
        "pct_of_parsed",
    ),
}

STATE_COUNT_COLUMNS = {
    STATE_FUNCTIONAL_ONLY: "functional_only",
    STATE_STATIC_ONLY: "static_only",
    STATE_BOTH: "both",
    STATE_NONE: "none",
    STATE_INCONCLUSIVE: "inconclusive",
}


REQUIRED_COUNT_FIELDS = (
    "rows",
    "annotated_rows",
    "task_clusters",
    "annotations",
    "type_associations",
    "category_associations",
    "gate_functional_only",
    "gate_static_only",
    "gate_both",
    "gate_none",
    "gate_inconclusive",
)


class MetricMismatch(ValueError):
    """Métrica calculada divergente dos valores de referência."""


def validate_expected(payload: Any) -> None:
    """Valida a estrutura do gabarito antes de qualquer comparação.

    Um arquivo ``{}`` (ou com seções vazias) não pode aprovar tudo: exige
    schema, escopo, contadores obrigatórios, os cinco estados de gate e todas
    as tabelas declaradas, cada uma não vazia e com as chaves de linha. Não
    compara valores — isso é papel de :func:`verify_expected`.
    """

    if not isinstance(payload, Mapping):
        raise MetricMismatch("gabarito não é objeto JSON")
    if payload.get("schema") != SCHEMA_EXPECTED:
        raise MetricMismatch(
            f"schema do gabarito ausente ou diferente de {SCHEMA_EXPECTED!r}"
        )
    scope = payload.get("scope")
    if not isinstance(scope, str) or not scope.strip():
        raise MetricMismatch("gabarito sem 'scope'")

    metrics = payload.get("metrics")
    if not isinstance(metrics, Mapping) or not metrics:
        raise MetricMismatch("gabarito sem seção 'metrics' preenchida")

    counts = metrics.get("counts")
    if not isinstance(counts, Mapping) or not counts:
        raise MetricMismatch("gabarito sem 'metrics.counts' preenchido")
    missing_counts = [key for key in REQUIRED_COUNT_FIELDS if key not in counts]
    if missing_counts:
        raise MetricMismatch(
            "gabarito sem contadores obrigatórios: " + ", ".join(missing_counts)
        )
    for key in REQUIRED_COUNT_FIELDS:
        value = counts[key]
        if type(value) is not int or value < 0:
            raise MetricMismatch(f"gabarito com contador inválido: {key}={value!r}")

    gate_states = metrics.get("gate_states")
    if not isinstance(gate_states, Mapping) or not gate_states:
        raise MetricMismatch("gabarito sem 'metrics.gate_states' preenchido")
    for state in CANONICAL_GATE_STATES:
        block = gate_states.get(state)
        if not isinstance(block, Mapping):
            raise MetricMismatch(f"gabarito sem o estado de gate {state!r}")
        if type(block.get("n")) is not int:
            raise MetricMismatch(f"gabarito com 'n' inválido no estado {state!r}")
        if not isinstance(block.get("pct_of_annotated"), (int, float)):
            raise MetricMismatch(
                f"gabarito com 'pct_of_annotated' inválido no estado {state!r}"
            )

    histogram = metrics.get("parse_histogram")
    if not isinstance(histogram, Mapping) or not histogram:
        raise MetricMismatch("gabarito sem 'metrics.parse_histogram' preenchido")
    histogram_counts = histogram.get("counts")
    if (
        not isinstance(histogram_counts, list)
        or not histogram_counts
        or any(type(value) is not int or value < 0 for value in histogram_counts)
    ):
        raise MetricMismatch("gabarito com 'parse_histogram.counts' inválido")
    if type(histogram.get("max")) is not int:
        raise MetricMismatch("gabarito com 'parse_histogram.max' inválido")

    tables = metrics.get("tables")
    if not isinstance(tables, Mapping) or not tables:
        raise MetricMismatch("gabarito sem 'metrics.tables' preenchido")
    required_tables = [
        name for name in TABLE_KEY_FIELDS if name != "parse_histogram"
    ]
    missing_tables = [name for name in required_tables if name not in tables]
    if missing_tables:
        raise MetricMismatch(
            "gabarito sem tabelas esperadas: " + ", ".join(missing_tables)
        )
    for name in required_tables:
        key_fields = TABLE_KEY_FIELDS[name]
        rows = tables[name]
        if not isinstance(rows, list) or not rows:
            raise MetricMismatch(f"gabarito com tabela vazia: {name}")
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                raise MetricMismatch(f"gabarito com linha não objeto em {name}[{index}]")
            missing = [field for field in key_fields if row.get(field) is None]
            if missing:
                raise MetricMismatch(
                    f"gabarito com chave incompleta em {name}[{index}]: "
                    + ", ".join(missing)
                )


def percent(numerator: int, denominator: int) -> float:
    """Percentual com uma casa decimal, arredondamento half-up."""

    if denominator <= 0:
        raise ValueError("denominador não positivo em percentual")
    value = (Decimal(numerator) * 100 / Decimal(denominator)).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )
    return float(value)


def percent_or_none(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return percent(numerator, denominator)


def _gate_counts(observations: Iterable[Observation]) -> Counter[str]:
    return Counter(obs.gate_state for obs in observations)


def _state_counts(source: Mapping[str, int | str]) -> dict[str, Any]:
    row: dict[str, Any] = {"total_n": int(source["total_n"])}
    for state, prefix in STATE_COUNT_COLUMNS.items():
        row[f"{prefix}_n"] = int(source[state])
    return row


def _state_row(source: Mapping[str, int | str]) -> dict[str, Any]:
    total = int(source["total_n"])
    row = _state_counts(source)
    for state, prefix in STATE_COUNT_COLUMNS.items():
        count = int(source[state])
        row[f"{prefix}_pct"] = percent_or_none(count, total) if total else None
    return row


def _corpus_counts(observations: Sequence[Observation]) -> dict[str, Any]:
    annotated = [obs for obs in observations if obs.annotated]
    parsed_annotated = [
        obs for obs in annotated if obs.static_parse_status != STATIC_PARSE_FAILED
    ]
    parsed = [obs for obs in observations if obs.static_parse_status != STATIC_PARSE_FAILED]
    return {
        "rows": len(observations),
        "annotated_rows": len(annotated),
        "task_clusters": len({obs.task_id for obs in annotated}),
        "annotations": sum(obs.annotation_count for obs in observations),
        "type_associations": sum(len(obs.types) for obs in observations),
        "category_associations": sum(len(obs.categories) for obs in observations),
        "same_category_collapse_pairs": sum(
            len(obs.types) - len(obs.categories) for obs in annotated
        ),
        "multi_type_implementations": sum(
            1 for obs in annotated if len(obs.types) > 1
        ),
        "multi_category_implementations": sum(
            1 for obs in annotated if len(obs.categories) > 1
        ),
        "annotated_functional_pass": sum(1 for obs in annotated if obs.functional_pass),
        "annotated_functional_fail": sum(
            1 for obs in annotated if not obs.functional_pass
        ),
        "corpus_functional_pass": sum(1 for obs in observations if obs.functional_pass),
        "corpus_functional_fail": sum(
            1 for obs in observations if not obs.functional_pass
        ),
        "annotated_parsed": len(parsed_annotated),
        "annotated_inconclusive": len(annotated) - len(parsed_annotated),
        "annotated_with_issues": sum(
            1 for obs in parsed_annotated if obs.issue_count > 0
        ),
        "annotated_without_issues": sum(
            1 for obs in parsed_annotated if obs.issue_count == 0
        ),
        "corpus_parsed": len(parsed),
        "corpus_inconclusive": len(observations) - len(parsed),
        "corpus_with_issues": sum(1 for obs in parsed if obs.issue_count > 0),
        "corpus_without_issues": sum(1 for obs in parsed if obs.issue_count == 0),
        "max_issues_per_parsed_annotated": max(
            (obs.issue_count for obs in parsed_annotated), default=0
        ),
        "max_issues_per_parsed_corpus": max(
            (obs.issue_count for obs in parsed), default=0
        ),
        "types_with_annotations": len({t for obs in observations for t in obs.types}),
        "categories_with_annotations": len(
            {c for obs in observations for c in obs.categories}
        ),
    }


def _gate_cross_rows(
    annotations: Sequence[Observation], corpus: Sequence[Observation]
) -> list[dict[str, Any]]:
    populations = (("annotated", annotations), ("corpus", corpus))
    strata = (
        ("functional_pass", True),
        ("functional_fail", False),
        ("total", None),
    )
    rows: list[dict[str, Any]] = []
    for population, subset in populations:
        for stratum, expected_pass in strata:
            if expected_pass is None:
                inner = list(subset)
            else:
                inner = [obs for obs in subset if obs.functional_pass is expected_pass]
            parsed = [
                obs for obs in inner if obs.static_parse_status != STATIC_PARSE_FAILED
            ]
            with_issues = sum(1 for obs in parsed if obs.issue_count > 0)
            without_issues = sum(1 for obs in parsed if obs.issue_count == 0)
            inconclusive = len(inner) - len(parsed)
            rows.append(
                {
                    "population": population,
                    "stratum": stratum,
                    "with_issues": with_issues,
                    "without_issues": without_issues,
                    "inconclusive": inconclusive,
                    "total": len(inner),
                    "pct_with_issues_of_total": percent_or_none(
                        with_issues, len(inner)
                    ),
                    "pct_with_issues_of_parsed": percent_or_none(
                        with_issues, len(parsed)
                    ),
                }
            )
    return rows


def _annotations_by_model(
    annotations: Sequence[Observation],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    total = len(annotations)
    silent_total = 0
    for model in MODELS:
        subset = [obs for obs in annotations if obs.model == model]
        silent = sum(1 for obs in subset if obs.gate_state == STATE_NONE)
        silent_total += silent
        rows.append(
            {
                "model": model,
                "annotated_n": len(subset),
                "annotated_pct": percent(len(subset), total),
                "silent_n": silent,
                "silent_pct_of_model": percent_or_none(silent, len(subset)),
            }
        )
    rows.append(
        {
            "model": "TOTAL",
            "annotated_n": total,
            "annotated_pct": 100.0,
            "silent_n": silent_total,
            "silent_pct_of_model": percent(silent_total, total),
        }
    )
    return rows


def _annotations_by_benchmark(
    corpus: Sequence[Observation],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    annotated_total = sum(1 for obs in corpus if obs.annotated)
    for dataset in DATASETS:
        subset = [obs for obs in corpus if obs.dataset == dataset]
        annotated = [obs for obs in subset if obs.annotated]
        silent = sum(1 for obs in annotated if obs.gate_state == STATE_NONE)
        rows.append(
            {
                "benchmark": dataset,
                "implementations_n": len(subset),
                "annotated_n": len(annotated),
                "annotated_pct": percent(len(annotated), annotated_total),
                "silent_n": silent,
                "silent_pct_of_benchmark": percent_or_none(silent, len(annotated)),
            }
        )
    return rows


def _prevalence_rows(corpus: Sequence[Observation]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dataset in DATASETS:
        for model in MODELS:
            subset = [
                obs for obs in corpus if obs.dataset == dataset and obs.model == model
            ]
            annotated = sum(1 for obs in subset if obs.annotated)
            rows.append(
                {
                    "benchmark": dataset,
                    "model": model,
                    "implementations_n": len(subset),
                    "annotated_n": annotated,
                    "annotated_pct": percent_or_none(annotated, len(subset)),
                }
            )
    return rows


FIELD_ALIASES = {"benchmark": "dataset"}


def _gate_rows(
    annotations: Sequence[Observation], group_fields: tuple[str, ...]
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], list[Observation]] = {}
    for obs in annotations:
        key = tuple(
            str(getattr(obs, FIELD_ALIASES.get(field, field))) for field in group_fields
        )
        groups.setdefault(key, []).append(obs)

    rows: list[dict[str, Any]] = []
    for key, subset in groups.items():
        counts = _gate_counts(subset)
        counts["total_n"] = len(subset)
        row = dict(zip(group_fields, key))
        row.update(_state_row(counts))
        rows.append(row)
    return rows


def _state_block(annotations: Sequence[Observation]) -> dict[str, Any]:
    counts = _gate_counts(annotations)
    total = len(annotations)
    return {
        state: {
            "n": counts.get(state, 0),
            "pct_of_annotated": percent(counts.get(state, 0), total),
            "label": GATE_STATE_LABELS[state],
        }
        for state in GATE_STATES
    }


def _category_rows(annotations: Sequence[Observation]) -> list[dict[str, Any]]:
    annotated = Counter[str]()
    silent = Counter[str]()
    for obs in annotations:
        for code in obs.categories:
            annotated[code] += 1
            if obs.gate_state == STATE_NONE:
                silent[code] += 1
    total_annotated = sum(annotated.values())
    total_silent = sum(silent.values())
    rows: list[dict[str, Any]] = []
    for code in CATEGORIES:
        rows.append(
            {
                "category_code": code,
                "category": CATEGORY_LABELS[code],
                "annotated_n": annotated[code],
                "annotated_pct": percent(annotated[code], total_annotated),
                "silent_n": silent[code],
                "silent_pct": percent(silent[code], total_silent),
            }
        )
    rows.append(
        {
            "category_code": "TOTAL",
            "category": "Total",
            "annotated_n": total_annotated,
            "annotated_pct": 100.0,
            "silent_n": total_silent,
            "silent_pct": 100.0,
        }
    )
    return rows


def _type_rows(annotations: Sequence[Observation]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    totals = Counter[str]()
    for hallucination_type in HALLUCINATION_TYPES:
        subset = [obs for obs in annotations if hallucination_type in obs.types]
        parsed = [obs for obs in subset if obs.static_parse_status != STATIC_PARSE_FAILED]
        without_issue = [obs for obs in parsed if obs.issue_count == 0]
        reproved = [obs for obs in subset if not obs.functional_pass]
        none = [obs for obs in subset if obs.gate_state == STATE_NONE]
        totals.update(
            {
                "annotated_n": len(subset),
                "parsed_n": len(parsed),
                "without_issue_n": len(without_issue),
                "reproved_n": len(reproved),
                "none_n": len(none),
            }
        )
        rows.append(
            {
                "type": hallucination_type,
                "annotated_n": len(subset),
                "parsed_n": len(parsed),
                "without_issue_n": len(without_issue),
                "without_issue_pct_of_parsed": percent_or_none(
                    len(without_issue), len(parsed)
                ),
                "without_issue_pct_of_annotated": percent_or_none(
                    len(without_issue), len(subset)
                ),
                "reproved_n": len(reproved),
                "reproved_pct_of_annotated": percent_or_none(
                    len(reproved), len(subset)
                ),
                "none_n": len(none),
                "none_pct_of_annotated": percent_or_none(len(none), len(subset)),
            }
        )
    rows.append(
        {
            "type": "TOTAL",
            "annotated_n": totals["annotated_n"],
            "parsed_n": totals["parsed_n"],
            "without_issue_n": totals["without_issue_n"],
            "without_issue_pct_of_parsed": percent(
                totals["without_issue_n"], totals["parsed_n"]
            ),
            "without_issue_pct_of_annotated": percent(
                totals["without_issue_n"], totals["annotated_n"]
            ),
            "reproved_n": totals["reproved_n"],
            "reproved_pct_of_annotated": percent(
                totals["reproved_n"], totals["annotated_n"]
            ),
            "none_n": totals["none_n"],
            "none_pct_of_annotated": percent(totals["none_n"], totals["annotated_n"]),
        }
    )
    return rows


def _type_composition_rows(
    annotations: Sequence[Observation],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    annotated = Counter[str]()
    silent = Counter[str]()
    for obs in annotations:
        for hallucination_type in obs.types:
            annotated[hallucination_type] += 1
            if obs.gate_state == STATE_NONE:
                silent[hallucination_type] += 1

    total_annotated = sum(annotated.values())
    total_silent = sum(silent.values())
    rows: list[dict[str, Any]] = []
    for hallucination_type in HALLUCINATION_TYPES:
        rows.append(
            {
                "type": hallucination_type,
                "annotated_n": annotated[hallucination_type],
                "annotated_pct": percent(annotated[hallucination_type], total_annotated),
                "silent_n": silent[hallucination_type],
                "silent_pct": percent(silent[hallucination_type], total_silent),
            }
        )
    rows.append(
        {
            "type": "TOTAL (associações de tipo)",
            "annotated_n": total_annotated,
            "annotated_pct": 100.0,
            "silent_n": total_silent,
            "silent_pct": 100.0,
        }
    )
    unique_silent = sum(1 for obs in annotations if obs.gate_state == STATE_NONE)
    rows.append(
        {
            "type": "Implementações únicas",
            "annotated_n": len(annotations),
            "annotated_pct": None,
            "silent_n": unique_silent,
            "silent_pct": percent(unique_silent, len(annotations)),
        }
    )
    return rows, {"annotated": total_annotated, "silent": total_silent}


def _silencing_rows(annotations: Sequence[Observation]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for hallucination_type in HALLUCINATION_TYPES:
        subset = [obs for obs in annotations if hallucination_type in obs.types]
        silent = [obs for obs in subset if obs.gate_state == STATE_NONE]
        rows.append(
            {
                "type": hallucination_type,
                "silent_n": len(silent),
                "annotated_n": len(subset),
                "silencing_pct": percent_or_none(len(silent), len(subset)),
            }
        )
    return rows


def _cooccurrence_rows(
    annotations: Sequence[Observation],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    annotated_pairs = Counter[tuple[str, str]]()
    silent_pairs = Counter[tuple[str, str]]()
    for obs in annotations:
        for pair in itertools.combinations(obs.types, 2):
            annotated_pairs[pair] += 1
            if obs.gate_state == STATE_NONE:
                silent_pairs[pair] += 1

    rows: list[dict[str, Any]] = [
        {
            "type_a": pair[0],
            "type_b": pair[1],
            "annotated_n": annotated_pairs.get(pair, 0),
            "silent_n": silent_pairs.get(pair, 0),
        }
        for pair in itertools.combinations(HALLUCINATION_TYPES, 2)
    ]
    observed = sorted(
        (count, pair) for pair, count in annotated_pairs.items() if count
    )
    top = {"annotated_n": observed[-1][0], "types": list(observed[-1][1])} if observed else None
    silent_observed = [
        {"types": list(pair), "silent_n": count}
        for pair, count in sorted(silent_pairs.items(), key=lambda item: (-item[1], item[0]))
        if count
    ]
    without = [
        hallucination_type
        for hallucination_type in HALLUCINATION_TYPES
        if not any(
            hallucination_type in pair and annotated_pairs.get(pair, 0)
            for pair in itertools.combinations(HALLUCINATION_TYPES, 2)
        )
    ]
    summary = {
        "pairs_with_annotated_cooccurrence": sum(
            1 for count in annotated_pairs.values() if count
        ),
        "pairs_with_silent_cooccurrence": len(silent_observed),
        "max_annotated_pair": top,
        "silent_pairs": silent_observed,
        "types_without_annotated_cooccurrence": without,
    }
    return rows, summary


def _histogram_rows(annotations: Sequence[Observation]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parsed = [obs for obs in annotations if obs.static_parse_status != STATIC_PARSE_FAILED]
    rows: list[dict[str, Any]] = []
    counts: list[int] = []
    for low, high, label in ISSUE_HISTOGRAM_BINS:
        if high is None:
            count = sum(1 for obs in parsed if obs.issue_count >= low)
        else:
            count = sum(1 for obs in parsed if low <= obs.issue_count <= high)
        counts.append(count)
        rows.append(
            {
                "bin_label": label,
                "issues_min": low,
                "issues_max": high,
                "implementations_n": count,
                "pct_of_parsed": percent(count, len(parsed)),
            }
        )
    summary = {
        "labels": [label for _, _, label in ISSUE_HISTOGRAM_BINS],
        "counts": counts,
        "total": len(parsed),
        "max": max((obs.issue_count for obs in parsed), default=0),
    }
    return rows, summary


def _silent_summary(annotations: Sequence[Observation]) -> dict[str, Any]:
    silent = [obs for obs in annotations if obs.gate_state == STATE_NONE]
    silent_types = Counter[str]()
    for obs in silent:
        for hallucination_type in obs.types:
            silent_types[hallucination_type] += 1
    ordered = sorted(
        silent_types.items(),
        key=lambda item: (-item[1], HALLUCINATION_TYPES.index(item[0])),
    )
    top4 = ordered[:4]
    return {
        "implementations": len(silent),
        "type_associations": sum(silent_types.values()),
        "category_associations": sum(len(obs.categories) for obs in silent),
        "types_with_associations": len(silent_types),
        "top4_type_associations": sum(count for _, count in top4),
        "top4_types": [name for name, _ in top4],
        "max_type_associations": top4[0][1] if top4 else 0,
    }


def compute_metrics(observations: Sequence[Observation]) -> dict[str, Any]:
    """Calcula todas as tabelas e contadores a partir das observações."""

    corpus = list(observations)
    annotations = [obs for obs in corpus if obs.annotated]
    if not annotations:
        raise ValueError("nenhuma implementação anotada nas observações")

    corpus_counts = _corpus_counts(corpus)
    states = _state_block(annotations)
    histogram_rows, histogram = _histogram_rows(annotations)
    type_rows = _type_rows(annotations)
    composition_rows, composition = _type_composition_rows(annotations)
    cooccurrence_rows, cooccurrence = _cooccurrence_rows(annotations)
    silent = _silent_summary(annotations)

    by_type_rows: list[dict[str, Any]] = []
    for hallucination_type in HALLUCINATION_TYPES:
        subset = [obs for obs in annotations if hallucination_type in obs.types]
        counts_for_type = _gate_counts(subset)
        counts_for_type["total_n"] = len(subset)  # type: ignore[assignment]
        by_type_rows.append(
            dict({"type": hallucination_type}, **_state_row(counts_for_type))
        )

    by_model_benchmark = sorted(
        _gate_rows(annotations, ("model", "benchmark")),
        key=lambda row: (row["model"], row["benchmark"]),
    )
    total_counts = _gate_counts(annotations)
    total_counts["total_n"] = len(annotations)  # type: ignore[assignment]
    by_model_benchmark.append(
        dict({"model": "TOTAL", "benchmark": "all"}, **_state_counts(total_counts))
    )

    tables: dict[str, list[dict[str, Any]]] = {
        "gate_cross_corpus": _gate_cross_rows(annotations, corpus),
        "annotations_by_model": _annotations_by_model(annotations),
        "annotations_by_benchmark": _annotations_by_benchmark(corpus),
        "prevalence_by_benchmark_model": _prevalence_rows(corpus),
        "gate_states_by_type": by_type_rows,
        "gate_states_by_model_benchmark": by_model_benchmark,
        "gate_states_by_model": sorted(
            _gate_rows(annotations, ("model",)),
            key=lambda row: MODELS.index(row["model"]),
        ),
        "gate_states_by_benchmark": sorted(
            _gate_rows(annotations, ("benchmark",)),
            key=lambda row: DATASETS.index(row["benchmark"]),
        ),
        "categories_summary": _category_rows(annotations),
        "types_static_summary": type_rows,
        "type_composition_silent": composition_rows,
        "type_silencing_rate": _silencing_rows(annotations),
        "type_cooccurrence": cooccurrence_rows,
        "parse_histogram": histogram_rows,
    }

    total_gate = {state: states[state]["n"] for state in GATE_STATES}
    counts = dict(corpus_counts)
    counts.update(
        {
            "silent_implementations": silent["implementations"],
            "silent_type_associations": silent["type_associations"],
            "silent_category_associations": silent["category_associations"],
            "silent_top4_type_associations": silent["top4_type_associations"],
            "types_with_silent_associations": silent["types_with_associations"],
            "parsed_annotated_total": corpus_counts["annotated_parsed"],
            "gate_functional_only": total_gate[STATE_FUNCTIONAL_ONLY],
            "gate_static_only": total_gate[STATE_STATIC_ONLY],
            "gate_both": total_gate[STATE_BOTH],
            "gate_none": total_gate[STATE_NONE],
            "gate_inconclusive": total_gate[STATE_INCONCLUSIVE],
        }
    )

    return {
        "counts": counts,
        "gate_states": states,
        "parse_histogram": histogram,
        "type_composition_totals": composition,
        "cooccurrence": cooccurrence,
        "tables": tables,
    }


def write_tables(metrics: Mapping[str, Any], output_dir: Path) -> list[str]:
    """Exporta cada tabela como CSV e devolve os nomes de arquivo escritos."""

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for name, columns in TABLE_COLUMNS.items():
        filename = f"{name}.csv"
        rows = metrics["tables"][name]
        with (target / filename).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(columns)
            for row in rows:
                writer.writerow([_format_cell(row.get(column)) for column in columns])
        written.append(filename)
    return written


def _format_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.1f}"
    return value


def _compare_values(path: str, expected: Any, actual: Any, diffs: list[str]) -> None:
    if isinstance(expected, float) or isinstance(actual, float):
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            diffs.append(f"{path}: esperado {expected!r}, obtido {actual!r}")
            return
        if abs(float(expected) - float(actual)) > TOLERANCE:
            diffs.append(f"{path}: esperado {expected!r}, obtido {actual!r}")
        return
    if expected != actual:
        diffs.append(f"{path}: esperado {expected!r}, obtido {actual!r}")


def _index_rows(
    name: str, rows: Sequence[Mapping[str, Any]]
) -> dict[tuple[Any, ...], Mapping[str, Any]]:
    keys = TABLE_KEY_FIELDS[name]
    indexed: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for row in rows:
        key = tuple(row.get(field) for field in keys)
        if key in indexed:
            raise MetricMismatch(f"tabela {name}: chave repetida {key!r}")
        indexed[key] = row
    return indexed


def verify_expected(metrics: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    """Compara as métricas calculadas com os valores de referência.

    Levanta :class:`MetricMismatch` com a lista de divergências; nunca altera o
    gabarito nem promove a saída para ``expected/``.
    """

    diffs: list[str] = []

    expected_counts = expected.get("counts", {})
    for key, value in expected_counts.items():
        if key not in metrics["counts"]:
            diffs.append(f"counts.{key}: ausente nas métricas")
            continue
        _compare_values(f"counts.{key}", value, metrics["counts"][key], diffs)

    histogram = expected.get("parse_histogram", {})
    for key, value in histogram.items():
        _compare_values(
            f"parse_histogram.{key}", value, metrics["parse_histogram"][key], diffs
        )

    expected_states = expected.get("gate_states", {})
    for state, block in expected_states.items():
        actual_block = metrics["gate_states"][state]
        for field, value in block.items():
            if field not in actual_block:
                diffs.append(f"gate_states.{state}.{field}: ausente nas métricas")
                continue
            _compare_values(
                f"gate_states.{state}.{field}", value, actual_block[field], diffs
            )

    for name, expected_rows in expected.get("tables", {}).items():
        if name not in metrics["tables"]:
            diffs.append(f"tables.{name}: tabela ausente nas métricas")
            continue
        actual_index = _index_rows(name, metrics["tables"][name])
        for expected_row in expected_rows:
            key = tuple(expected_row.get(field) for field in TABLE_KEY_FIELDS[name])
            actual_row = actual_index.get(key)
            if actual_row is None:
                diffs.append(f"tables.{name}{key}: linha ausente nas métricas")
                continue
            for field, value in expected_row.items():
                if field in TABLE_KEY_FIELDS[name]:
                    continue
                if field not in actual_row:
                    diffs.append(f"tables.{name}{key}.{field}: ausente nas métricas")
                    continue
                _compare_values(
                    f"tables.{name}{key}.{field}", value, actual_row[field], diffs
                )

    if diffs:
        raise MetricMismatch(
            "divergência contra expected/metrics.json:\n- " + "\n- ".join(diffs)
        )
