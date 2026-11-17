# Alucinações silenciosas — artefato de reprodução

Pacote de dados derivados, scripts e testes associado ao estudo de **Priscila
C. F. J. Bemm e Marcelo L. Baraldi**, da Universidade Estadual de Maringá.
O artigo e as apresentações não estão incluídos.

## O que este pacote reproduz

A partir de observações da execução **`full_dataset`**, o pacote recalcula
contagens, percentuais, cruzamentos por tipo/modelo/benchmark, coocorrências,
histograma de issues e o intervalo de confiança da proporção silenciosa.
As saídas são JSON e CSV, não a diagramação LaTeX ou as figuras do artigo.

**Não reexecuta** geração por LLM, testes funcionais ou SonarQube. Os resultados
dessas etapas são insumos históricos. Reproduzir os cálculos não constitui
validação independente das anotações ou da correção dos testes originais.

## Execução rápida

Requer Python 3.10 ou superior. O pacote usa somente a biblioteca padrão:
não exige chave de API, Docker, SonarQube, instalação de bibliotecas Python ou
acesso à rede durante a análise.

```bash
git clone https://github.com/mlbaraldi/alucinacoes-silenciosas-artefato.git
cd alucinacoes-silenciosas-artefato
python3 -m unittest discover -s tests
python3 scripts/verify_offline.py
```

O último comando inclui o bootstrap com **200.000 réplicas**, semente
**20261115** e reamostragem de **433 grupos de tarefas**. O comando informa o
diretório em que salvou os resultados. Para conferir somente a parte
descritiva, use `--skip-bootstrap`; essa execução é **parcial**.

O repositório é privado: o clone exige autenticação de uma conta com acesso.
Consulte [as instruções detalhadas](docs/execucao.md).

## Resultados de referência

| Medida | Valor |
|---|---:|
| Implementações no corpus | 3.120 |
| Implementações com alucinação anotada | 1.134 |
| Só teste funcional | 686 |
| Só análise estática | 46 |
| Ambos | 333 |
| Nenhum: implementações silenciosas | 25 |
| Parsing estático inconclusivo | 44 |
| Proporção silenciosa | 2,2% |
| IC bootstrap de 95% | [1,3%; 3,2%] |

As cinco classes somam 1.134. Os testes funcionais reprovaram **1.063**
implementações anotadas (93,7%), incluindo as 44 com parsing inconclusivo.
Por isso, 686 + 333 não é a contagem completa de reprovação funcional.

Uma **issue sinaliza a implementação**, não necessariamente sua alucinação.
Parsing concluído não significa compilação bem-sucedida. Falha de parsing não
é ausência de issue e fica em classe separada.

As **25 implementações silenciosas** geram **26 associações de tipo**.
No conjunto anotado há 1.212 anotações, 1.187 associações de tipo e 1.181
associações de categoria; essas unidades não são intercambiáveis.

## Organização

- `data/`: observações mínimas e manifesto de proveniência.
- `alucinacoes/`: normalização, extração, métricas e bootstrap.
- `scripts/`: comandos de extração, análise e verificação.
- `expected/metrics.json`: valores de referência usados nas verificações;
  não são atualizados automaticamente pelo pipeline.
- `tests/`: testes de regras e casos de erro.
- `docs/`: contrato dos dados e instruções.
- `outputs/`: resultados locais regeneráveis, fora do controle de versão.

## Dados e atribuição

Os resultados funcionais e a taxonomia têm origem em Liu et al. (2026),
*Beyond Functional Correctness: Exploring Hallucinations in LLM-Generated Code*,
DOI `10.1109/TSE.2026.3657432`, e em seu
[repositório de dados](https://github.com/Lorien1128/code_hallucination).
O manifesto registra os hashes dos artefatos locais de análise estática.

Não são distribuídos código gerado, enunciados, soluções, explicações das
anotações, mensagens de erro ou logs brutos. Leia [NOTICE.md](NOTICE.md) para
proveniência e ressalvas de licenciamento. O caráter privado do repositório não
substitui autorização nem transfere direitos de terceiros.

## Versão e uso no artigo

A revisão e as evidências da execução limpa estão em [docs/REVIEW.md](docs/REVIEW.md).
Há uma errata conhecida no manuscrito: 838/3.009 corresponde a **27,8%**
com uma casa decimal, não a 27,9%. Os scripts preservam as contagens e
calculam o percentual correto.

A versão deve ser identificada por **tag e commit**, e não apenas pelo nome da
branch. O arquivo [CITATION.cff](CITATION.cff) contém a identificação do artefato.
Instruções e texto sugerido para mencionar o pacote no artigo estarão em
`docs/disponibilidade-artefatos.md`.
