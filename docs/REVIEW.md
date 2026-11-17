# Revisão e evidência de validação da versão v1.0.0

## Revisão direta pelo orquestrador

Foram lidos os caminhos de normalização, projeção dos dados, parsing,
classificação em cinco estados, denominadores, deduplicação, agrupamento por
tarefa, bootstrap, comparação com referências e comandos de execução.

Foram identificados e corrigidos antes da publicação:

1. Resultado funcional ausente não pode virar reprovação por omissão.
   `None`, objeto sem status e valor inválido agora interrompem a extração.
2. O verificador não pode remover o diretório indicado pelo usuário.
   A exclusão recursiva foi removida; diretório existente é recusado e o
   padrão usa um diretório novo.
3. Log vazio, truncado ou com falha de parsing não reconhecida não pode
   transformar ausência de evidência em parsing concluído.
4. O escopo `full_dataset` deve estar vinculado aos hashes dos insumos;
   apenas um nome de diretório ou uma declaração de escopo não basta.
5. Referência ausente/vazia não pode resultar em comparação aprovada.
   Execuções sem bootstrap completo são explicitamente parciais.
6. Saídas não devem sobrescrever entradas ou valores de referência.

O manifesto oferece rastreabilidade e detecção de alterações acidentais;
não é assinatura digital nem prova independente de que os eventos históricos
ocorreram conforme relatados.

## Execução limpa

Foi criada uma cópia independente sem `.git`, ambientes, caches ou saídas.
Nela foram executados:

```bash
python3 -m unittest discover -s tests
python3 scripts/verify_offline.py
```

Resultado: 137 testes, 6 pulados por exigirem os artefatos brutos locais.
A análise offline e o bootstrap completo passaram:

- 3.120 implementações; 1.134 anotadas.
- Cinco estados: 686 / 46 / 333 / 25 / 44.
- 1.212 anotações, 1.187 associações de tipo e 1.181 de categoria.
- 25 silenciosas únicas, 26 associações silenciosas e 22 nos quatro tipos
  mais frequentes.
- 433 grupos; semente 20261115; 200.000 réplicas; IC [1,3%; 3,2%].
- 14 tabelas CSV geradas.

Separadamente, o orquestrador reexecutou a extração com os três artefatos
originais e comparou byte a byte o JSONL resultante com o distribuído:

`5eba63e300a0bdf69dc2ca89e3d8d09b14ed8373f98df63a761ec1770f267c44`

A inspeção da projeção confirmou 3.120 linhas, apenas os campos permitidos
e ausência de código, explicações e mensagens de erro. A busca local por
padrões de tokens GitHub, chaves privadas e credenciais AWS não encontrou
ocorrências nos arquivos candidatos à publicação. Essa busca não é garantia
universal de ausência de dados sensíveis.

## Limitações e errata conhecida

A Tabela 1 do manuscrito revisado apresentava 27,9% para 838/3.009.
O cálculo com uma casa decimal resulta em **27,8%**. O artefato conserva
os números absolutos e calcula o percentual correto. A edição do manuscrito
não faz parte desta entrega.

O máximo observado no scan completo é 14 issues por implementação.
A hipótese de máximo 16 não foi confirmada nesses insumos e não foi usada.

Não foram reexecutados LLMs, testes funcionais originais ou SonarQube.
Não se afirma reprodução literal de toda a diagramação ou de todas as
expressões do manuscrito.
