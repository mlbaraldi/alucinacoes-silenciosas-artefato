"""Manifestos de proveniência com hashes SHA-256 e comandos sem caminho absoluto.

Nenhum manifesto registra caminho absoluto da máquina: os insumos entram pelo
nome do arquivo dentro do diretório de artefatos, e os comandos usam
marcadores (``<ARTIFACTS_DIR>``, ``<OUTPUT_PATH>``).
"""

from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
from typing import Any, Mapping

from . import __version__
from .constants import (
    FULL_DATASET_INPUTS,
    SCHEMA_MANIFEST,
    SCOPE_BASIS_PINNED,
    SCOPE_BASIS_UNVERIFIED,
    SCOPE_FULL_DATASET,
    SCOPE_UNVERIFIED,
)

CHUNK_SIZE = 1 << 20


def sha256_file(path: Path) -> str:
    """SHA-256 em streaming, sem carregar o arquivo inteiro em memória."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    """Escreve JSON determinístico (chaves ordenadas, UTF-8, quebra final)."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    target.write_text(text + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def toolchain() -> dict[str, str]:
    return {
        "python_version": platform.python_version(),
        "artifact_version": __version__,
    }


def build_manifest(
    *,
    scope: str,
    schema: str,
    inputs: list[dict[str, Any]],
    command: str,
    outputs: list[dict[str, Any]],
    counts: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_MANIFEST,
        "observation_schema": schema,
        "scope": scope,
        "generator": {"name": "extract_observations", "version": __version__},
        "toolchain": toolchain(),
        "inputs": inputs,
        "command": command,
        "outputs": outputs,
        "counts": counts,
        "contract": contract,
        "path_policy": "nenhum caminho absoluto é registrado neste manifesto",
    }


def file_evidence(
    path: Path, *, role: str, digest: str | None = None, **extra: Any
) -> dict[str, Any]:
    """Evidência de um insumo: nome, hash, tamanho e metadados declarados."""

    target = Path(path)
    payload: dict[str, Any] = {
        "role": role,
        "file": target.name,
        "sha256": digest if digest is not None else sha256_file(target),
        "size_bytes": target.stat().st_size,
    }
    payload.update(extra)
    return payload


def path_conflicts(
    planned: Mapping[str, Path], protected: Mapping[str, Path]
) -> list[str]:
    """Conflitos entre saídas planejadas e arquivos que não podem ser sobrescritos."""

    resolved_protected = {
        label: Path(path).resolve() for label, path in protected.items()
    }
    problems: list[str] = []
    seen: dict[Path, str] = {}
    for label, path in planned.items():
        resolved = Path(path).resolve()
        owners = [
            owner
            for owner, target in resolved_protected.items()
            if target == resolved
        ]
        if owners:
            problems.append(
                f"{label} sobrescreveria {', '.join(sorted(owners))} ({resolved})"
            )
        if resolved in seen:
            problems.append(
                f"{label} e {seen[resolved]} apontam para o mesmo arquivo ({resolved})"
            )
        seen[resolved] = label
    return problems


def is_within(path: Path, directory: Path) -> bool:
    """Verdadeiro quando ``path`` resolve dentro de ``directory``."""

    resolved = Path(path).resolve()
    root = Path(directory).resolve()
    return resolved == root or root in resolved.parents


def resolve_scope(input_hashes: dict[str, str]) -> tuple[str, str]:
    """Afirma ``full_dataset`` apenas quando os três hashes conferem com o pin."""

    if set(input_hashes) != set(FULL_DATASET_INPUTS):
        return SCOPE_UNVERIFIED, SCOPE_BASIS_UNVERIFIED
    if all(
        input_hashes[name] == expected
        for name, expected in FULL_DATASET_INPUTS.items()
    ):
        return SCOPE_FULL_DATASET, SCOPE_BASIS_PINNED
    return SCOPE_UNVERIFIED, SCOPE_BASIS_UNVERIFIED


def adopt_scope(
    observations_path: Path, manifest_path: Path | None = None
) -> tuple[str, str]:
    """Adota o escopo do manifesto apenas se ele descrever este JSONL.

    O escopo é recalculado a partir dos hashes de entrada registrados no
    manifesto; um manifesto que apenas declare ``full_dataset`` sem os hashes
    do pin não é aceito.
    """

    observations = Path(observations_path)
    manifest = (
        Path(manifest_path)
        if manifest_path is not None
        else observations.parent / "manifest.json"
    )
    if not manifest.is_file():
        return SCOPE_UNVERIFIED, "manifesto ausente; escopo não afirmado"
    try:
        payload = read_json(manifest)
    except (OSError, json.JSONDecodeError):
        return SCOPE_UNVERIFIED, "manifesto ilegível; escopo não afirmado"
    if payload.get("schema") != SCHEMA_MANIFEST:
        return SCOPE_UNVERIFIED, "manifesto com schema diferente; escopo não afirmado"
    outputs = payload.get("outputs") or []
    matches = [item for item in outputs if item.get("file") == observations.name]
    if not matches or matches[0].get("sha256") != sha256_file(observations):
        return (
            SCOPE_UNVERIFIED,
            "manifesto não corresponde ao JSONL lido; escopo não afirmado",
        )
    recorded = {
        item.get("file"): item.get("sha256") for item in payload.get("inputs", [])
    }
    scope, basis = resolve_scope(recorded)
    if payload.get("scope") != scope:
        return (
            SCOPE_UNVERIFIED,
            "escopo declarado no manifesto não confere com os hashes registrados",
        )
    return scope, basis
