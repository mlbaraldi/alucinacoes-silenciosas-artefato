#!/usr/bin/env python3
"""Reproduz o IC 95% da proporção de alucinações silenciosas.

Uso:
    python scripts/bootstrap_silent_ci.py --input data/observations.jsonl

Política de gabarito:

* execução **completa** (semente 20261115 e 200.000 réplicas, os parâmetros do
  manuscrito) **exige** ``expected/metrics.json`` existente, legível, com seção
  ``bootstrap`` compatível com os parâmetros pedidos; ausência ou gabarito
  incompatível encerra com código 2 antes de rodar;
* execução **reduzida** (qualquer outro ``--seed``/``--replicas``) é declarada
  PARCIAL na saída e no JSON: ela não valida o IC do manuscrito e o gabarito,
  quando presente e compatível, é comparado e registrado como tal;
* a saída registra o comando real (semente e réplicas efetivas), os parâmetros
  e o resultado da comparação — nada é hardcoded.

O arquivo de saída não pode sobrescrever o JSONL de entrada nem o gabarito.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alucinacoes.bootstrap import (  # noqa: E402
    BootstrapError,
    run_bootstrap,
    verify_bootstrap,
)
from alucinacoes.constants import (  # noqa: E402
    BOOTSTRAP_REPLICAS,
    BOOTSTRAP_SEED,
    SCHEMA_METRICS,
)
from alucinacoes.manifest import (  # noqa: E402
    adopt_scope,
    path_conflicts,
    read_json,
    sha256_file,
    toolchain,
    write_json,
)
from alucinacoes.observations import (  # noqa: E402
    ObservationSchemaError,
    load_observations,
)

COMMAND_TEMPLATE = (
    "python scripts/bootstrap_silent_ci.py --input <OBSERVATIONS_PATH> "
    "--output <OUTPUT_PATH> --seed {seed} --replicas {replicas}"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, required=True, help="observations.jsonl derivado"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs") / "bootstrap_silent_ci.json",
        help="arquivo JSON de saída",
    )
    parser.add_argument("--seed", type=int, default=BOOTSTRAP_SEED)
    parser.add_argument("--replicas", type=int, default=BOOTSTRAP_REPLICAS)
    parser.add_argument(
        "--expected",
        type=Path,
        default=REPO_ROOT / "expected" / "metrics.json",
        help="valores de referência conferidos (somente leitura)",
    )
    return parser


def _check_expected(
    args: argparse.Namespace, full_mode: bool
) -> tuple[dict | None, dict, str | None]:
    """Valida o gabarito. Devolve (payload, status, erro fatal)."""

    if not args.expected.is_file():
        if full_mode:
            return (
                None,
                {"verified": False, "reason": "gabarito ausente"},
                f"bootstrap completo exige o gabarito com os valores de referência conferidos; ausente: {args.expected}",
            )
        return (
            None,
            {
                "verified": False,
                "reason": "gabarito ausente; execução PARCIAL não valida o IC",
            },
            None,
        )

    try:
        payload = read_json(args.expected)
    except (OSError, json.JSONDecodeError) as exc:
        if full_mode:
            return (
                None,
                {"verified": False, "reason": "gabarito ilegível"},
                f"gabarito ilegível ({exc.__class__.__name__}) em {args.expected}",
            )
        return (
            None,
            {"verified": False, "reason": "gabarito ilegível; execução PARCIAL"},
            None,
        )

    expected = payload.get("bootstrap") if isinstance(payload, dict) else None
    if not isinstance(expected, dict):
        if full_mode:
            return (
                payload,
                {"verified": False, "reason": "gabarito sem seção bootstrap"},
                "gabarito sem seção 'bootstrap' válida",
            )
        return (
            payload,
            {"verified": False, "reason": "gabarito sem seção bootstrap"},
            None,
        )

    if expected.get("seed") != args.seed or expected.get("replicas") != args.replicas:
        detail = (
            f"gabarito seed={expected.get('seed')!r} replicas={expected.get('replicas')!r}; "
            f"execução seed={args.seed} replicas={args.replicas}"
        )
        if full_mode:
            return (
                payload,
                {"verified": False, "reason": detail},
                f"gabarito incompatível com os parâmetros: {detail}",
            )
        return payload, {"verified": False, "reason": detail}, None

    return payload, {"verified": False, "reason": "comparação não executada"}, None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    problems = path_conflicts(
        {"--output": args.output},
        {"--input": args.input, "--expected": args.expected},
    )
    if problems:
        for problem in problems:
            print(f"ERRO: {problem}", file=sys.stderr)
        print(
            "ERRO: a saída não pode sobrescrever a entrada nem o gabarito",
            file=sys.stderr,
        )
        return 2

    full_mode = args.seed == BOOTSTRAP_SEED and args.replicas == BOOTSTRAP_REPLICAS
    mode = "completo" if full_mode else "parcial"

    expected_payload, expected_status, fatal = _check_expected(args, full_mode)
    if fatal is not None:
        print(f"ERRO: {fatal}", file=sys.stderr)
        return 2

    try:
        observations = load_observations(args.input)
    except (OSError, ObservationSchemaError) as exc:
        print(f"ERRO: observações inválidas: {exc}", file=sys.stderr)
        return 2

    scope, scope_basis = adopt_scope(args.input)

    try:
        result = run_bootstrap(observations, replicas=args.replicas, seed=args.seed)
    except BootstrapError as exc:
        print(f"ERRO: bootstrap recusado: {exc}", file=sys.stderr)
        return 2

    print(
        f"clusters={result['clusters']} silent={result['silent']} "
        f"total={result['total']}"
    )
    print(
        f"seed={result['seed']} replicas={result['replicas']} "
        f"ci={result['ci_low_pct']:.1f},{result['ci_high_pct']:.1f}"
    )
    print(f"modo={mode}")

    if expected_status["reason"] == "comparação não executada":
        try:
            verify_bootstrap(result, expected_payload["bootstrap"])
        except BootstrapError as exc:
            print(f"ERRO: {exc}", file=sys.stderr)
            return 1
        expected_status = {
            "verified": True,
            "reason": "clusters/silent/total/IC conferem com o gabarito",
        }

    document = {
        "schema": SCHEMA_METRICS,
        "scope": scope,
        "scope_basis": scope_basis,
        "mode": mode,
        "command": COMMAND_TEMPLATE.format(
            seed=args.seed, replicas=args.replicas
        ),
        "parameters": {"seed": args.seed, "replicas": args.replicas},
        "toolchain": toolchain(),
        "inputs": {
            "observations": {
                "file": args.input.name,
                "sha256": sha256_file(args.input),
            },
            "expected": {
                "file": args.expected.name,
                "sha256": (
                    sha256_file(args.expected) if args.expected.is_file() else None
                ),
                "verified": expected_status["verified"],
                "reason": expected_status["reason"],
            },
        },
        "result": result,
    }
    write_json(args.output, document)

    print(f"scope={scope} ({scope_basis})")
    if expected_status["verified"]:
        print("expected: OK")
    else:
        print(f"expected: NÃO comparado ({expected_status['reason']})")
    if not full_mode:
        print(
            "PARCIAL: réplicas/semente diferentes do manuscrito; "
            "este resultado não valida o IC publicado"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
