#!/usr/bin/env python3
"""Calcula as tabelas descritivas (Tabelas 1–8) a partir das observações.

Uso:
    python scripts/analyze_observations.py \
        --input data/observations.jsonl \
        --output outputs

Gera ``metrics.json`` e um CSV por tabela no diretório de saída e confere o
resultado contra ``expected/metrics.json`` (valores de referência conferidos,
somente leitura). A aprovação final do status é do orquestrador, após a
execução limpa.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alucinacoes.constants import SCHEMA_METRICS  # noqa: E402
from alucinacoes.manifest import (  # noqa: E402
    adopt_scope,
    path_conflicts,
    read_json,
    sha256_file,
    toolchain,
    write_json,
)
from alucinacoes.metrics import (  # noqa: E402
    TABLE_COLUMNS,
    MetricMismatch,
    compute_metrics,
    validate_expected,
    verify_expected,
    write_tables,
)
from alucinacoes.observations import (  # noqa: E402
    ObservationSchemaError,
    load_observations,
)

COMMAND = (
    "python scripts/analyze_observations.py --input <OBSERVATIONS_PATH> "
    "--output <OUTPUT_DIR> --expected <EXPECTED_PATH>"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, required=True, help="observations.jsonl derivado"
    )
    parser.add_argument(
        "--output", type=Path, default=Path("outputs"), help="diretório de saída"
    )
    parser.add_argument(
        "--expected",
        type=Path,
        default=REPO_ROOT / "expected" / "metrics.json",
        help="valores de referência conferidos (não é reescrito)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="manifesto da extração (padrão: manifest.json ao lado do --input)",
    )
    parser.add_argument(
        "--skip-expected",
        action="store_true",
        help="não comparar com o gabarito (uso apenas para depuração)",
    )
    return parser


def _planned_outputs(output_dir: Path) -> dict[str, Path]:
    planned = {"metrics.json": output_dir / "metrics.json"}
    for name in TABLE_COLUMNS:
        planned[f"{name}.csv"] = output_dir / f"{name}.csv"
    return planned


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    manifest_path = args.manifest or (args.input.parent / "manifest.json")
    problems = path_conflicts(
        _planned_outputs(args.output),
        {
            "--input": args.input,
            "--expected": args.expected,
            "--manifest": manifest_path,
        },
    )
    if args.output.exists() and not args.output.is_dir():
        problems.append(f"--output não é diretório ({args.output})")
    if problems:
        for problem in problems:
            print(f"ERRO: {problem}", file=sys.stderr)
        print("ERRO: saídas não podem sobrescrever insumos, manifesto ou gabarito", file=sys.stderr)
        return 2

    try:
        observations = load_observations(args.input)
    except (OSError, ObservationSchemaError) as exc:
        print(f"ERRO: observações inválidas: {exc}", file=sys.stderr)
        return 2

    metrics = compute_metrics(observations)
    scope, scope_basis = adopt_scope(args.input, args.manifest)

    # Validação e comparação acontecem ANTES de qualquer escrita: uma falha
    # não pode deixar CSV/metrics.json aparentemente validados no disco.
    expected_payload = None
    if not args.skip_expected:
        if not args.expected.is_file():
            print(f"ERRO: gabarito ausente: {args.expected}", file=sys.stderr)
            return 2
        try:
            expected_payload = read_json(args.expected)
        except (OSError, json.JSONDecodeError) as exc:
            print(
                f"ERRO: gabarito ilegível ({exc.__class__.__name__}): {args.expected}",
                file=sys.stderr,
            )
            return 2
        try:
            validate_expected(expected_payload)
        except MetricMismatch as exc:
            print(f"ERRO: gabarito inválido: {exc}", file=sys.stderr)
            return 2
        expected_scope = expected_payload.get("scope")
        if expected_scope != scope:
            print(
                "ERRO: gabarito é de escopo "
                f"{expected_scope!r} e o insumo é {scope!r} ({scope_basis})",
                file=sys.stderr,
            )
            return 2
        try:
            verify_expected(metrics, expected_payload["metrics"])
        except MetricMismatch as exc:
            print(f"ERRO: {exc}", file=sys.stderr)
            return 1

    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    written_csv = write_tables(metrics, output_dir)

    document = {
        "schema": SCHEMA_METRICS,
        "scope": scope,
        "scope_basis": scope_basis,
        "command": COMMAND,
        "toolchain": toolchain(),
        "inputs": {
            "observations": {
                "file": args.input.name,
                "sha256": sha256_file(args.input),
                "records": len(observations),
            },
            "expected": (
                {
                    "file": args.expected.name,
                    "sha256": sha256_file(args.expected),
                }
                if expected_payload is not None
                else None
            ),
        },
        "path_policy": "nenhum caminho absoluto é registrado neste arquivo",
        **metrics,
        "tables_csv": written_csv,
    }
    write_json(output_dir / "metrics.json", document)

    counts = metrics["counts"]
    print(
        "rows={rows} annotated={annotated_rows} clusters={task_clusters} "
        "annotations={annotations} type_assoc={type_associations} "
        "category_assoc={category_associations}".format(**counts)
    )
    print(
        "gate: functional_only={gate_functional_only} static_only={gate_static_only} "
        "both={gate_both} none={gate_none} inconclusive={gate_inconclusive}".format(
            **counts
        )
    )
    print(
        "silent={silent_implementations} silent_type_assoc={silent_type_associations} "
        "top4={silent_top4_type_associations}".format(**counts)
    )
    print(f"tabelas CSV: {len(written_csv)} em <OUTPUT_DIR>")
    print(f"scope={scope} ({scope_basis})")
    if expected_payload is not None:
        print("expected: OK")
    else:
        print("expected: não verificado (--skip-expected)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
