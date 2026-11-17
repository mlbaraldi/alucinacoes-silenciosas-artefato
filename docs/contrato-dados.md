# Contrato de dados

Este documento descreve o que o artefato lê, o que ele deriva, o que ele
recusa e como os números são definidos. Ele não substitui a leitura de
[`NOTICE.md`](../NOTICE.md), que trata de proveniência e limites de uso.

## Escopo

O escopo é o conjunto completo de artefatos da análise estática
(`scope = full_dataset`): 3.120 implementações de cinco modelos em três
benchmarks, com anotações de alucinação e resultado da varredura do SonarQube.

O artefato **não** gera código com LLMs, **não** reexecuta o SonarQube e
**não** inclui o pipeline upstream de geração, extração de código ou rotulagem.
Ele consome somente três arquivos já publicados e derivados:

| Arquivo | Papel | Uso |
|---|---|---|
| `metadata.jsonl` | uma linha por implementação | identificadores, modelo, benchmark, rótulos e desfecho funcional |
| `mapped_issues.json` | uma entrada por issue do SonarQube | contagem de issues por arquivo analisado |
| `sonar_scan.log` | log do SonarScanner | quais arquivos não puderam ser analisados (parsing inconclusivo) |

Os três arquivos são tratados como **somente leitura**. O extrator não escreve,
não move e não corrige nada no diretório de origem.

A proveniência declarada fica no manifesto: revisão upstream
`c15a328c90b2046c5751e16b79eb00ddbeace7b1` e SHA-256 do `result.jsonl`
`b2f7d2087a6789c7dd89a7a22fb937083f1784f1df97a3a69595b74179c84bfc`. Nenhum
desses artefatos é baixado ou lido: `result.jsonl` não é insumo desta extração,
que usa apenas a projeção publicada em `full_dataset/artifacts`.

**Limitação declarada:** o artefato **não recomputa a varredura estática**. A
execução do SonarQube (versão, perfil de regras e configuração do scanner) não
faz parte deste pacote e exigiria infraestrutura própria; o que se reproduz é a
derivação e a agregação a partir do resultado publicado, com verificação de
hash dos três insumos.

## Allowlist de leitura (obrigatória)

O metadata contém, além dos rótulos, campos com **código e texto livre** —
`conflict-content`, `error_message`, `error_detail_message`, `project`,
`hallucination-type-other`. Por isso a leitura é uma projeção estrutural: o
extrator só enxerga as chaves abaixo, e todo o resto é descartado antes de
qualquer uso.

| Origem | Campos lidos |
|---|---|
| `metadata.jsonl` | `row_number`, `_id`, `model`, `dataset`, `source_file`, `code_labels`, `evaluation_result` |
| `code_labels[]` | `hallucination-type` |
| `evaluation_result` | `is_pass`, `status` |
| `mapped_issues.json` | `issue_key`, `source_file`, `row_number`, `model`, `dataset`, `sonar_type` |

O `task_id` precisa casar com um identificador opaco
(`[A-Za-z0-9_.:/-]{1,64}`): sem espaços, chaves ou pontuação de código. O
manifesto registra `fields_used` e `fields_ignored` do metadata, de modo que a
projeção é auditável; os testes incluem um caso adversarial com código e texto
livre nos campos descartados.

O leitor de `observations.jsonl` repete as validações do extrator: campos
exatos, tipos, valores enumerados, `task_id` no padrão opaco e `row_id` denso
de 1 a N. Um JSONL editado à mão não é aceito por totais coincidentes.

CLIs de saída (`--output`, `--manifest`) recusam caminho resolvido que
sobrescreva qualquer insumo, o manifesto, o gabarito ou outro arquivo
planejado; no extrator, também é recusado escrever dentro do diretório de
artefatos.

## O que é derivado

`scripts/extract_observations.py` produz `data/observations.jsonl` com um
registro mínimo por implementação:

| Campo | Tipo | Definição |
|---|---|---|
| `row_id` | inteiro ≥ 1 | `row_number` do metadata; denso, único e na ordem do arquivo |
| `task_id` | texto | `_id` original da tarefa; é a chave de agrupamento do bootstrap |
| `model` | texto | modelo gerador (`MODELS` em `alucinacoes/constants.py`) |
| `dataset` | texto | benchmark (`CEJava`, `CEPython`, `HumanEval`) |
| `functional_pass` | booleano | desfecho funcional normalizado (regra abaixo) |
| `static_parse_status` | texto | `parsed` ou `parse_failed` |
| `issue_count` | inteiro ≥ 0 | número de issues do SonarQube para o mesmo arquivo |
| `types` | lista | `hallucination-type` distintos, em ordem alfabética |
| `categories` | lista | categorias distintas (`R`, `C`, `K`) derivadas dos tipos |
| `annotation_count` | inteiro ≥ 0 | número de anotações (`code_labels`) da implementação |
| `type_annotations` | objeto | contagem de anotações por tipo; soma igual a `annotation_count` |

