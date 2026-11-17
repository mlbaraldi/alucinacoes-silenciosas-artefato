"""Normalização do desfecho funcional de uma implementação.

Contrato (ver docs/contrato-dados.md):

1. ``evaluation_result.is_pass`` tem precedência absoluta quando a chave existe;
   o valor precisa ser booleano JSON. Valor de outro tipo impede o fallback e
   falha fechado.
2. Sem ``is_pass``, a chave ``status`` decide: ``pass`` aprova; ``fail`` e
   ``timeout`` reprovam. Qualquer outro status é desconhecido e falha fechado.
3. Não existe desfecho por omissão. ``evaluation_result`` ausente/nulo, sem
   nenhuma das duas chaves, ou com valor indeterminado **falha fechado** com
   :class:`EvaluationResultError`; a extração não inventa reprovação.

Falha de parsing estático não altera o desfecho funcional: são dimensões
distintas. A linha que tem parsing inconclusivo ainda precisa de um desfecho
funcional determinado; se não tiver, a extração é recusada.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PASS_STATUS = "pass"
FAIL_STATUSES = frozenset({"fail", "timeout"})


class EvaluationResultError(ValueError):
    """``evaluation_result`` indeterminado, ausente ou fora do contrato."""


def normalize_functional_pass(evaluation_result: Any, *, row_id: Any = None) -> bool:
    """Devolve aprovação/reprovação funcional como booleano.

    Levanta :class:`EvaluationResultError` para resultado ausente, malformado
    ou indeterminado, para que a extração não produza observações ambíguas.
    """

    where = f"row_id={row_id!r}" if row_id is not None else "linha sem row_id"

    if evaluation_result is None:
        raise EvaluationResultError(f"evaluation_result ausente em {where}")
    if not isinstance(evaluation_result, Mapping):
        raise EvaluationResultError(
            f"evaluation_result não é objeto JSON em {where}"
        )

    if "is_pass" in evaluation_result:
        value = evaluation_result["is_pass"]
        if type(value) is not bool:
            raise EvaluationResultError(
                f"is_pass não booleano em {where}: {type(value).__name__}"
            )
        return value

    if "status" in evaluation_result:
        status = evaluation_result["status"]
        if status == PASS_STATUS:
            return True
        if status in FAIL_STATUSES:
            return False
        raise EvaluationResultError(f"status desconhecido em {where}: {status!r}")

    raise EvaluationResultError(
        f"evaluation_result sem is_pass/status em {where}: desfecho indeterminado"
    )
