"""Leitura do log do SonarScanner: quais fontes não puderam ser analisadas.

O log precisa provar duas coisas antes de qualquer conclusão:

1. a execução terminou com sucesso (marcador de conclusão e ausência de
   marcador de falha), senão o log é considerado vazio/truncado e a extração é
   recusada;
2. toda linha que anuncia falha de parsing segue um dos dois formatos
   conhecidos do scanner; linha malformada falha fechado em vez de virar
   "parsed".

Nenhuma linha do log é copiada para as observações: apenas os caminhos
relativos são extraídos, comparados com o metadata e descartados.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SOURCE_FILE_LINE = re.compile(r"ERROR: Unable to parse source file : '([^']*)'")
FILE_LINE = re.compile(r"ERROR: Unable to parse file: (.+)")

SUCCESS_MARKERS = ("INFO: ANALYSIS SUCCESSFUL", "INFO: EXECUTION SUCCESS")
FAILURE_MARKERS = (
    "INFO: EXECUTION FAILURE",
    "ERROR: Error during SonarScanner execution",
)
PARSE_FAILURE_HINT = "unable to parse"


class SonarScanError(ValueError):
    """Log de análise estática incongruente, truncado ou fora do contrato."""


@dataclass(frozen=True)
class ParseErrorScan:
    """Resultado da varredura de falhas de parsing do log."""

    paths: tuple[str, ...]
    pattern_hits: dict[str, int]
    lines_scanned: int
    success_marker: str

    def __contains__(self, path: object) -> bool:
        return path in self._path_set

    def __len__(self) -> int:
        return len(self.paths)

    @property
    def _path_set(self) -> frozenset[str]:
        return frozenset(self.paths)


def _validate_path(path: str, *, pattern: str) -> str:
    cleaned = path.strip()
    if not cleaned:
        raise SonarScanError(f"caminho vazio no padrão {pattern!r}")
    if "\x00" in cleaned:
        raise SonarScanError(f"caminho com byte nulo no padrão {pattern!r}")
    if cleaned.startswith("/") or cleaned.startswith("\\"):
        raise SonarScanError(f"caminho absoluto no log ({pattern!r}): {cleaned!r}")
    if re.match(r"^[A-Za-z]:[\\/]", cleaned):
        raise SonarScanError(f"caminho absoluto no log ({pattern!r}): {cleaned!r}")
    return cleaned


def _require_complete_execution(lines: list[str]) -> str:
    """Exige evidência de execução concluída; recusa log vazio ou truncado."""

    for marker in FAILURE_MARKERS:
        if any(marker in line for line in lines):
            raise SonarScanError(f"log registra falha de execução ({marker})")

    present = [
        marker for marker in SUCCESS_MARKERS if any(marker in line for line in lines)
    ]
    if not present:
        raise SonarScanError(
            "log sem evidência de execução concluída com sucesso "
            "(vazio, truncado ou de outro estágio); parsing não pode ser declarado"
        )
    return present[-1]


def scan_parse_errors(log_text: str) -> ParseErrorScan:
    """Extrai os caminhos relativos com falha de parsing, sem duplicatas."""

    if not isinstance(log_text, str) or not log_text.strip():
        raise SonarScanError(
            "log vazio: não há evidência de execução do scanner"
        )

    lines = [line.rstrip() for line in log_text.splitlines()]
    success_marker = _require_complete_execution(lines)

    hits: dict[str, list[str]] = {"source_file": [], "file": []}
    for line in lines:
        if PARSE_FAILURE_HINT not in line.lower():
            continue
        source_match = SOURCE_FILE_LINE.fullmatch(line)
        if source_match is not None:
            hits["source_file"].append(
                _validate_path(source_match.group(1), pattern="source_file")
            )
            continue
        file_match = FILE_LINE.fullmatch(line)
        if file_match is not None:
            hits["file"].append(_validate_path(file_match.group(1), pattern="file"))
            continue
        raise SonarScanError(
            "linha de falha de parsing em formato não reconhecido: "
            f"{line[:80]!r}"
        )

    for name, found in hits.items():
        if len(found) != len(set(found)):
            raise SonarScanError(f"caminho repetido no padrão {name!r}: log ambíguo")

    overlap = set(hits["source_file"]) & set(hits["file"])
    if overlap:
        raise SonarScanError(
            "caminho listado nos dois padrões de falha de parsing: "
            + ", ".join(sorted(overlap)[:3])
        )

    paths = tuple(sorted(hits["source_file"] + hits["file"]))
    return ParseErrorScan(
        paths=paths,
        pattern_hits={name: len(found) for name, found in hits.items()},
        lines_scanned=len(lines),
        success_marker=success_marker,
    )
