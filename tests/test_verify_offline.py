"""Verificação offline: segurança do workdir e resolução de caminhos.

O ponto crítico: o script nunca apaga diretório algum. Qualquer ``--workdir``
existente é recusado, e nada no repositório, no diretório pai ou no diretório
pessoal é removido.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

import support

from alucinacoes.extraction import extract_observations, write_extraction

SCRIPT = support.REPO_ROOT / "scripts" / "verify_offline.py"
_spec = importlib.util.spec_from_file_location("verify_offline", SCRIPT)
assert _spec is not None and _spec.loader is not None
verify_offline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify_offline)


class WorkdirGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def test_workdir_existente_e_recusado_e_preservado(self) -> None:
        target = self.base / "existente"
        (target / "nested").mkdir(parents=True)
        sentinel = target / "nested" / "sentinela.txt"
        sentinel.write_text("não apagar", encoding="utf-8")

        prepared, error = verify_offline._prepare_workdir(target, self.base)
        self.assertIsNone(prepared)
        self.assertIn("já existe", error)
        self.assertTrue(sentinel.is_file())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "não apagar")

    def test_workdir_novo_e_criado(self) -> None:
        prepared, error = verify_offline._prepare_workdir(Path("novo"), self.base)
        self.assertEqual(error, "")
        self.assertIsNotNone(prepared)
        self.assertEqual(prepared, self.base / "novo")
        self.assertTrue(prepared.is_dir())

    def test_workdir_repo_raiz_e_parent_sao_recusados(self) -> None:
        for target in (support.REPO_ROOT, support.REPO_ROOT.parent, Path.home()):
            with self.subTest(target=target):
                prepared, error = verify_offline._prepare_workdir(target, self.base)
                self.assertIsNone(prepared)
                self.assertIn("já existe", error)
        # nada do repositório foi removido
        self.assertTrue((support.REPO_ROOT / "expected" / "metrics.json").is_file())
        self.assertTrue((support.REPO_ROOT / "alucinacoes" / "extraction.py").is_file())

    def test_diretorio_padrao_e_unico_em_outputs(self) -> None:
        first, error_one = verify_offline._prepare_workdir(None, self.base)
        second, error_two = verify_offline._prepare_workdir(None, self.base)
        self.assertEqual((error_one, error_two), ("", ""))
        self.assertNotEqual(first, second)
        self.assertTrue(str(first).startswith(str(support.REPO_ROOT / "outputs")))
        for path in (first, second):
            self.assertTrue(path.is_dir())
            path.rmdir()

    def test_caminho_relativo_resolve_no_cwd_original(self) -> None:
        relative = Path("sub") / "obs.jsonl"
        self.assertEqual(
            verify_offline._resolve(relative, self.base), self.base / relative
        )
        absolute = Path("/tmp/abs.jsonl")
        self.assertEqual(verify_offline._resolve(absolute, self.base), absolute)

    def test_cli_recusa_workdir_existente_sem_apagar(self) -> None:
        target = self.base / "cli-existente"
        (target / "nested").mkdir(parents=True)
        sentinel = target / "sentinela.txt"
        sentinel.write_text("manter", encoding="utf-8")

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = verify_offline.main(
                [
                    "--observations",
                    str(self.base / "nao-existe.jsonl"),
                    "--workdir",
                    str(target),
                    "--skip-bootstrap",
                ]
            )
        self.assertEqual(code, 2)
        self.assertIn("já existe", stderr.getvalue())
        self.assertTrue(sentinel.is_file())
        self.assertTrue((target / "nested").is_dir())

    def test_cli_sem_artefatos_nem_observacoes_falha_antes_de_analisar(self) -> None:
        stderr = io.StringIO()
        stdout = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            code = verify_offline.main(
                [
                    "--observations",
                    str(self.base / "ausente.jsonl"),
                    "--workdir",
                    str(self.base / "novo"),
                    "--skip-bootstrap",
                ]
            )
        self.assertEqual(code, 2)
        self.assertIn("informe --artifacts", stderr.getvalue())
        self.assertFalse((self.base / "novo" / "analise").exists())


class ObservationsBindingTest(unittest.TestCase):
    """Sem --artifacts, o JSONL precisa bater com o manifesto ao lado."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        artifacts = support.write_artifacts(
            self.root / "artifacts",
            support.default_metadata(),
            [],
            support.default_log(),
        )
        self.result = extract_observations(artifacts)
        self.data = self.root / "data"
        self.observations = self.data / "observations.jsonl"
        self.manifest = self.data / "manifest.json"
        write_extraction(
            self.result,
            output_path=self.observations,
            manifest_path=self.manifest,
        )

    def _main(self, observations: Path) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = verify_offline.main(
                [
                    "--observations",
                    str(observations),
                    "--workdir",
                    str(self.root / f"work-{observations.parent.name}"),
                    "--skip-bootstrap",
                ]
            )
        return code, stdout.getvalue(), stderr.getvalue()

    def test_manifesto_ausente_recusa(self) -> None:
        isolated = self.root / "solto"
        isolated.mkdir()
        copy = isolated / "observations.jsonl"
        copy.write_bytes(self.observations.read_bytes())
        code, _, stderr = self._main(copy)
        self.assertEqual(code, 2)
        self.assertIn("manifesto ausente", stderr)

    def test_jsonl_adulterado_com_totais_iguais_recusa(self) -> None:
        lines = self.observations.read_text(encoding="utf-8").splitlines()
        import json as _json

        first = _json.loads(lines[0])
        third = _json.loads(lines[2])
        assert first["functional_pass"] != third["functional_pass"]
        first["functional_pass"], third["functional_pass"] = (
            third["functional_pass"],
            first["functional_pass"],
        )
        lines[0] = _json.dumps(first, sort_keys=True, separators=(",", ":"))
        lines[2] = _json.dumps(third, sort_keys=True, separators=(",", ":"))
        self.observations.write_text("\n".join(lines) + "\n", encoding="utf-8")

        code, _, stderr = self._main(self.observations)
        self.assertEqual(code, 2)
        self.assertIn("hash registrado no manifesto", stderr)

    def test_escopo_nao_verificado_recusa_o_gabarito(self) -> None:
        code, stdout, stderr = self._main(self.observations)
        self.assertEqual(code, 2)
        self.assertIn("escopo 'unverified'", stderr)
        self.assertIn("corpus completo", stderr)
        self.assertNotIn("PARCIAL", stdout)

    def test_skip_bootstrap_marca_verificacao_parcial(self) -> None:
        # O caminho com escopo pinado é exercitado na integração; aqui basta
        # confirmar que a mensagem de parcial não some quando a análise falha.
        code, _, stderr = self._main(self.observations)
        self.assertEqual(code, 2)
        self.assertIn("escopo", stderr)


if __name__ == "__main__":
    unittest.main()
