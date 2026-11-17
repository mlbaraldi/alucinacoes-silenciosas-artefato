# Execução

Procedimentos técnicos do artefato. Todas as etapas rodam offline, sem rede,
sem `git` e sem reexecutar o SonarQube ou qualquer modelo de linguagem.

## Requisitos

- Python 3.11 ou superior (testado em 3.14).
- Apenas biblioteca padrão. Não há dependências de terceiros: `requirements.txt`
  documenta essa ausência. Gráficos e notebooks não fazem parte deste pacote.

## 1. Extrair as observações

```bash
python scripts/extract_observations.py \
    --artifacts "<ARTIFACTS_DIR>" \
    --output data/observations.jsonl
```

`<ARTIFACTS_DIR>` deve conter `metadata.jsonl`, `mapped_issues.json` e
`sonar_scan.log` (por exemplo, o diretório `full_dataset/artifacts` do
repositório de origem). O manifesto sai em `data/manifest.json` por padrão;
use `--manifest` para outro caminho.

`--output` e `--manifest` não podem apontar para os três insumos, para o mesmo
arquivo entre si, nem para dentro do diretório de artefatos (somente leitura):
o comando recusa com código 2 antes de escrever qualquer coisa.

Saída esperada: `scope=full_dataset`, `scope_basis=...pin...`,
`rows=3120 annotated=1134 clusters=433 annotations=1212 type_assoc=1187
category_assoc=1181 issues=1426 parse_failures=111`, seguida dos SHA-256 dos
três insumos e da saída.

O escopo só é `full_dataset` quando os três hashes conferem com o pin do
corpus; qualquer outra cópia (ou diretório apenas chamado `full_dataset`) sai
como `unverified` e a análise com o gabarito é recusada.

O manifesto registra `fields_used`/`fields_ignored` do metadata (allowlist
estrutural), a revisão upstream e o SHA-256 do `result.jsonl` declarado em
`NOTICE.md` (`used_as_input: false`), além das contagens de sobreposição: 53
implementações multi-tipo, 47 multi-categoria e 6 pares do mesmo tipo
colapsados por categoria.

## 2. Calcular as tabelas

```bash
python scripts/analyze_observations.py \
    --input data/observations.jsonl \
    --output outputs
```

Gera `outputs/metrics.json` e um CSV por tabela. Antes de escrever qualquer
arquivo, o gabarito é **validado estruturalmente** (schema, `scope`, seções
`metrics.counts`, `metrics.gate_states`, `metrics.tables` e
`metrics.parse_histogram` preenchidas, contadores e tabelas obrigatórias,
estados de gate completos) e **comparado** célula a célula: gabarito inválido
ou ilegível termina com código 2, divergência termina com código 1, e em ambos
os casos nada é criado em `--output` — não existe saída "aparentemente
validada" depois de falha. Um arquivo `{}` é recusado. `--skip-expected` existe
apenas para depuração e não deve ser usado em verificação.

A saída não pode sobrescrever `--input`, `--expected` nem o manifesto: se
`--output` for o diretório do gabarito (por exemplo `expected/`), a execução é
recusada com código 2 antes de criar qualquer arquivo.

## 3. Reproduzir o intervalo de confiança

```bash
python scripts/bootstrap_silent_ci.py \
    --input data/observations.jsonl \
    --output outputs/bootstrap_silent_ci.json
```

Saída esperada: `clusters=433 silent=25 total=1134`,
`seed=20261115 replicas=200000 ci=1.3,3.2`, `modo=completo`, `expected: OK`.

Política do gabarito:

- **modo completo** (semente 20261115 **e** 200.000 réplicas, os parâmetros do
  manuscrito) exige `expected/metrics.json` existente, legível e com seção
  `bootstrap` compatível; ausência, arquivo ilegível ou parâmetros divergentes
  encerram com código 2 **antes** de rodar;
- **modo parcial** (qualquer outro `--seed`/`--replicas`) é impresso como
  `modo=parcial` + linha `PARCIAL`, grava
  `expected.verified=false` com o motivo e **não** valida o IC do manuscrito;
- o JSON de saída registra o comando real (semente e réplicas efetivas), os
  parâmetros, o escopo adotado e o resultado da comparação.

O bootstrap padrão leva cerca de 20 segundos. O arquivo de saída não pode
sobrescrever o JSONL de entrada nem o gabarito (código 2).

## 4. Verificação completa

```bash
python scripts/verify_offline.py --artifacts "<ARTIFACTS_DIR>"
```

Encadeia extração, análise e bootstrap e falha no primeiro passo com problema.
Sem os artefatos de origem, use `--observations data/observations.jsonl`.
`--skip-bootstrap` executa apenas extração e análise.

