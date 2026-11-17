# Proveniência e limites de uso

Este repositório reúne um artefato de análise associado ao trabalho de Priscila
C. F. J. Bemm e Marcelo L. Baraldi sobre alucinações silenciosas em código
gerado por modelos de linguagem. O manuscrito e as apresentações não fazem
parte desta distribuição.

## Origem dos dados

As anotações e avaliações funcionais provêm do trabalho de Liu et al.,
*Beyond Functional Correctness: Exploring Hallucinations in LLM-Generated
Code*, IEEE Transactions on Software Engineering, 2026,
DOI `10.1109/TSE.2026.3657432`, preprint `arXiv:2404.00971`.

- Repositório: <https://github.com/Lorien1128/code_hallucination>
- Revisão consultada: `c15a328c90b2046c5751e16b79eb00ddbeace7b1`.
- SHA-256 do `result.jsonl` original:
  `b2f7d2087a6789c7dd89a7a22fb937083f1784f1df97a3a69595b74179c84bfc`.

A classificação estática deriva exclusivamente da execução local denominada
`full_dataset`, com SonarQube 10, SonarScanner 5.0.1 e Java 17. A configuração
declarava Python 3.11, mas a versão efetiva usada pelo analisador foi Python
3.10. Os hashes dos insumos efetivamente usados na extração estão no manifesto
de proveniência do pacote.

O repositório upstream apresenta um badge “CC BY 4.0” em seu README, mas não
foi localizado um arquivo de licença nem uma delimitação explícita do alcance
da indicação sobre código, dados e anotações. Essa ambiguidade é registrada
aqui; não se conclui que a ausência de arquivo, por si só, invalide a indicação
ou que autorize qualquer forma de redistribuição.

Os benchmarks subjacentes incluem:

- HumanEval: <https://github.com/openai/human-eval>, com licença MIT.
- CoderEval: <https://github.com/CoderEval/CoderEval>; não foi localizado
  um arquivo de licença na consulta realizada.

## O que é distribuído

A seleção de dados é limitada a observações estruturadas: identificadores,
categorias e tipos, resultados funcionais normalizados, estado de parsing e
contagens de issues. Não são incluídos código gerado, soluções de referência,
enunciados, explicações textuais das anotações, mensagens de erro, tokens ou
logs brutos. Isso reduz a exposição de conteúdo de terceiros, sem constituir
parecer jurídico sobre os direitos aplicáveis a bases de dados ou derivados.

Os scripts deste pacote implementam o procedimento de análise; não incluem o
pipeline upstream de geração por LLM. A atribuição aos autores dos dados e da
taxonomia deve ser preservada.

## Compartilhamento e licença

O repositório é privado e destinado à revisão acadêmica. A visibilidade privada
não elimina obrigações de atribuição, licenciamento ou autorização.

Nenhuma nova licença de redistribuição de conteúdo de terceiros é concedida
por este pacote. Também não se aplica automaticamente o badge upstream ao
código novo. Uma licença pública para o artefato deverá ser definida pelos
autores antes de eventual abertura do repositório.

## Limite de reprodução

Reproduzir métricas a partir das observações distribuídas é diferente de
reexecutar geração, testes funcionais ou o scan do SonarQube. Os resultados
de tais etapas são insumos históricos desta análise. O extrator permite
reconstruir as observações quando os artefatos originais do scan estão
disponíveis, mas eles não são redistribuídos aqui.