As 1.212 anotações individuais, as 1.187 associações implementação–tipo e as
1.181 associações implementação–categoria são reconstruídas a partir de
`annotation_count`, `types` e `categories`, respectivamente. Existem 53
implementações com mais de um tipo e 47 com mais de uma categoria; a diferença
de 6 entre 1.187 e 1.181 corresponde a pares de tipos da mesma categoria
colapsados na deduplicação por categoria.

Nenhum tipo é excluído: os 12 tipos da taxonomia contam, inclusive `Common
Sense` e `Inconsistent Libraries` (o `excluded_desc` do `constants.py`
upstream **não** é aplicado).

### O que nunca é copiado

Código gerado, trechos, prompts, enunciados, explicações, mensagens de erro ou
de issue, nomes de projeto, caminhos de arquivo e o log bruto do scanner. O
log é lido apenas para extrair caminhos relativos de falha de parsing, que são
comparados e descartados. Nenhuma linha do log e nenhum caminho aparecem em
`observations.jsonl` ou no manifesto.

## Normalização do desfecho funcional

1. Se `evaluation_result.is_pass` existe, ele decide; o valor precisa ser
   booleano JSON. Valor de outro tipo **falha fechado** (não há fallback).
2. Sem `is_pass`, `status` decide: `pass` aprova; `fail` e `timeout` reprovam.
   Status desconhecido **falha fechado**.
3. **Nenhum desfecho é inferido por omissão.** `evaluation_result` ausente ou
   nulo, objeto sem `is_pass` e sem `status`, ou valor indeterminado fazem a
   extração falhar fechado com `EvaluationResultError`; não existe
   "reprovação por padrão".

Falha de parsing estático não altera o desfecho funcional: são dimensões
distintas, mas a linha ainda precisa de desfecho funcional determinado. Por
isso existem implementações funcionalmente aprovadas com parsing inconclusivo
(duas no corpus completo), e uma linha inconclusiva sem desfecho funcional
seria recusada. No corpus usado, as 3.120 linhas têm desfecho determinado
(`is_pass` booleano ou `status` conhecido), por isso a regra estrita não altera
nenhum dado derivado.

## Estado da análise estática

`static_parse_status = parse_failed` quando o caminho relativo aparece no
`sonar_scan.log` como falha de parsing, reconhecendo os dois formatos
emitidos pelo scanner (`Unable to parse source file : '...'` e
`Unable to parse file: ...`). Caso contrário, `parsed`.

O log precisa provar que a execução terminou: é recusado se estiver vazio,
truncado, sem marcador de conclusão (`INFO: ANALYSIS SUCCESSFUL` /
`INFO: EXECUTION SUCCESS`) ou com marcador de falha
(`EXECUTION FAILURE`). Toda linha que anuncia falha de parsing
(`unable to parse`) precisa casar integralmente com um dos dois formatos;
linha malformada falha fechado em vez de ser silenciosamente ignorada e virar
`parsed`. Linhas de continuação (`ERROR: Parse error at line ...`) não são
tratadas como novas falhas.

`issue_count` é o número de registros de `mapped_issues.json` com o mesmo
`source_file`. Uma fonte com issues é, por definição, uma fonte analisada.

## Escopo afirmado por hash, não por nome

O manifesto só declara `scope = full_dataset` quando os SHA-256 dos três
insumos conferem com o pin do corpus completo (`FULL_DATASET_INPUTS` em
`alucinacoes/constants.py`). Caso contrário o escopo é `unverified`, com a
base registrada em `scope_basis`; nome de diretório (`full_dataset/...`) não é
evidência.

A análise adota o escopo do manifesto apenas se ele descrever o JSONL lido
(hash da saída confere) e se os hashes de entrada registrados baterem com o
pin. O gabarito é do corpus completo: se o insumo for `unverified`, a análise
recusa a comparação em vez de afirmar números do corpus completo para um
recorte diferente.

## Falhas fechadas

A extração é recusada, sem produzir saída, quando:

- um tipo de alucinação está fora da taxonomia de 12 tipos ou uma anotação não
  tem tipo;
- `is_pass` não é booleano, `status` tem valor desconhecido, ou o desfecho
  funcional está ausente/indeterminado;
- o log do scanner está vazio/truncado, sem marcador de conclusão, com marcador
  de falha, ou tem linha de falha de parsing fora dos dois formatos;
- `row_number` é duplicado, não inteiro, não denso de 1 a N ou fora de ordem;
- `source_file` é duplicado, absoluto, contém byte nulo ou tem extensão
  incongruente com o benchmark;
- modelo ou benchmark está fora do conjunto;
- uma issue aponta fonte inexistente no metadata, ou diverge em
  `row_number`/`model`/`dataset`, ou tem `issue_key` repetida, ou tem
  `sonar_type` fora de `{BUG, CODE_SMELL, VULNERABILITY}`;
- um caminho aparece ao mesmo tempo como falha de parsing e como fonte de
  issue;
- o log lista um caminho absoluto, vazio ou repetido, ou um caminho que não
  existe no metadata.

Em qualquer um desses casos a execução termina com código 2 e uma mensagem
com o contexto (sem caminho absoluto), em vez de gerar uma observação ambígua.

