"""Extração das observações mínimas a partir dos artefatos do conjunto completo.

Entradas (somente leitura): ``metadata.jsonl``, ``mapped_issues.json`` e
``sonar_scan.log`` do diretório de artefatos ``full_dataset``. Saídas:
``observations.jsonl`` e um manifesto de proveniência.

O extrator falha fechado para: tipo de alucinação desconhecido, status funcional
desconhecido, ``is_pass`` não booleano, identificadores duplicados ou fora da
ordem densa, modelo/dataset desconhecido, extensão de arquivo incongruente com
o benchmark, issue apontando para fonte inexistente ou inconsistente, fonte
listada ao mesmo tempo como falha de parsing e como contendo issues, e log com
caminho repetido ou absoluto.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .constants import (
    DATASET_EXTENSIONS,
    DATASETS,
    EVALUATION_READ_FIELDS,
    HALLUCINATION_TYPES,
    ISSUE_READ_FIELDS,
    LABEL_READ_FIELDS,
    METADATA_READ_FIELDS,
    MODELS,
    SCHEMA_OBSERVATIONS,
    STATIC_PARSE_FAILED,
    STATIC_PARSED,
    TASK_ID_PATTERN,
    TYPE_TO_CATEGORY,
    UPSTREAM_DECLARED,
)
from .manifest import (
    build_manifest,
    file_evidence,
    resolve_scope,
    sha256_file,
    write_json,
)
from .normalization import EvaluationResultError, normalize_functional_pass
from .observations import Observation, dump_observations, observations_schema_summary
from .sonar_scan import SonarScanError, scan_parse_errors

METADATA_FILE = "metadata.jsonl"
ISSUES_FILE = "mapped_issues.json"
SCAN_LOG_FILE = "sonar_scan.log"

SONAR_ISSUE_TYPES = frozenset({"CODE_SMELL", "BUG", "VULNERABILITY"})

COMMAND = (
    "python scripts/extract_observations.py "
    "--artifacts <ARTIFACTS_DIR> --output <OUTPUT_PATH> --manifest <MANIFEST_PATH>"
)

CONTRACT = {
    "functional_pass": (
        "is_pass booleano tem precedência; sem is_pass, status pass aprova e "
        "fail/timeout reprovam; desfecho ausente/nulo, sem as duas chaves, com "
        "is_pass não booleano ou status desconhecido falha fechado — nenhuma "
        "reprovação é inferida por omissão"
    ),
    "static_parse_status": (
        "parse_failed quando o caminho relativo consta como falha de parsing no "
        "sonar_scan.log; caso contrário parsed"
    ),
    "issue_count": "registros de mapped_issues.json para o mesmo source_file",
    "types": "hallucination-type distintos por implementação, em ordem alfabética",
    "categories": "categorias distintas derivadas de TYPE_TO_CATEGORY",
    "row_order": "mesma ordem do metadata.jsonl, row_id denso de 1 a N",
    "field_allowlist": {
        "metadata": list(METADATA_READ_FIELDS),
        "label": list(LABEL_READ_FIELDS),
        "evaluation_result": list(EVALUATION_READ_FIELDS),
        "issue": list(ISSUE_READ_FIELDS),
        "note": (
            "projeção estrutural: campos fora da allowlist — inclusive "
            "conflict-content, error_message, error_detail_message, project, "
            "message e generation_line — nunca entram na observação"
        ),
    },
    "upstream": {
        "revision": UPSTREAM_DECLARED["revision"],
        "result_sha256": UPSTREAM_DECLARED["result_sha256"],
        "used_as_input": False,
    },
    "fail_closed": [
        "tipo de alucinação desconhecido ou anotação sem tipo",
        "is_pass não booleano ou status funcional desconhecido",
        "task_id fora do padrão opaco aceito",
        "row_number duplicado, não inteiro ou fora da ordem densa",
        "source_file duplicado, absoluto ou com extensão incongruente ao benchmark",
        "modelo ou dataset fora da taxonomia do conjunto",
        "issue apontando fonte inexistente ou com row/model/dataset divergente",
        "issue_key duplicada",
        "fonte simultaneamente com falha de parsing e com issues",
        "falha de parsing fora do metadata ou repetida no log",
    ],
}


class ExtractionError(ValueError):
    """Artefatos incongruentes; a extração não deve produzir observações."""


@dataclass(frozen=True)
class ExtractionResult:
    observations: tuple[Observation, ...]
    manifest: dict[str, Any]
    summary: dict[str, Any]


def _read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ExtractionError(f"JSON inválido em {path.name}:{line_number}") from exc
            if not isinstance(payload, dict):
                raise ExtractionError(
                    f"registro não objeto em {path.name}:{line_number}"
                )
            rows.append(payload)
    if not rows:
        raise ExtractionError(f"nenhum registro em {path.name}")
    return rows


def _read_issue_list(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"JSON inválido em {path.name}") from exc
    if not isinstance(payload, list):
        raise ExtractionError(f"lista de issues inválida em {path.name}")
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ExtractionError(f"issue {index} não é objeto em {path.name}")
    return payload


def _require_str(row: Mapping[str, Any], key: str, *, where: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ExtractionError(f"{key} ausente ou inválido ({where})")
    return value


def _check_source_file(source: str, dataset: str, *, where: str) -> None:
    if "\x00" in source:
        raise ExtractionError(f"source_file com byte nulo ({where})")
    if source.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", source):
        raise ExtractionError(f"source_file absoluto ({where})")
    expected = "." + DATASET_EXTENSIONS[dataset]
    if not source.endswith(expected):
        raise ExtractionError(
            f"source_file com extensão incongruente ao benchmark {dataset} ({where})"
        )
    if "/" not in source:
        raise ExtractionError(f"source_file sem diretório relativo ({where})")


def _project(
    row: Any, fields: tuple[str, ...], *, artifact: str, where: str
) -> dict[str, Any]:
    """Projeta somente as chaves da allowlist; o resto do registro é descartado."""

    if not isinstance(row, Mapping):
        raise ExtractionError(f"registro não objeto em {artifact} ({where})")
    missing = [field for field in fields if field not in row]
    if missing:
        raise ExtractionError(
            f"campo(s) ausente(s) em {artifact} ({where}): " + ", ".join(missing)
        )
    return {field: row[field] for field in fields}


def _validate_task_id(value: Any, *, where: str) -> str:
    task_id = _require_str({"task_id": value}, "task_id", where=where)
    if not re.fullmatch(TASK_ID_PATTERN, task_id):
        raise ExtractionError(f"_id fora do padrão opaco aceito ({where})")
    return task_id


def _project_labels(labels: Any, *, where: str) -> tuple[str, ...]:
    if not isinstance(labels, list):
        raise ExtractionError(f"code_labels não é lista ({where})")
    types: list[str] = []
    for index, label in enumerate(labels):
        projected = _project(
            label,
            LABEL_READ_FIELDS,
            artifact=f"code_labels[{index}]",
            where=where,
        )
        label_type = projected["hallucination-type"]
        if not isinstance(label_type, str) or not label_type.strip():
            raise ExtractionError(f"anotação sem hallucination-type ({where})")
        if label_type not in HALLUCINATION_TYPES:
            raise ExtractionError(
                f"tipo de alucinação desconhecido ({where}): {label_type!r}"
            )
        types.append(label_type)
    return tuple(types)


def _project_evaluation(value: Any, *, where: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ExtractionError(f"evaluation_result não é objeto JSON ({where})")
    return {field: value[field] for field in EVALUATION_READ_FIELDS if field in value}


def _index_metadata(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Valida o metadata e devolve registros projetados na ordem do arquivo."""

    records: list[dict[str, Any]] = []
    seen: set[int] = set()
    seen_sources: set[str] = set()
    previous = 0
    for position, row in enumerate(rows, start=1):
        row_number = row.get("row_number")
        if type(row_number) is not int or row_number < 1:
            raise ExtractionError(f"row_number inválido na posição {position}")
        if row_number in seen:
            raise ExtractionError(f"row_number duplicado: {row_number}")
        seen.add(row_number)
        if row_number <= previous:
            raise ExtractionError("metadata fora da ordem crescente de row_number")
        previous = row_number

        where = f"row_number={row_number}"
        projected = _project(
            row, METADATA_READ_FIELDS, artifact="metadata", where=where
        )
        task_id = _validate_task_id(projected["_id"], where=where)
        model = _require_str(projected, "model", where=where)
        dataset = _require_str(projected, "dataset", where=where)
        if model not in MODELS:
            raise ExtractionError(f"model desconhecido ({where}): {model!r}")
        if dataset not in DATASETS:
            raise ExtractionError(f"dataset desconhecido ({where}): {dataset!r}")

        source = _require_str(projected, "source_file", where=where)
        _check_source_file(source, dataset, where=where)
        if source in seen_sources:
            raise ExtractionError(f"source_file duplicado ({where})")
        seen_sources.add(source)

        records.append(
            {
                "row_number": row_number,
                "task_id": task_id,
                "model": model,
                "dataset": dataset,
                "source_file": source,
                "label_types": _project_labels(projected["code_labels"], where=where),
                "evaluation": _project_evaluation(
                    projected["evaluation_result"], where=where
                ),
            }
        )

    expected_rows = set(range(1, len(rows) + 1))
    if seen != expected_rows:
        raise ExtractionError("row_number não é denso de 1 a N no metadata")
    return records


