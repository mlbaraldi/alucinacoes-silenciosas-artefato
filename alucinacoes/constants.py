"""Constantes factuais do estudo, com atribuição.

A lista de modelos, de benchmarks, dos 12 tipos de alucinação e o mapa
tipo → categoria descrevem a taxonomia de Liu et al. (2026) usada pelo conjunto
de dados de origem (repositório ``code_hallucination``, arquivo ``constants.py``
da revisão citada em NOTICE.md). São fatos de domínio, não código: aqui são
redeclarados como dados para que o artefato funcione sem cópia do upstream.

Qualquer nome fora destas tabelas é tratado como desconhecido e falha fechado
durante a extração.
"""

from __future__ import annotations

SCHEMA_OBSERVATIONS = "observations/1"
SCHEMA_MANIFEST = "manifest/1"
SCHEMA_METRICS = "metrics/1"
SCHEMA_EXPECTED = "expected-metrics/1"

SCOPE_FULL_DATASET = "full_dataset"
SCOPE_UNVERIFIED = "unverified"

# Pin dos três insumos do corpus completo. O escopo só é afirmado quando os
# SHA-256 conferem; nome de diretório ou de arquivo não é evidência.
FULL_DATASET_INPUTS = {
    "metadata.jsonl": (
        "f9335b54afcf2f0d23c37b2c3dc1fe0f0bf34b1a5fa1d49fc84422cb5e73113b"
    ),
    "mapped_issues.json": (
        "c050343ec432246ddfbf66d6cd9965f117634aa75eef9488be40b398fa290544"
    ),
    "sonar_scan.log": (
        "61667575081b6b56bf5435cceb41c7b633870738ade7aa14eb6fef5afb8975e4"
    ),
}

SCOPE_BASIS_PINNED = (
    "sha256 dos três insumos confere com o pin do corpus completo"
)
SCOPE_BASIS_UNVERIFIED = (
    "sha256 dos insumos não confere com o pin; escopo não afirmado"
)

GENERATOR_NAME = "extract_observations"

# Benchmarks presentes na coluna ``dataset`` do metadata.jsonl.
DATASETS = ("CEJava", "CEPython", "HumanEval")

# Modelos geradores, como aparecem na coluna ``model``.
MODELS = (
    "codellama-7b",
    "deepseek-coder-1.3b",
    "deepseek-coder-7b",
    "deepseek-r1",
    "gpt-4",
)

# Extensão esperada do arquivo analisado por benchmark.
DATASET_EXTENSIONS = {"CEJava": "java", "CEPython": "py", "HumanEval": "py"}

# Os 12 tipos, em ordem alfabética (mesma ordem das tabelas do manuscrito).
HALLUCINATION_TYPES = (
    "Algorithm",
    "Behavior Conflicting",
    "Common Sense",
    "Computer Theory",
    "Data Conflicting",
    "Fragmented Logics",
    "Inconsistent Libraries",
    "Library/Project",
    "Mathematics & Natural Science",
    "Undefined Variables",
    "Useless Statements (executed without effect)",
    "Useless Statements (unexecuted)",
)

# Categorias: R = Requirement Conflicting, C = Code Inconsistency,
# K = Knowledge Hallucinations.
CATEGORIES = ("R", "C", "K")

CATEGORY_LABELS = {
    "R": "Requirement Conflicting",
    "C": "Code Inconsistency",
    "K": "Knowledge Hallucinations",
}

TYPE_TO_CATEGORY = {
    "Behavior Conflicting": "R",
    "Data Conflicting": "R",
    "Undefined Variables": "C",
    "Useless Statements (executed without effect)": "C",
    "Fragmented Logics": "C",
    "Inconsistent Libraries": "C",
    "Useless Statements (unexecuted)": "C",
    "Common Sense": "K",
    "Mathematics & Natural Science": "K",
    "Algorithm": "K",
    "Library/Project": "K",
    "Computer Theory": "K",
}

STATIC_PARSED = "parsed"
STATIC_PARSE_FAILED = "parse_failed"

# Allowlist de campos lidos do metadata.jsonl. Qualquer outro campo — inclusive
# `conflict-content`, `error_message`, `error_detail_message` e `project`, que
# podem carregar código gerado ou explicações — nunca é projetado para a
# observação. A projeção é estrutural: o extrator só enxerga as chaves abaixo.
METADATA_READ_FIELDS = (
    "row_number",
    "_id",
    "model",
    "dataset",
    "source_file",
    "code_labels",
    "evaluation_result",
)

# Das anotações, apenas o tipo canônico. O texto livre
# `hallucination-type-other` (que pode conter explicação em chinês) é ignorado.
LABEL_READ_FIELDS = ("hallucination-type",)

# Do resultado funcional, apenas o desfecho. Mensagens de erro e detalhes de
# compilação/execução não são lidos.
EVALUATION_READ_FIELDS = ("is_pass", "status")

# Das issues, apenas campos de identificação e contagem; `message`, `line` e
# `generation_line` não são lidos.
ISSUE_READ_FIELDS = (
    "issue_key",
    "source_file",
    "row_number",
    "model",
    "dataset",
    "sonar_type",
)

# Identificador opaco aceito para tarefa: sem espaços, chaves ou pontuação de
# código. Cobre os ObjectIds do CoderEval e os ids `HumanEval/<n>`.
TASK_ID_PATTERN = r"[A-Za-z0-9_.:/-]{1,64}"

# Proveniência declarada (NOTICE.md). Não é baixada nem lida pela extração:
# serve para amarrar o manifesto ao commit e ao arquivo de resultados citados.
UPSTREAM_DECLARED = {
    "repository": "https://github.com/Lorien1128/code_hallucination",
    "revision": "c15a328c90b2046c5751e16b79eb00ddbeace7b1",
    "result_file": "result.jsonl",
    "result_sha256": (
        "b2f7d2087a6789c7dd89a7a22fb937083f1784f1df97a3a69595b74179c84bfc"
    ),
    "note": (
        "declarado em NOTICE.md; result.jsonl não é insumo desta extração, que "
        "usa apenas a projeção publicada em full_dataset/artifacts"
    ),
    "used_as_input": False,
}


STATE_FUNCTIONAL_ONLY = "functional_only"
STATE_STATIC_ONLY = "static_only"
STATE_BOTH = "both"
STATE_NONE = "none"
STATE_INCONCLUSIVE = "inconclusive"

GATE_STATES = (
    STATE_FUNCTIONAL_ONLY,
    STATE_STATIC_ONLY,
    STATE_BOTH,
    STATE_NONE,
    STATE_INCONCLUSIVE,
)

GATE_STATE_LABELS = {
    STATE_FUNCTIONAL_ONLY: "só teste funcional",
    STATE_STATIC_ONLY: "só análise estática",
    STATE_BOTH: "teste e estático",
    STATE_NONE: "nenhum",
    STATE_INCONCLUSIVE: "inconclusivo",
}

# Faixas do histograma de issues por implementação (Figura 4 do manuscrito).
ISSUE_HISTOGRAM_BINS = (
    (0, 0, "0"),
    (1, 1, "1"),
    (2, 2, "2"),
    (3, 4, "3-4"),
    (5, None, "5+"),
)

BOOTSTRAP_SEED = 20261115
BOOTSTRAP_REPLICAS = 200000
BOOTSTRAP_QUANTILES = (0.025, 0.975)
BOOTSTRAP_QUANTILE_RULE = "values[int(q*(len(values)-1))]"
