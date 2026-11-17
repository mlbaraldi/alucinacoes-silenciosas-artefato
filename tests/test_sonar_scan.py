"""Leitura do log do SonarScanner: formatos, evidência de sucesso e recusas."""

from __future__ import annotations

import unittest

import support

from alucinacoes.sonar_scan import SonarScanError, scan_parse_errors


def _log(*lines: str) -> str:
    return "".join(line + "\n" for line in lines)


COMPLETE = (
    "INFO: Indexing files...",
    "INFO: ANALYSIS SUCCESSFUL, you can find the results at: http://localhost/dashboard",
    "INFO: EXECUTION SUCCESS",
)


class ParseErrorScanTest(unittest.TestCase):
    def test_extrai_os_dois_formatos_do_log(self) -> None:
        log = _log(
            "INFO: Indexing files...",
            "ERROR: Unable to parse source file : 'src/CEJava/a/1.java'",
            "ERROR: Unable to parse file: src/HumanEval/b/2.py",
            "INFO: 2 files indexed",
            "INFO: ANALYSIS SUCCESSFUL, you can find the results at: http://x",
            "INFO: EXECUTION SUCCESS",
        )
        scan = scan_parse_errors(log)
        self.assertEqual(
            scan.paths, ("src/CEJava/a/1.java", "src/HumanEval/b/2.py")
        )
        self.assertEqual(scan.pattern_hits, {"source_file": 1, "file": 1})
        self.assertIn("src/HumanEval/b/2.py", scan)
        self.assertNotIn("src/outro/3.py", scan)
        self.assertEqual(len(scan), 2)
        self.assertEqual(scan.success_marker, "INFO: EXECUTION SUCCESS")
        self.assertEqual(scan.lines_scanned, 6)

    def test_remove_cr_e_espacos_das_linhas(self) -> None:
        log = (
            "ERROR: Unable to parse file: src/HumanEval/b/2.py   \r\n"
            "INFO: ANALYSIS SUCCESSFUL\r\n"
            "INFO: EXECUTION SUCCESS\r\n"
        )
        scan = scan_parse_errors(log)
        self.assertEqual(scan.paths, ("src/HumanEval/b/2.py",))

    def test_log_sem_falhas_de_parsing(self) -> None:
        scan = scan_parse_errors(_log(*COMPLETE))
        self.assertEqual(scan.paths, ())
        self.assertEqual(len(scan), 0)
        self.assertEqual(scan.pattern_hits, {"source_file": 0, "file": 0})

    def test_linha_de_continuacao_parse_error_nao_e_falha(self) -> None:
        log = _log(
            "ERROR: Unable to parse file: src/HumanEval/b/2.py",
            "ERROR: Parse error at line 23 column 0:",
            "INFO: ANALYSIS SUCCESSFUL",
            "INFO: EXECUTION SUCCESS",
        )
        scan = scan_parse_errors(log)
        self.assertEqual(scan.paths, ("src/HumanEval/b/2.py",))

    def test_log_vazio_recusa(self) -> None:
        for log in ("", "   \n\n", None):
            with self.subTest(log=log):
                with self.assertRaises(SonarScanError):
                    scan_parse_errors(log)

    def test_log_truncado_sem_evidencia_de_sucesso_recusa(self) -> None:
        log = _log(
            "INFO: Indexing files...",
            "ERROR: Unable to parse file: src/HumanEval/b/2.py",
        )
        with self.assertRaises(SonarScanError) as caught:
            scan_parse_errors(log)
        self.assertIn("evidência", str(caught.exception))

    def test_log_com_falha_de_execucao_recusa(self) -> None:
        log = _log(
            "INFO: ANALYSIS SUCCESSFUL",
            "INFO: EXECUTION FAILURE",
        )
        with self.assertRaises(SonarScanError):
            scan_parse_errors(log)

    def test_linha_unable_to_parse_malformada_recusa(self) -> None:
        malformed = (
            "ERROR: Unable to parse source file: src/a/1.java",
            "ERROR: Unable to parse file src/a/1.java",
            "WARN: unable to parse anything at all",
        )
        for line in malformed:
            with self.subTest(line=line):
                with self.assertRaises(SonarScanError):
                    scan_parse_errors(_log(line, *COMPLETE))

    def test_caminho_repetido_no_mesmo_padrao_recusa(self) -> None:
        log = _log(
            "ERROR: Unable to parse file: src/HumanEval/b/2.py",
            "ERROR: Unable to parse file: src/HumanEval/b/2.py",
            *COMPLETE,
        )
        with self.assertRaises(SonarScanError):
            scan_parse_errors(log)

    def test_caminho_nos_dois_padroes_recusa(self) -> None:
        log = _log(
            "ERROR: Unable to parse source file : 'src/a/1.java'",
            "ERROR: Unable to parse file: src/a/1.java",
            *COMPLETE,
        )
        with self.assertRaises(SonarScanError):
            scan_parse_errors(log)

    def test_caminho_absoluto_recusa(self) -> None:
        for bad in ("/usr/src/a/1.java", "C:\\src\\a\\1.java"):
            with self.subTest(path=bad):
                with self.assertRaises(SonarScanError):
                    scan_parse_errors(_log(f"ERROR: Unable to parse file: {bad}", *COMPLETE))

    def test_caminho_vazio_recusa(self) -> None:
        with self.assertRaises(SonarScanError):
            scan_parse_errors(
                _log("ERROR: Unable to parse source file : ''", *COMPLETE)
            )


if __name__ == "__main__":
    unittest.main()
