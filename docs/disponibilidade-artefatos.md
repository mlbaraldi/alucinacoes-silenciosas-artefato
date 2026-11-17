# Como mencionar o artefato no artigo

## Onde inserir

Ao final da seção **Metodologia**, após a descrição da análise e do bootstrap,
acrescente uma subseção **Disponibilidade dos artefatos**. Se o modelo de
submissão exigir uma declaração específica antes das referências, use esse
local em vez de duplicar o texto.

## Texto sugerido

> Para apoiar a verificabilidade dos resultados, foi organizado um artefato
> versionado contendo observações estruturadas derivadas da execução
> `full_dataset`, scripts de análise, testes automatizados, valores de referência
> e instruções de execução. O pacote permite recalcular as métricas descritivas
> e o intervalo de confiança por bootstrap sem reexecutar a geração de código,
> os testes funcionais originais ou a análise do SonarQube. A versão utilizada
> é a v1.0.0, disponível em repositório privado, mediante concessão de acesso
> aos avaliadores: https://github.com/mlbaraldi/alucinacoes-silenciosas-artefato.
> O pacote não inclui o manuscrito nem código-fonte ou mensagens de erro dos
> exemplos analisados. A proveniência dos dados, as limitações de reprodução
> e uma errata de arredondamento identificada na conferência estão documentadas
> no repositório.

No LaTeX, use `\texttt{full\_dataset}` e
`\url{https://github.com/mlbaraldi/alucinacoes-silenciosas-artefato}`.
Consulte a tag `v1.0.0` e registre também o hash do commit na versão final
da declaração ou na referência bibliográfica. A tag identifica o estado
entregue; `main` pode receber mudanças posteriores.

Não escreva “disponível publicamente”, “acesso aberto” ou “DOI do artefato”:
o repositório é privado e não possui DOI.

## Acesso da banca

1. Solicite os nomes de usuário GitHub dos avaliadores.
2. No repositório, abra **Settings → Collaborators / Manage access**.
3. Convide as contas e confirme que aceitaram antes da defesa.
4. Envie o link da tag `v1.0.0` junto das instruções de reprodução.
5. Não compartilhe sua senha ou token. O link, isoladamente, não dá acesso.

A inclusão de colaboradores é uma ação do proprietário e não foi realizada
automaticamente na preparação deste artefato.

## Pequena correção pendente no manuscrito

Na Tabela 1, o percentual 838/3.009 deve aparecer como **27,8%**, não
27,9%. Essa é uma correção de arredondamento, sem alteração das contagens ou
das conclusões. O artigo não foi modificado nesta etapa.
