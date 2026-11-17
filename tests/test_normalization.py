"""Comportamento da normalização do desfecho funcional."""

from __future__ import annotations

import unittest

import support  # noqa: F401  (insere o repositório no sys.path)

from alucinacoes.normalization import (
    EvaluationResultError,
    normalize_functional_pass,
)


class NormalizationTest(unittest.TestCase):
    def test_is_pass_true_tem_precedencia_sobre_status(self) -> None:
        self.assertIs(
            normalize_functional_pass({"is_pass": True, "status": "fail"}), True
        )

    def test_is_pass_false_tem_precedencia_sobre_status(self) -> None:
        self.assertIs(
            normalize_functional_pass({"is_pass": False, "status": "pass"}), False
        )

    def test_is_pass_nulo_falha_fechado_sem_fallback(self) -> None:
        for value in (None, 1, 0, "true", [], {}):
            with self.subTest(value=value):
                with self.assertRaises(EvaluationResultError):
                    normalize_functional_pass({"is_pass": value, "status": "pass"})

    def test_status_pass_aprova(self) -> None:
        self.assertIs(normalize_functional_pass({"status": "pass"}), True)

    def test_status_fail_e_timeout_reprovam(self) -> None:
        self.assertIs(normalize_functional_pass({"status": "fail"}), False)
        self.assertIs(normalize_functional_pass({"status": "timeout"}), False)

    def test_status_desconhecido_falha_fechado(self) -> None:
        for status in ("error", "PASS", "", None, 0):
            with self.subTest(status=status):
                with self.assertRaises(EvaluationResultError):
                    normalize_functional_pass({"status": status})

    def test_ausencia_de_resultado_falha_fechado(self) -> None:
        for evaluation in (None, {}, {"error": "compile error"}, {"return_code": 0}):
            with self.subTest(evaluation=evaluation):
                with self.assertRaises(EvaluationResultError):
                    normalize_functional_pass(evaluation)

    def test_chaves_ausentes_falham_fechado(self) -> None:
        with self.assertRaises(EvaluationResultError) as caught:
            normalize_functional_pass({}, row_id=7)
        self.assertIn("row_id=7", str(caught.exception))
        self.assertIn("indeterminado", str(caught.exception))

    def test_resultado_nao_objeto_falha_fechado(self) -> None:
        for value in ("pass", 1, [True]):
            with self.subTest(value=value):
                with self.assertRaises(EvaluationResultError):
                    normalize_functional_pass(value)

    def test_contexto_do_row_id_aparece_na_mensagem(self) -> None:
        with self.assertRaises(EvaluationResultError) as caught:
            normalize_functional_pass({"is_pass": "sim"}, row_id=42)
        self.assertIn("row_id=42", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
