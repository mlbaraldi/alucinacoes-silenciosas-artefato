#!/usr/bin/env python3
"""Deriva ``observations.jsonl`` e o manifesto a partir dos artefatos de origem.

Uso:
    python scripts/extract_observations.py \
        --artifacts /caminho/para/analysis/sonarqube/full_dataset/artifacts \
        --output data/observations.jsonl

O diretório de artefatos precisa conter ``metadata.jsonl``, ``mapped_issues.json``
e ``sonar_scan.log``. Nada é escrito no diretório de origem.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alucinacoes.extraction import (  # noqa: E402
    ISSUES_FILE,
    METADATA_FILE,
    SCAN_LOG_FILE,
    ExtractionError,
    extract_observations,
    write_extraction,
)
from alucinacoes.manifest import is_within, path_conflicts  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts",
        type=Path,
        required=True,
        help="diretório somente leitura com metadata.jsonl, mapped_issues.json e sonar_scan.log",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="arquivo JSONL de saída (ex.: data/observations.jsonl)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="manifesto de proveniência (padrão: manifest.json ao lado da saída)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest_path = args.manifest or (args.output.parent / "manifest.json")

    artifacts = args.artifacts.resolve()
    planned = {
        "--output": args.output,
        "--manifest": manifest_path,
    }
    protected = {
        "--artifacts/metadata.jsonl": artifacts / METADATA_FILE,
        "--artifacts/mapped_issues.json": artifacts / ISSUES_FILE,
        "--artifacts/sonar_scan.log": artifacts / SCAN_LOG_FILE,
    }
    problems = path_conflicts(planned, protected)
    for label, path in planned.items():
        if is_within(path, artifacts):
            problems.append(
                f"{label} gravaria dentro do diretório de artefatos (somente leitura)"
            )
    if problems:
        for problem in problems:
            print(f"ERRO: {problem}", file=sys.stderr)
        print("ERRO: escolha caminhos de saída fora dos insumos", file=sys.stderr)
        return 2

    try:
        result = extract_observations(args.artifacts)
    except ExtractionError as exc:
        print(f"ERRO: extração recusada: {exc}", file=sys.stderr)
        return 2

    manifest = write_extraction(
        result, output_path=args.output, manifest_path=manifest_path
    )

    summary = result.summary
    print(f"scope={manifest['scope']}")
    print(f"scope_basis={manifest['scope_basis']}")
    print(
        "rows={rows} annotated={annotated_rows} clusters={task_clusters} "
        "annotations={annotations} type_assoc={type_associations} "
        "category_assoc={category_associations} issues={issues} "
        "parse_failures={parse_failures}".format(**summary)
    )
    for evidence in manifest["inputs"]:
        print(f"{evidence['role']}: sha256={evidence['sha256']} bytes={evidence['size_bytes']}")
    output = manifest["outputs"][0]
    print(f"output: {output['file']} sha256={output['sha256']} records={output['records']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
