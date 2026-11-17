"""Schema das observações mínimas e leitura/escrita do JSONL derivado.

Cada linha de ``data/observations.jsonl`` descreve uma implementação sem expor
código, trechos, mensagens de erro, nomes de projeto ou caminhos de arquivo.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .constants import (
    CATEGORIES,
    DATASETS,
    HALLUCINATION_TYPES,
    MODELS,
    SCHEMA_OBSERVATIONS,
    STATE_BOTH,
    STATE_FUNCTIONAL_ONLY,
    STATE_INCONCLUSIVE,
    STATE_NONE,
    STATE_STATIC_ONLY,
    STATIC_PARSE_FAILED,
    STATIC_PARSED,
    TASK_ID_PATTERN,
    TYPE_TO_CATEGORY,
)

OBSERVATION_FIELDS = (
    "row_id",
    "task_id",
    "model",
    "dataset",
    "functional_pass",
    "static_parse_status",
    "issue_count",
    "types",
    "categories",
    "annotation_count",
    "type_annotations",
)


class ObservationSchemaError(ValueError):
    """Observação fora do contrato de dados."""


@dataclass(frozen=True)
class Observation:
    row_id: int
    task_id: str
    model: str
    dataset: str
    functional_pass: bool
    static_parse_status: str
    issue_count: int
    types: tuple[str, ...]
    categories: tuple[str, ...]
    annotation_count: int
    type_annotations: Mapping[str, int]

    @property
    def annotated(self) -> bool:
        """A implementação recebeu ao menos um tipo de alucinação."""

        return bool(self.types)

    @property
    def gate_state(self) -> str:
        """Estado conclusivo dos dois gates (ou inconclusivo por parsing)."""

        if self.static_parse_status == STATIC_PARSE_FAILED:
            return STATE_INCONCLUSIVE
        if self.functional_pass:
            return STATE_STATIC_ONLY if self.issue_count else STATE_NONE
        return STATE_BOTH if self.issue_count else STATE_FUNCTIONAL_ONLY

    def as_dict(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "task_id": self.task_id,
            "model": self.model,
            "dataset": self.dataset,
            "functional_pass": self.functional_pass,
            "static_parse_status": self.static_parse_status,
            "issue_count": self.issue_count,
            "types": list(self.types),
            "categories": list(self.categories),
            "annotation_count": self.annotation_count,
            "type_annotations": dict(self.type_annotations),
        }


def _expect_int(value: Any, *, field: str, row_id: Any, minimum: int = 0) -> int:
    if type(value) is not int:
        raise ObservationSchemaError(
            f"{field} não inteiro em row_id={row_id!r}: {type(value).__name__}"
        )
    if value < minimum:
        raise ObservationSchemaError(f"{field} < {minimum} em row_id={row_id!r}")
    return value


def observation_from_dict(row: Mapping[str, Any]) -> Observation:
    """Valida e converte um objeto JSON em :class:`Observation`."""

    if not isinstance(row, Mapping):
        raise ObservationSchemaError("observação não é objeto JSON")

    unknown = set(row) - set(OBSERVATION_FIELDS)
    if unknown:
        raise ObservationSchemaError(
            "campos não previstos no schema: " + ", ".join(sorted(unknown))
        )
    missing = set(OBSERVATION_FIELDS) - set(row)
    if missing:
        raise ObservationSchemaError(
            "campos ausentes no schema: " + ", ".join(sorted(missing))
        )

    row_id = _expect_int(row["row_id"], field="row_id", row_id="?", minimum=1)

    task_id = row["task_id"]
    if not isinstance(task_id, str) or not task_id.strip():
        raise ObservationSchemaError(f"task_id inválido em row_id={row_id}")
    if re.fullmatch(TASK_ID_PATTERN, task_id) is None:
        raise ObservationSchemaError(
            f"task_id fora do padrão opaco aceito em row_id={row_id}"
        )

    model = row["model"]
    if model not in MODELS:
        raise ObservationSchemaError(f"model desconhecido em row_id={row_id}: {model!r}")

    dataset = row["dataset"]
    if dataset not in DATASETS:
        raise ObservationSchemaError(
            f"dataset desconhecido em row_id={row_id}: {dataset!r}"
        )

    functional_pass = row["functional_pass"]
    if type(functional_pass) is not bool:
        raise ObservationSchemaError(f"functional_pass não booleano em row_id={row_id}")

    static_parse_status = row["static_parse_status"]
    if static_parse_status not in (STATIC_PARSED, STATIC_PARSE_FAILED):
        raise ObservationSchemaError(
            f"static_parse_status desconhecido em row_id={row_id}: "
            f"{static_parse_status!r}"
        )

    issue_count = _expect_int(row["issue_count"], field="issue_count", row_id=row_id)
    if static_parse_status == STATIC_PARSE_FAILED and issue_count:
        raise ObservationSchemaError(
            f"parsing falho com issue_count>0 em row_id={row_id}"
        )

    types_value = row["types"]
    if not isinstance(types_value, list) or not all(
        isinstance(item, str) for item in types_value
    ):
        raise ObservationSchemaError(f"types inválido em row_id={row_id}")
    types = tuple(types_value)
    if len(set(types)) != len(types):
        raise ObservationSchemaError(f"types com duplicata em row_id={row_id}")
    if list(types) != sorted(types):
        raise ObservationSchemaError(f"types fora de ordem canônica em row_id={row_id}")
    unknown_types = [item for item in types if item not in HALLUCINATION_TYPES]
    if unknown_types:
        raise ObservationSchemaError(
            f"tipo de alucinação desconhecido em row_id={row_id}: {unknown_types!r}"
        )

    expected_categories = tuple(sorted({TYPE_TO_CATEGORY[item] for item in types}))
    categories = row["categories"]
    if not isinstance(categories, list) or not all(
        isinstance(item, str) for item in categories
    ):
        raise ObservationSchemaError(f"categories inválido em row_id={row_id}")
    if tuple(categories) != expected_categories:
        raise ObservationSchemaError(
            f"categories incongruentes com types em row_id={row_id}"
        )
    if any(item not in CATEGORIES for item in categories):
        raise ObservationSchemaError(f"categoria desconhecida em row_id={row_id}")

    annotation_count = _expect_int(
        row["annotation_count"], field="annotation_count", row_id=row_id
    )

    type_annotations = row["type_annotations"]
    if not isinstance(type_annotations, Mapping):
        raise ObservationSchemaError(f"type_annotations inválido em row_id={row_id}")
    for name, count in type_annotations.items():
        if name not in types:
            raise ObservationSchemaError(
                f"type_annotations com tipo não listado em row_id={row_id}: {name!r}"
            )
        _expect_int(count, field=f"type_annotations[{name!r}]", row_id=row_id, minimum=1)
    if set(type_annotations) != set(types):
        raise ObservationSchemaError(
            f"type_annotations não cobre todos os types em row_id={row_id}"
        )
    if sum(type_annotations.values()) != annotation_count:
        raise ObservationSchemaError(
            f"type_annotations não soma annotation_count em row_id={row_id}"
        )

    return Observation(
        row_id=row_id,
        task_id=task_id,
        model=model,
        dataset=dataset,
        functional_pass=functional_pass,
        static_parse_status=static_parse_status,
        issue_count=issue_count,
        types=types,
        categories=expected_categories,
        annotation_count=annotation_count,
        type_annotations=dict(type_annotations),
    )


def dump_observations(observations: Iterable[Observation]) -> str:
    """Serializa na ordem recebida, com chaves ordenadas e sem espaços extra."""

    lines = [
        json.dumps(obs.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for obs in observations
    ]
    return "".join(line + "\n" for line in lines)


def load_observations(path: Path) -> list[Observation]:
    """Lê o JSONL validando schema, ordem e unicidade dos identificadores."""

    observations: list[Observation] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ObservationSchemaError(f"linha vazia em {path.name}:{line_number}")
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ObservationSchemaError(
                    f"JSON inválido em {path.name}:{line_number}"
                ) from exc
            observation = observation_from_dict(payload)
            if observation.row_id != line_number:
                raise ObservationSchemaError(
                    "row_id não é denso 1..N em "
                    f"{path.name}:{line_number}: row_id={observation.row_id}"
                )
            observations.append(observation)
    if not observations:
        raise ObservationSchemaError(f"nenhuma observação em {path.name}")
    return observations


def observations_schema_summary() -> dict[str, Any]:
    """Descrição do schema para o manifesto de proveniência."""

    return {
        "schema": SCHEMA_OBSERVATIONS,
        "fields": list(OBSERVATION_FIELDS),
        "enums": {
            "model": list(MODELS),
            "dataset": list(DATASETS),
            "static_parse_status": [STATIC_PARSED, STATIC_PARSE_FAILED],
            "types": list(HALLUCINATION_TYPES),
            "categories": list(CATEGORIES),
        },
        "order": "row_id crescente, mesma ordem do metadata.jsonl de origem",
        "excluded": [
            "código gerado e trechos",
            "prompt, enunciado e explicações",
            "conflict-content e hallucination-type-other (texto livre)",
            "error_message e error_detail_message (podem conter código)",
            "mensagens de erro ou de issue",
            "nomes de projeto e caminhos de arquivo",
            "log bruto do scanner",
        ],
        "projection": "allowlist estrutural em alucinacoes/constants.py",
    }