## Definições de agregação

- **Implementação anotada**: `types` não vazio (1.134 de 3.120).
- **Silenciosa**: anotada, `functional_pass = true`, `parsed` e
  `issue_count = 0`.
- **Estados de gate** (cinco, mutuamente exclusivos):
  `functional_only` (reprovada, sem issue), `static_only` (aprovada, com
  issue), `both` (reprovada, com issue), `none` (aprovada, sem issue) e
  `inconclusive` (parsing falho).
- **Percentuais**: uma casa decimal, arredondamento half-up.

Denominadores, por tabela:

| Tabela | Denominador de percentual |
|---|---|
| `gate_cross_corpus` | total da população/estrato e subconjunto com parsing concluído |
| `annotations_by_model` | 1.134 anotadas (coluna do total) e anotadas do modelo |
| `annotations_by_benchmark` | 1.134 anotadas e anotadas do benchmark |
| `prevalence_by_benchmark_model` | implementações do par benchmark–modelo |
| `gate_states_by_type` | implementações anotadas com o tipo |
| `gate_states_by_model_benchmark` | apenas contagens |
| `categories_summary` | associações de categoria anotadas e silenciosas |
| `types_static_summary` | "sem issue": associações com parsing concluído; "reprova" e "nenhum": associações anotadas do tipo (coluna adicional de "sem issue" também é publicada sobre anotadas) |
| `type_silencing_rate` | associações anotadas do tipo |
| `parse_histogram` | associações anotadas com parsing concluído |

Faixas do histograma de issues por implementação: `0`, `1`, `2`, `3–4` e
`5+`, iguais às da Figura 4 do manuscrito. O máximo de issues por fonte é
**14**, confirmado tanto nas 1.090 anotadas parseadas quanto no corpus completo
parseado (`max_issues_per_parsed_annotated` e `max_issues_per_parsed_corpus`
em `metrics.json`).

O bootstrap usa os 433 grupos de tarefa anotados, a semente `20261115` e
200.000 réplicas, com quantil por piso: `values[int(q*(n-1))]` para
`q = 0,025` e `q = 0,975`. A comparação com o gabarito exige
`1,3% ≤ IC ≤ 3,2%` na mesma codificação.

A execução com os parâmetros do manuscrito é o **modo completo** e exige o
gabarito existente e compatível; qualquer outra semente/réplica é **modo
parcial**, declarada como tal e sem validar o IC publicado. A saída registra o
comando real, os parâmetros efetivos, o escopo adotado e o resultado da
comparação.

## Gabarito (`expected/metrics.json`)

`expected/metrics.json` guarda **valores de referência conferidos e
independentes**: os números vêm das Tabelas 1–8 do manuscrito revisado e da
aritmética delas, não de `outputs/`. A aprovação final do status é do
orquestrador, depois da execução limpa; o arquivo não é declarado aprovado por
si. O script de análise valida a estrutura (schema, escopo, `counts`, os cinco
`gate_states`, as 13 tabelas e o histograma, com contadores e chaves
obrigatórios) e só então compara os valores. Arquivo vazio, ilegível ou
incompleto é recusado com código 2; divergência é código 1; nos dois casos
nenhum CSV ou `metrics.json` é gravado. Nada é promovido automaticamente de
`outputs/` para `expected/`.

O artefato **não afirma reprodução numérica 1:1 completa** do texto: a
varredura estática não é recomputada e a única divergência conhecida é a errata
de arredondamento descrita abaixo.

Divergências conhecidas, registradas em vez de silenciadas:

1. **Errata não corrigida no Overleaf.** A Tabela 1 do manuscrito revisado
   imprime **27,9%** para "Total Com (parseada)" do corpus completo; a
   aritmética dá `838/3.009 = 27,849%`, que arredonda para **27,8%** pela regra
   half-up. As demais células da mesma tabela conferem (26,9% no total e
   33,4%/34,8% na população anotada). O artefato usa 27,8% e mantém a diferença
   visível em `expected/metrics.json`; o documento no Overleaf **não** foi
   alterado porque a edição não foi autorizada nesta etapa.
2. O máximo de issues por implementação é **14** nas anotadas parseadas e
   também **14** no corpus completo parseado, segundo `mapped_issues.json`
   (1.426 issues em 838 arquivos).

## Taxonomia

Os 12 tipos e as 3 categorias vêm da taxonomia de Liu et al. (2026), a mesma
usada pelo conjunto de dados de origem e pelo arquivo `constants.py` do
repositório upstream. O mapa tipo → categoria é declarado como dado em
`alucinacoes/constants.py`, com atribuição em cabeçalho; nenhum código do
upstream é copiado.

## Publicação

`data/observations.jsonl`, `data/manifest.json` e `outputs/` são gerados
localmente. `outputs/` é ignorado pelo controle de versão. A publicação de
`data/` depende da revisão de licença descrita em `NOTICE.md`; o conteúdo das
observações está limitado a identificadores, rótulos, booleanos e contagens.
