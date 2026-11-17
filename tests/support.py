"""Apoio aos testes: caminho do repositório, artefatos sintéticos e observações."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alucinacoes.constants import TYPE_TO_CATEGORY  # noqa: E402
from alucinacoes.observations import Observation, observation_from_dict  # noqa: E402

METADATA_FILE = "metadata.jsonl"
ISSUES_FILE = "mapped_issues.json"
SCAN_LOG_FILE = "sonar_scan.log"


def observation_payload(
    row_id: int,
    *,
    task_id: str = "task-1",
    model: str = "gpt-4",
    dataset: str = "HumanEval",
    functional_pass: bool = True,
    static_parse_status: str = "parsed",
    issue_count: int = 0,
    types: Sequence[str] = (),
    type_annotations: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Monta o objeto JSON de uma observação já no formato do schema."""

    ordered_types = sorted(set(types))
    if type_annotations is None:
        type_annotations = {name: 1 for name in ordered_types}
    else:
        type_annotations = dict(sorted(type_annotations.items()))
    annotation_count = sum(type_annotations.values())
    return {
        "row_id": row_id,
        "task_id": task_id,
        "model": model,
        "dataset": dataset,
        "functional_pass": functional_pass,
        "static_parse_status": static_parse_status,
        "issue_count": issue_count,
        "types": ordered_types,
        "categories": sorted({TYPE_TO_CATEGORY[name] for name in ordered_types}),
        "annotation_count": annotation_count,
        "type_annotations": type_annotations,
    }


def make_observation(**kwargs: Any) -> Observation:
    return observation_from_dict(observation_payload(**kwargs))


def write_observations(path: Path, payloads: Iterable[dict[str, Any]]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(payload, sort_keys=True, separators=(",", ":")) for payload in payloads]
    target.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return target


def metadata_row(
    row_number: int,
    source_file: str,
    *,
    task_id: str = "task-1",
    model: str = "gpt-4",
    dataset: str = "HumanEval",
    evaluation_result: Mapping[str, Any] | None = None,
    labels: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    return {
        "row_number": row_number,
        "_id": task_id,
        "model": model,
        "dataset": dataset,
        "source_file": source_file,
        "code_labels": [dict(label) for label in labels],
        "evaluation_result": (
            {"is_pass": True} if evaluation_result is None else dict(evaluation_result)
        ),
    }


def label(hallucination_type: str) -> dict[str, Any]:
    return {"hallucination-type": hallucination_type}


def issue(
    issue_key: str,
    row: Mapping[str, Any],
    *,
    sonar_type: str = "CODE_SMELL",
) -> dict[str, Any]:
    return {
        "issue_key": issue_key,
        "source_file": row["source_file"],
        "row_number": row["row_number"],
        "model": row["model"],
        "dataset": row["dataset"],
        "sonar_rule": "java:S1854",
        "sonar_type": sonar_type,
        "severity": "MAJOR",
        "line": 1,
    }


def write_artifacts(
    directory: Path,
    metadata: Sequence[Mapping[str, Any]],
    issues: Sequence[Mapping[str, Any]],
    log_text: str,
) -> Path:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    metadata_text = "".join(
        json.dumps(row, sort_keys=True) + "\n" for row in metadata
    )
    (target / METADATA_FILE).write_text(metadata_text, encoding="utf-8")
    (target / ISSUES_FILE).write_text(
        json.dumps(list(issues), sort_keys=True), encoding="utf-8"
    )
    (target / SCAN_LOG_FILE).write_text(log_text, encoding="utf-8")
    return target


def default_metadata() -> list[dict[str, Any]]:
    """Quatro linhas cobrindo os casos do contrato."""

    return [
        metadata_row(
            1,
            "src/HumanEval/gpt-4/0001_task.py",
            task_id="t1",
            labels=[
                label("Behavior Conflicting"),
                label("Behavior Conflicting"),
                label("Algorithm"),
            ],
            evaluation_result={"is_pass": True, "status": "fail"},
        ),
        metadata_row(
            2,
            "src/HumanEval/gpt-4/0002_task.py",
            task_id="t1",
            labels=[label("Library/Project")],
            evaluation_result={"status": "pass"},
        ),
        metadata_row(
            3,
            "src/CEJava/codellama-7b/0003_task.java",
            task_id="t2",
            model="codellama-7b",
            dataset="CEJava",
            labels=[],
            evaluation_result={"is_pass": False},
        ),
        metadata_row(
            4,
            "src/CEPython/deepseek-r1/0004_task.py",
            task_id="t3",
            model="deepseek-r1",
            dataset="CEPython",
            labels=[label("Undefined Variables")],
            evaluation_result={"status": "timeout"},
        ),
    ]


def success_tail() -> str:
    return (
        "INFO: ANALYSIS SUCCESSFUL, you can find the results at: "
        "http://localhost/dashboard\n"
        "INFO: EXECUTION SUCCESS\n"
    )


def default_log() -> str:
    return (
        "INFO: Indexing files...\n"
        "ERROR: Unable to parse file: src/CEPython/deepseek-r1/0004_task.py\n"
        "INFO: 4 files indexed\n" + success_tail()
    )
