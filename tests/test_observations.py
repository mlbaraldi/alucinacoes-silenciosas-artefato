"""Schema das observações no lado da leitura: padrão de task_id e densidade."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import support

from alucinacoes.observations import (
    ObservationSchemaError,
    load_observations,
)


class LoaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _payloads(self, row_ids: list[int]) -> list[dict]:
        return [
            support.observation_payload(
                row_id=row_id, task_id=f"t{row_id}", types=["Algorithm"]
            )
            for row_id in row_ids
        ]

    def test_aceita_row_id_denso(self) -> None:
        path = support.write_observations(
            self.root / "obs.jsonl", self._payloads([1, 2, 3])
        )
        self.assertEqual(len(load_observations(path)), 3)

    def test_recusa_row_id_nao_denso(self) -> None:
        path = support.write_observations(
            self.root / "obs.jsonl", self._payloads([1, 3])
        )
        with self.assertRaises(ObservationSchemaError) as caught:
            load_observations(path)
        self.assertIn("denso", str(caught.exception))

    def test_recusa_row_id_fora_de_ordem(self) -> None:
        path = support.write_observations(
            self.root / "obs.jsonl", self._payloads([2, 1])
        )
        with self.assertRaises(ObservationSchemaError):
            load_observations(path)

    def test_recusa_task_id_fora_do_padrao_opaco(self) -> None:
        for bad in ("tarefa com espaco", "task{1}", "a;b", "x" * 65):
            with self.subTest(task_id=bad):
                payload = support.observation_payload(row_id=1, task_id=bad)
                path = support.write_observations(self.root / "obs.jsonl", [payload])
                with self.assertRaises(ObservationSchemaError) as caught:
                    load_observations(path)
                self.assertIn("padrão opaco", str(caught.exception))

    def test_aceita_human_eval_e_objectid(self) -> None:
        payloads = [
            support.observation_payload(row_id=1, task_id="HumanEval/140"),
            support.observation_payload(row_id=2, task_id="636767191a6d9265ec017c0f"),
        ]
        path = support.write_observations(self.root / "obs.jsonl", payloads)
        self.assertEqual(len(load_observations(path)), 2)


if __name__ == "__main__":
    unittest.main()