Regras do diretório de trabalho — o script **nunca apaga nada**:

- sem `--workdir`, cria um subdiretório único em `outputs/` (ignorado pelo
  controle de versão) e o informa na saída;
- `--workdir` precisa apontar para caminho **inexistente**; caminho existente
  (repositório, diretório pai, home ou qualquer pasta do usuário) é recusado
  com código 2 e nada é removido;
- caminhos relativos da linha de comando são resolvidos contra o diretório
  corrente original, antes de os subprocessos rodarem com `cwd` no repositório;
- quando `--artifacts` é usado, a análise recebe o manifesto da extração e o
  escopo vem dos hashes registrados;
- sem `--artifacts`, o JSONL precisa ter `manifest.json` ao lado e o SHA-256
  precisa coincidir com o registrado; entrada adulterada é recusada (mesmo que
  os totais permaneçam iguais) e escopo diferente de `full_dataset` também.

A última linha da execução distingue o que foi verificado:
`verificação offline completa` (extração, análise e bootstrap com 200.000
réplicas) ou `verificação offline PARCIAL` (bootstrap não executado ou com
réplicas reduzidas).

## 5. Testes

```bash
python -m unittest discover -s tests -v
```

A suíte principal é autocontida (fixtures sintéticas). O módulo de integração
com os artefatos reais é ignorado, a menos que a variável abaixo esteja
definida:

```bash
ALUCINACOES_ARTIFACTS_DIR="<ARTIFACTS_DIR>" python -m unittest discover -s tests
```

## Arquivos gerados

| Arquivo | Conteúdo | Tabela do manuscrito |
|---|---|---|
| `gate_cross_corpus.csv` | cruzamento funcional × estático nas populações anotada e completa | Tabela 1 |
| `annotations_by_model.csv` | anotadas e silenciosas por modelo | Tabela 2 |
| `annotations_by_benchmark.csv` | anotadas e silenciosas por benchmark | derivada da Tabela 8 |
| `prevalence_by_benchmark_model.csv` | taxa de anotação por par benchmark–modelo | Figura 3 |
| `gate_states_by_type.csv` | cinco estados por tipo de alucinação | Tabela 7 |
| `gate_states_by_model_benchmark.csv` | cinco estados por modelo e benchmark, com total | Tabela 8 |
| `gate_states_by_model.csv` | cinco estados por modelo | derivada da Tabela 8 |
| `gate_states_by_benchmark.csv` | cinco estados por benchmark | derivada da Tabela 8 |
| `categories_summary.csv` | associações anotadas e silenciosas por categoria | Tabela 3 |
| `types_static_summary.csv` | anotadas, parseadas, sem issue, reprovação e nenhum por tipo | Tabela 4 |
| `type_composition_silent.csv` | composição das anotadas e das silenciosas por tipo | Tabela 5 |
| `type_silencing_rate.csv` | taxa de silenciamento por tipo | Tabela 6 |
| `parse_histogram.csv` | distribuição de issues por implementação anotada parseada | Figura 4 |
| `type_cooccurrence.csv` | coocorrência de pares de tipos | texto da Tabela 5 |
| `metrics.json` | todas as tabelas, contadores, estado de gate e proveniência | — |

`outputs/` é ignorado pelo controle de versão. `expected/` é somente leitura
para os scripts e contém valores de referência conferidos; o status final da
reprodução é aprovado pelo orquestrador depois da execução limpa.

## Limites da reprodução

- A varredura estática não é reexecutada: o SonarQube, o perfil de regras e a
  configuração do scanner não fazem parte do pacote. O que se verifica é a
  derivação a partir do resultado publicado e o hash dos três insumos.
- O log precisa conter evidência de execução concluída; log vazio, truncado ou
  com falha de execução é recusado.
- O máximo de issues por fonte é 14, nas anotadas e no corpus completo.
- O bootstrap completo (200.000 réplicas) é a etapa mais longa; `--replicas`
  reduzido serve apenas para fumaça e não valida o IC.
- O desfecho funcional não tem valor padrão: ausência/indeterminação recusa a
  extração em vez de gerar reprovação.

## Interpretação dos erros

- Código 1 em `analyze_observations.py`: divergência contra o gabarito; a
  mensagem indica tabela, chave e campo.
- Código 2 em `extract_observations.py`: artefato incongruente (ver a lista de
  falhas fechadas em `docs/contrato-dados.md`).
- Código 2 em `bootstrap_silent_ci.py`: universo vazio ou parâmetros
  inválidos.

Nenhum código de erro indica retentativa automática: corrigir a causa e rodar
de novo é decisão do operador.
