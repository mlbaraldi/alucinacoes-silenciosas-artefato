#!/usr/bin/env python3
"""Verificação offline do artefato: extração → análise → bootstrap.

Uso (com os artefatos de origem disponíveis):
    python scripts/verify_offline.py --artifacts /caminho/para/full_dataset/artifacts

Uso (apenas com o JSONL já derivado):
    python scripts/verify_offline.py --observations data/observations.jsonl

Regras de segurança do diretório de trabalho:

* o script **nunca apaga** diretório algum (não há ``rmtree``);
* ``--workdir`` precisa apontar para um caminho que ainda não existe; caminho
  existente — inclusive o repositório, seu pai ou qualquer diretório do usuário
  — é recusado com código 2;
* sem ``--workdir``, um subdiretório único é criado em ``outputs/`` (ignorado
  pelo controle de versão);
* caminhos relativos da linha de comando são resolvidos contra o diretório
  corrente original, antes de qualquer subprocesso rodar com ``cwd`` no
  repositório.

Os comandos executados são os mesmos documentados em docs/execucao.md. Nenhum
acesso à rede, nenhum uso de git e nenhuma reexecução do SonarQube.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alucinacoes.constants import (  # noqa: E402
    BOOTSTRAP_REPLICAS,
    SCOPE_FULL_DATASET,
)
from alucinacoes.manifest import adopt_scope, read_json, sha256_file  # noqa: E402


def _display(argument: str) -> str:
    path = Path(argument)
    if path.is_absolute():
        return f"<{path.name}>"
    return argument


def run_step(label: str, arguments: list[str]) -> bool:
    command = [sys.executable, *arguments]
    print(f"\n== {label} ==")
    print("$ python " + " ".join(_display(argument) for argument in arguments))
    completed = subprocess.run(command, cwd=REPO_ROOT)
    if completed.returncode != 0:
        print(f"FALHOU: {label} (código {completed.returncode})", file=sys.stderr)
        return False
    print(f"OK: {label}")
    return True


def _resolve(path: Path, base: Path) -> Path:
    """Resolve caminho relativo contra o diretório corrente original."""

    return path if path.is_absolute() else (base / path)


def _protected(path: Path) -> bool:
    target = path.resolve()
    repo = REPO_ROOT.resolve()
    protected = {repo, *repo.parents, Path.home().resolve(), Path(target.anchor)}
    return target in protected


def _prepare_workdir(argument: Path | None, base: Path) -> tuple[Path | None, str]:
    """Devolve (workdir, erro). Nunca remove nada do disco."""

    if argument is None:
        outputs = REPO_ROOT / "outputs"
        outputs.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix="verificacao-", dir=outputs)), ""

    workdir = _resolve(argument, base)
    if workdir.exists():
        return None, (
            f"--workdir já existe ({workdir}); este comando nunca apaga diretórios. "
            "Escolha um caminho novo para a verificação."
        )
    if _protected(workdir):
        return None, (
            f"--workdir aponta para diretório protegido ({workdir}); "
            "escolha um caminho novo fora do repositório e do diretório pessoal."
        )
    try:
        workdir.mkdir(parents=True)
    except OSError as exc:
        return None, f"não foi possível criar --workdir ({workdir}): {exc}"
    return workdir, ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=None,
        help="diretório de artefatos de origem (se omitido, usa --observations)",
    )
    parser.add_argument(
        "--observations",
        type=Path,
        default=REPO_ROOT / "data" / "observations.jsonl",
        help="JSONL derivado já existente",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=None,
        help="diretório novo para a verificação (precisa não existir)",
    )
    parser.add_argument(
        "--replicas", type=int, default=200000, help="réplicas do bootstrap"
    )
    parser.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="não executar o bootstrap (verificação parcial)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base = Path.cwd()

    workdir, error = _prepare_workdir(args.workdir, base)
    if workdir is None:
        print(f"ERRO: {error}", file=sys.stderr)
        return 2
    print(f"workdir={workdir}")

    artifacts = _resolve(args.artifacts, base) if args.artifacts is not None else None
    observations = _resolve(args.observations, base)
    manifest = None

    if artifacts is not None:
        observations = workdir / "observations.jsonl"
        manifest = workdir / "manifest.json"
        if not run_step(
            "extração",
            [
                str(SCRIPTS / "extract_observations.py"),
                "--artifacts",
                str(artifacts),
                "--output",
                str(observations),
                "--manifest",
                str(manifest),
            ],
        ):
            return 1
    else:
        if not observations.is_file():
            print(
                f"ERRO: informe --artifacts ou um --observations existente ({observations})",
                file=sys.stderr,
            )
            return 2
        manifest = observations.parent / "manifest.json"
        if not manifest.is_file():
            print(
                f"ERRO: manifesto ausente ao lado de {observations.name}; "
                "rode a extração antes de verificar",
                file=sys.stderr,
            )
            return 2
        try:
            payload = read_json(manifest)
        except (OSError, json.JSONDecodeError):
            print(f"ERRO: manifesto ilegível ({manifest})", file=sys.stderr)
            return 2
        outputs = payload.get("outputs") or []
        matches = [item for item in outputs if item.get("file") == observations.name]
        if not matches or matches[0].get("sha256") != sha256_file(observations):
            print(
                "ERRO: o JSONL não corresponde ao hash registrado no manifesto "
                "(entrada alterada ou manifesto de outro arquivo)",
                file=sys.stderr,
            )
            return 2
        scope, basis = adopt_scope(observations, manifest)
        if scope != SCOPE_FULL_DATASET:
            print(
                f"ERRO: escopo {scope!r} ({basis}); a verificação usa o gabarito "
                "do corpus completo",
                file=sys.stderr,
            )
            return 2

    analysis_args = [
        str(SCRIPTS / "analyze_observations.py"),
        "--input",
        str(observations),
        "--output",
        str(workdir / "analise"),
        "--expected",
        str(REPO_ROOT / "expected" / "metrics.json"),
    ]
    if manifest is not None:
        analysis_args.extend(["--manifest", str(manifest)])
    if not run_step("análise", analysis_args):
        return 1

    if not args.skip_bootstrap:
        if not run_step(
            "bootstrap",
            [
                str(SCRIPTS / "bootstrap_silent_ci.py"),
                "--input",
                str(observations),
                "--output",
                str(workdir / "analise" / "bootstrap_silent_ci.json"),
                "--replicas",
                str(args.replicas),
            ],
        ):
            return 1

    if args.skip_bootstrap:
        print("\nverificação offline PARCIAL: bootstrap não executado")
    elif args.replicas != BOOTSTRAP_REPLICAS:
        print(
            f"\nverificação offline PARCIAL: bootstrap com {args.replicas} réplicas "
            "(não valida o IC do gabarito)"
        )
    else:
        print(
            "\nverificação offline completa: extração, análise e bootstrap "
            f"({BOOTSTRAP_REPLICAS} réplicas)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