def _index_issues(
    issues: list[dict[str, Any]], metadata_by_source: Mapping[str, Mapping[str, Any]]
) -> Counter[str]:
    """Valida cada issue contra o metadata e conta issues por source_file."""

    if len(issues) != len({issue.get("issue_key") for issue in issues}):
        raise ExtractionError("issue_key duplicada ou ausente em mapped_issues.json")

    counts: Counter[str] = Counter()
    for index, issue in enumerate(issues):
        where = f"issue {index}"
        projected = _project(
            issue, ISSUE_READ_FIELDS, artifact="mapped_issues", where=where
        )
        issue_key = _require_str(projected, "issue_key", where=where)
        where = f"issue_key={issue_key}"
        source = _require_str(projected, "source_file", where=where)
        row = metadata_by_source.get(source)
        if row is None:
            raise ExtractionError(f"issue aponta fonte inexistente no metadata ({where})")
        if projected["row_number"] != row["row_number"]:
            raise ExtractionError(f"row_number divergente do metadata ({where})")
        if projected["model"] != row["model"]:
            raise ExtractionError(f"model divergente do metadata ({where})")
        if projected["dataset"] != row["dataset"]:
            raise ExtractionError(f"dataset divergente do metadata ({where})")
        issue_type = projected["sonar_type"]
        if issue_type not in SONAR_ISSUE_TYPES:
            raise ExtractionError(f"sonar_type desconhecido ({where}): {issue_type!r}")
        _check_source_file(source, row["dataset"], where=where)
        counts[source] += 1
    return counts


