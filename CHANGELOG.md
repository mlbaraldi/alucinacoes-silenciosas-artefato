# Changelog técnico

Este arquivo registra mudanças do código do artefato. Não há release publicado;
a versão abaixo é de desenvolvimento e depende de revisão antes de qualquer
publicação.

## 0.1.0-dev — não publicado

Primeira montagem do artefato de reprodução independente.

- `scripts/extract_observations.py`: deriva `data/observations.jsonl` mínimo
  (identificador, tarefa, modelo, benchmark, desfecho funcional normalizado,
  estado de parsing, contagem de issues, tipos e categorias deduplicados) a
  partir de `metadata.jsonl`, `mapped_issues.json` e `sonar_scan.log`, com
  manifesto SHA-256 e recusas fail-closed.
- `alucinacoes/normalization.py`: precedência de `is_pass` booleano, fallback
  `status` (`pass`/`fail`/`timeout`); desfecho ausente/nulo, objeto sem as duas
  chaves, status desconhecido e `is_pass` não booleano falham fechado — sem
  reprovação inferida por omissão.
- `alucinacoes/sonar_scan.py`: reconhece os dois formatos de erro de parsing do
  log, exige marcador de conclusão (recusa log vazio/truncado ou com falha de
  execução), recusa linha `unable to parse` malformada e caminho absoluto,
  vazio ou repetido.
- `alucinacoes/metrics.py`: Tabelas 1–8 (nomes semânticos, sem índice numérico
  ambíguo), cinco estados de gate, histograma de issues `0/1/2/3–4/5+`, dedup
  de tipo e categoria, coocorrência e comparação com o gabarito.
- `scripts/bootstrap_silent_ci.py`: bootstrap agrupado por tarefa, semente
  20261115, 200.000 réplicas, quantil por piso. O modo completo exige gabarito
  existente e compatível (ausência/ilegível/incompatível → código 2 antes de
  rodar); o modo reduzido é declarado PARCIAL, sem validar o IC; o JSON registra
  comando real, parâmetros, escopo e resultado da comparação.
- `scripts/verify_offline.py`: verificação encadeada sem rede, sem git e sem
  reexecutar SonarQube. O `rmtree` foi removido: o script nunca apaga
  diretório, recusa `--workdir` existente (repositório, pai, home inclusos),
  cria subdiretório único em `outputs/` e resolve caminhos relativos contra o
  cwd original antes de rodar subprocessos.
- Escopo afirmado por SHA-256 dos três insumos (`FULL_DATASET_INPUTS`): fora do
  pin o escopo é `unverified` e a análise recusa o gabarito do corpus completo.
- Gabarito validado estruturalmente (schema, escopo, `counts` obrigatórios,
  cinco `gate_states`, todas as tabelas e histograma) e comparado **antes** de
  gravar CSV/`metrics.json`; `{}` ou arquivo ilegível → código 2 sem saída,
  divergência → código 1 sem saída.
- `expected/metrics.json`: valores de referência conferidos e independentes de
  `outputs/`, transcritos das tabelas do manuscrito revisado; status sujeito à
  aprovação do orquestrador após a execução limpa. Registra a errata pendente
  no Overleaf (27,9% impresso versus 27,8% aritmético) e não afirma reprodução
  numérica 1:1 completa.
- Guardas de caminho nas três CLIs: `--output`/`--manifest` não podem
  sobrescrever insumos, manifesto, gabarito ou o próprio par (checagem por
  caminho resolvido); o extrator também recusa escrever no diretório de
  artefatos.
- Leitor de observações repete `TASK_ID_PATTERN` e exige `row_id` denso 1..N.
- `verify_offline` sem `--artifacts` confirma o SHA-256 do JSONL contra o
  manifesto ao lado (entrada adulterada é recusada mesmo com totais iguais) e
  imprime `verificação offline completa` ou `PARCIAL`.
- `tests/`: normalização, parser do log, extração (inclusive recusas),
  definições de denominador, dedup, cinco estados, histograma, coocorrência,
  bootstrap (oráculo independente e golden), integridade do gabarito e
  integração opcional com os artefatos reais.
- Allowlist de leitura estrutural: metadata, anotações, desfecho funcional e
  issues são projetados campo a campo; `conflict-content`,
  `error_message`/`error_detail_message`, `project`, `hallucination-type-other`
  e `message` nunca são lidos. `task_id` exige identificador opaco.
- Manifesto declara a revisão upstream e o SHA-256 do `result.jsonl` citados em
  `NOTICE.md` (`used_as_input: false`) e registra `fields_used`/`fields_ignored`.
- Contadores novos: 53 implementações multi-tipo, 47 multi-categoria, 6 pares
  do mesmo tipo colapsados por categoria; máximo de issues por fonte é 14 nos
  dois recortes. Nenhum tipo é excluído (12 tipos, incluindo `Common Sense` e
  `Inconsistent Libraries`).
- `docs/contrato-dados.md` e `docs/execucao.md`: escopo, allowlist, definições,
  recusas, limites (varredura não reexecutada) e comandos.

Pendências conhecidas:

- revisão de código pelo orquestrador antes de qualquer publicação;
- definição de licença e decisão sobre publicar `data/observations.jsonl`
  (ver `NOTICE.md`);
- reprodução completa do bootstrap em ambiente limpo é executada pelo
  orquestrador; a suíte local valida apenas o universo (433/25/1.134) com
  réplicas reduzidas.