def extract_observations(artifacts_dir: Path) -> ExtractionResult:
    """Constrói as observações e o manifesto a partir do diretório de artefatos."""

    artifacts = Path(artifacts_dir)
    metadata_path = artifacts / METADATA_FILE
    issues_path = artifacts / ISSUES_FILE
    log_path = artifacts / SCAN_LOG_FILE
    for path in (metadata_path, issues_path, log_path):
        if not path.is_file():
            raise ExtractionError(f"insumo ausente: {path.name}")

    metadata_rows = _read_jsonl_objects(metadata_path)
    issues = _read_issue_list(issues_path)
    log_text = log_path.read_text(encoding="utf-8", errors="strict")

    input_hashes = {
        METADATA_FILE: sha256_file(metadata_path),
        ISSUES_FILE: sha256_file(issues_path),
        SCAN_LOG_FILE: sha256_file(log_path),
    }
    scope, scope_basis = resolve_scope(input_hashes)

    try:
        parse_scan = scan_parse_errors(log_text)
    except SonarScanError as exc:
        raise ExtractionError(str(exc)) from exc

    records = _index_metadata(metadata_rows)
    metadata_by_source = {record["source_file"]: record for record in records}
    issue_counts = _index_issues(issues, metadata_by_source)

    parse_failed = set(parse_scan.paths)
    unknown_sources = parse_failed - set(metadata_by_source)
    if unknown_sources:
        raise ExtractionError(
            "falha de parsing fora do metadata: "
            + ", ".join(sorted(unknown_sources)[:3])
        )
    ambiguous = parse_failed & set(issue_counts)
    if ambiguous:
        raise ExtractionError(
            "fonte com falha de parsing e com issues: "
            + ", ".join(sorted(ambiguous)[:3])
        )

    observations: list[Observation] = []
    annotations = 0
    type_associations = 0
    category_associations = 0
    multi_type = 0
    multi_category = 0
    max_issues_annotated = 0
    max_issues_corpus = 0
    for record in records:
        row_id = record["row_number"]
        source = record["source_file"]
        try:
            functional_pass = normalize_functional_pass(
                record["evaluation"], row_id=row_id
            )
        except EvaluationResultError as exc:
            raise ExtractionError(str(exc)) from exc

        labels = record["label_types"]
        annotations += len(labels)
        type_annotations = Counter(labels)
        types = tuple(sorted(type_annotations))
        categories = tuple(sorted({TYPE_TO_CATEGORY[item] for item in types}))
        type_associations += len(types)
        category_associations += len(categories)
        if len(types) > 1:
            multi_type += 1
        if len(categories) > 1:
            multi_category += 1

        parse_status = (
            STATIC_PARSE_FAILED if source in parse_failed else STATIC_PARSED
        )
        issue_count = issue_counts.get(source, 0)
        if parse_status == STATIC_PARSED:
            if types:
                max_issues_annotated = max(max_issues_annotated, issue_count)
            max_issues_corpus = max(max_issues_corpus, issue_count)

        observations.append(
            Observation(
                row_id=row_id,
                task_id=record["task_id"],
                model=record["model"],
                dataset=record["dataset"],
                functional_pass=functional_pass,
                static_parse_status=parse_status,
                issue_count=issue_count,
                types=types,
                categories=categories,
                annotation_count=len(labels),
                type_annotations=dict(sorted(type_annotations.items())),
            )
        )

    annotated = sum(1 for obs in observations if obs.annotated)
    counts = {
        "rows": len(observations),
        "annotated_rows": annotated,
        "task_clusters": len({obs.task_id for obs in observations if obs.annotated}),
        "annotations": annotations,
        "type_associations": type_associations,
        "category_associations": category_associations,
        "same_category_collapse_pairs": type_associations - category_associations,
        "multi_type_implementations": multi_type,
        "multi_category_implementations": multi_category,
        "max_issues_per_parsed_annotated": max_issues_annotated,
        "max_issues_per_parsed_corpus": max_issues_corpus,
        "issues": len(issues),
        "source_files_with_issues": len(issue_counts),
        "parse_failures": len(parse_failed),
        "functional_pass": sum(1 for obs in observations if obs.functional_pass),
        "functional_fail": sum(1 for obs in observations if not obs.functional_pass),
    }
    if observations[-1].row_id != len(observations):
        raise ExtractionError("row_id final não corresponde ao total de linhas")

    manifest = build_manifest(
        scope=scope,
        schema=SCHEMA_OBSERVATIONS,
        inputs=[
            file_evidence(
                metadata_path,
                role="metadata",
                digest=input_hashes[METADATA_FILE],
                records=len(metadata_rows),
                fields_used=list(METADATA_READ_FIELDS),
                fields_ignored=sorted(
                    set(metadata_rows[0]) - set(METADATA_READ_FIELDS)
                ),
            ),
            file_evidence(
                issues_path,
                role="mapped_issues",
                digest=input_hashes[ISSUES_FILE],
                records=len(issues),
                source_files=len(issue_counts),
            ),
            file_evidence(
                log_path,
                role="sonar_scan_log",
                digest=input_hashes[SCAN_LOG_FILE],
                parse_error_paths=len(parse_scan),
                parse_error_pattern_hits=dict(parse_scan.pattern_hits),
            ),
        ],
        command=COMMAND,
        outputs=[],
        counts=counts,
        contract=CONTRACT,
    )
    manifest["scope_basis"] = scope_basis
    manifest["source_dataset"] = {
        "name": "code_hallucination full_dataset artifacts",
        "layout": "analysis/sonarqube/full_dataset/artifacts",
        "upstream": dict(UPSTREAM_DECLARED),
    }
    manifest["observation_schema_summary"] = observations_schema_summary()

    summary = {
        "rows": counts["rows"],
        "annotated_rows": counts["annotated_rows"],
        "task_clusters": counts["task_clusters"],
        "annotations": counts["annotations"],
        "type_associations": counts["type_associations"],
        "category_associations": counts["category_associations"],
        "multi_type_implementations": counts["multi_type_implementations"],
        "multi_category_implementations": counts["multi_category_implementations"],
        "max_issues_per_parsed_annotated": counts["max_issues_per_parsed_annotated"],
        "max_issues_per_parsed_corpus": counts["max_issues_per_parsed_corpus"],
        "issues": counts["issues"],
        "parse_failures": counts["parse_failures"],
    }
    return ExtractionResult(
        observations=tuple(observations), manifest=manifest, summary=summary
    )


def write_extraction(
    result: ExtractionResult, *, output_path: Path, manifest_path: Path
) -> dict[str, Any]:
    """Grava o JSONL e o manifesto (com hash da saída) e devolve o manifesto."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(dump_observations(result.observations), encoding="utf-8")

    manifest = dict(result.manifest)
    manifest["outputs"] = [
        {
            "role": "observations",
            "file": output.name,
            "sha256": sha256_file(output),
            "records": len(result.observations),
        }
    ]
    write_json(Path(manifest_path), manifest)
    return manifest
