# Spec: modelo de estimativa de faixa salarial

**Issue:** #4, dividida nas sub-issues #51 (preparo, baseline e MLflow), #52 (modelo, conformal e go/no-go) e #53 (`estimar_faixa`). **Relacionadas:** #5 (equidade, usa as métricas por grupo daqui), #11 (agente salarial, consome o modelo depois), #3 (EDA, PR #28 ainda aberto).
**Base:** página [Modelo salarial](https://github.com/ArtemisHubApp/artemishub_docs/blob/main/docs/arquitetura/modelo-salarial.md) do `artemishub_docs` (commit `e45cb65`), aprovada como caminho em 22/11.
**Tamanho:** S3. Modelo de ML novo, com atributos sensíveis no treino, critério de go/no-go e mudança no que o agente salarial vai responder.

## Intenção

Dar à usuária uma faixa salarial de referência para o perfil dela (ocupação, UF, escolaridade, experiência) que **não repita a desigualdade** da RAIS. O modelo separa o efeito de sexo e raça do efeito do perfil e mostra duas faixas: a do mercado hoje e a de referência, que é o que o mercado paga ao grupo de referência com o mesmo perfil. A diferença entre as duas é o argumento da usuária na negociação.

## Objetivos, não objetivos e anti-objetivos

**Objetivos**

- Baseline (mediana por ocupação e UF) e modelo quantílico treinados e avaliados na RAIS STEM 2025.
- MAE do modelo pelo menos 15% menor que o do baseline (go/no-go) e cobertura do intervalo de previsão de 80% ≥ 80% no teste.
- MAE, MAPE, R² (em ln) e cobertura registrados no MLflow, junto com as métricas por sexo × raça para a #5.
- Função `estimar_faixa` que devolve as duas faixas prontas para o agente explicar.

**Não objetivos**

- Ligar o modelo ao grafo do agente (#11). A função fica pronta para entrar atrás da porta `ConsultaSalarial`, mas a troca é outra issue: a **#54**, que também põe a jornada, a experiência e a escolaridade nos `Parametros` do agente (hoje eles não têm esses dados).
- O critério de equidade (≤ 5 p.p. de diferença no erro entre grupos). Isso é da #5; aqui só registramos as métricas por grupo.
- Versionar o modelo treinado no DVC. Ainda não existe remote (DagsHub, plano de CI/CD) e o DVC não roda na worktree.
- Validação ano a ano, porque só temos 2025 (ver Limitações).

**Anti-objetivos** (o que faria a entrega falhar mesmo funcionando)

- Sexo ou raça da usuária mudarem o valor que ela vê. Nenhuma função pública recebe sexo nem raça da usuária (RNF-14).
- A faixa de referência ser vendida como "o quanto você vale". Ela é um piso conservador e a resposta precisa dizer isso.
- Mostrar um número de um recorte com pouquíssimas pessoas sem avisar.

## Abordagens consideradas

| | Abordagem | Prós | Contras |
|---|---|---|---|
| A | **Modelo cego:** sexo e raça fora do treino, usados só na #5 | Simples. Segue o RNF-14 ao pé da letra. | A desigualdade entra pelas outras variáveis, só que sem aparecer. Não dá para mostrar a faixa "sem a diferença". |
| **B** | **Oaxaca-Blinder:** sexo e raça no treino, fixados num grupo de referência na previsão | Separa o efeito da discriminação do efeito do perfil e entrega a faixa de referência que a tela Salário pede. | Mais trabalho. Depende da escolha do grupo de referência. |

**Escolhida: B** (Ana Julia, 22/11), como está na página de arquitetura. Sexo e raça entram no treino para medir o efeito deles. Na previsão, ficam fixos, e por isso nunca são dados da usuária.

## Decisões da Ana Julia (22/11)

1. Seguir a página `arquitetura/modelo-salarial.md` (abordagem B).
2. **Grupo de referência** configurável, com **homem branco** como padrão (é a referência da EDA). Ainda vai ser confirmado com o grupo.
3. **Sem validação ano a ano.** O treino e o teste são divisões dentro de 2025, e isso fica registrado como limitação.
4. **Salário por hora e correção pelo IPCA**, como na página. O tratamento do IPCA com um ano só está abaixo.
5. Se passar de uns 400 linhas, dividir em PRs menores (ver Entrega em PRs), com três sub-issues da #4 marcadas como semana-3.
6. **Experiência entra no modelo desde o PR 2**, com a idade como base (ver Variáveis).
7. **A ferramenta recebe a jornada da usuária.** É isso que permite usar a jornada real na avaliação (ver Avaliação).
8. **A usuária vê a faixa P25–P75.** O intervalo de 80% serve só para o critério. A cobertura real do P25–P75 também vai para o MLflow.
9. **A faixa de mercado é a das mulheres de todas as raças**, sem perguntar a raça. Como contexto, a resposta mostra a diferença por raça já agregada (nacional ou regional), e não uma faixa por perfil. Ainda vai ser confirmado com o grupo.

## Dados

Fonte: `data/processed/rais_stem_2025_brasil.parquet` (2.478.804 vínculos; dicionário em `docs/dicionario_dados_rais.md`). Lido em 22/11:

- Sem faltantes, exceto `horas_contratuais` (4,74%) e `cbo_nome` (0,01%, não usado).
- Jornada: mediana de 44 h, 5,9% abaixo de 40 h e 0,15% abaixo de 10 h.
- 271 ocupações (CBO de 6 dígitos), 65 famílias, 27 UFs e 87 divisões da CNAE.
- Menor célula de sexo × raça: mulheres indígenas (786 vínculos).

**Preparo**

1. **Jornada ausente (4,74%):** imputar com a mediana de `horas_contratuais` da CBO × UF no treino (ou da CBO, se a célula tiver menos de 30) e marcar `jornada_imputada = True`. A marcação não é variável do modelo, porque a ferramenta não tem esse dado; ela serve para registrar as métricas com e sem esses vínculos. Tirá-los apagaria um grupo bem pago e desigual entre grupos (ver Riscos para a #5). *Minha decisão.*
2. **Jornada abaixo de 10 h semanais (0,15%):** sai do treino e do teste, porque gera valores por hora absurdos. *Minha decisão.*
3. Salário por hora = `remuneracao_media / (horas_contratuais × 52/12)`. Alvo: `ln(salário por hora)`.
4. **Experiência potencial** = `max(0, idade − anos_de_estudo − 6)`, a definição de Mincer (1974): quem começou a estudar aos 6 anos e não parou de trabalhar desde que saiu da escola. Os anos de estudo vêm de `config/anos_estudo.csv`, convertidos das faixas de escolaridade da RAIS:

   | Código RAIS | Escolaridade (layout RAIS) | Anos de estudo | Por quê |
   |---:|---|---:|---|
   | 1 | Analfabeto | 0 | |
   | 2 | Até o 5º ano incompleto do fundamental | 2 | ponto médio de 0 a 4 |
   | 3 | 5º ano completo do fundamental | 5 | |
   | 4 | Do 6º ao 9º ano incompleto do fundamental | 7 | ponto médio de 6 a 8 |
   | 5 | Fundamental completo | 9 | ensino fundamental de 9 anos |
   | 6 | Médio incompleto | 10 | ponto médio de 10 a 11, arredondado para baixo |
   | 7 | Médio completo | 12 | 9 + 3 |
   | 8 | Superior incompleto | 14 | ponto médio de 13 a 15 |
   | 9 | Superior completo | 16 | 12 + 4 (bacharelado típico; engenharias de 5 anos ficam com 1 ano a mais de experiência potencial) |
   | 10 | Mestrado | 18 | 16 + 2 |
   | 11 | Doutorado | 22 | 18 + 4 |

   Faixas incompletas usam o ponto médio dos anos possíveis, a mesma lógica dos "anos de estudo" do IBGE. Os códigos foram conferidos no parquet (`escolaridade_codigo` × `escolaridade`). *Os valores são decisão minha; a tabela fica no `config/` para a equipe ajustar.*
5. Divisão aleatória com semente fixa: **70% treino, 10% calibração, 20% teste**. Dentro do treino, 10% servem para a parada antecipada do LightGBM. O baseline usa a mesma divisão.

**Variáveis**

| Papel | Variáveis |
|---|---|
| Perfil, o f(·) da página | `cbo` (categórica, 6 dígitos), `uf` (categórica), `escolaridade_codigo` (ordinal), `experiencia_potencial` (anos), `tempo_emprego_meses`, `cnae_divisao` (2 primeiros dígitos de `cnae_classe`, categórica), `tamanho_estabelecimento` (ordinal, 1 a 10) |
| Grupo, o g(·) da página | `sexo`, `raca_cor` (categóricas, com `nao_identificado` como categoria) |
| Fora | `idade` crua (só entra pela experiência potencial), `tipo_contrato` (a usuária não sabe responder no chat) e `municipio` (muitas categorias e recortes pequenos). *Minha decisão.* Se der no-go, o tipo de contrato é o próximo teste. |

**Por que experiência potencial e não a idade crua.** A idade é o substituto da experiência na RAIS, e por isso entra no modelo. Só que a Constituição (art. 7º, XXX) proíbe diferença de salário por idade no mesmo inciso que proíbe por sexo e cor. Com a idade crua, a ferramenta precisaria perguntar a idade da usuária, e a idade dela mexeria no valor dela. A experiência potencial guarda quase a mesma informação no treino (dada a escolaridade, é a idade deslocada) e, na previsão, vem da **experiência que a usuária informa, em anos**, que é o que a issue pede. A idade dela nunca é perguntada.

As interações com CBO e UF que a página pede ficam por conta das árvores do LightGBM, sem termos explícitos.

## Modelo

- **Regressão quantílica com LightGBM** (API nativa, `objective="quantile"`), com um modelo para cada quantil: **0,10; 0,25; 0,50; 0,75; 0,90**, sobre `ln(salário por hora)`. Se os quantis se cruzarem, eles são ordenados por linha.
- **Conformal (CQR, Romano et al. 2019)** no conjunto de calibração, em escala log. O par (q10, q90) é calibrado para 80% e o par (q25, q75) para 50%. A calibração é **separada por sexo × raça** (Mondrian), como diz a página, para a cobertura ficar parecida entre os grupos. Grupo com menos de 500 vínculos na calibração usa a calibração do sexo. *O limite de 500 é decisão minha.*
- **Experimentos registrados:** baseline e LightGBM quantílico. Se der tempo, um OLS minceriano como segunda referência (R² de 0,43 na EDA).
- Os hiperparâmetros ficam para quem implementar, com parada antecipada. O que for escolhido vai para o MLflow.

## Avaliação (modo factual)

Tudo no conjunto de teste, prevendo com o sexo e a raça verdadeiros, como diz a página. A faixa de referência não entra nas métricas.

- **Baseline:** mediana da `remuneracao_media` mensal por **CBO de 6 dígitos × UF** no treino. Se a célula tiver menos de 30 vínculos, usa a mediana nacional da CBO (o mesmo `N_MINIMO` de `src/salarios.py`). Escolhi CBO, e não família, porque é a leitura literal de "ocupação" e dá o baseline mais forte. Numa divisão exploratória 80/20 de 22/11, o baseline teve **MAE de R$ 3.609 e MAPE de 59%**, então a meta fica em torno de **MAE ≤ R$ 3.068**.
- **Previsão mensal do modelo:** P50 por hora × `horas_contratuais × 52/12` do próprio vínculo. A comparação é em reais por mês, como o critério. **Isso só é justo porque `estimar_faixa` recebe a jornada semanal da usuária** (`horas_semanais`): na avaliação, o modelo usa o mesmo dado que vai ter em produção. Se um dia a ferramenta deixar de receber a jornada, a avaliação principal passa a ser a do cenário "sem jornada" abaixo.
- **Cenário sem jornada** (registrado, não decide o go): P50 por hora × mediana da jornada da CBO × UF. Mostra quanto se perde quando a usuária não informa a jornada. Também registro um "baseline por hora" (mediana por hora × jornada) como referência.
- **Métricas:** MAE, MAPE, R² em ln, cobertura do intervalo de 80% (critério ≥ 80%), cobertura do P25–P75 (a faixa que a usuária vê) antes e depois da calibração, e largura média dos intervalos. Tudo no geral, por sexo × raça, e com e sem os vínculos de jornada imputada.
- **Go/no-go:** `ganho_mae = 1 − MAE_modelo / MAE_baseline ≥ 0,15` **e** cobertura 80% ≥ 0,80. A meta de R² de 0,55 a 0,65 entra só como referência, porque ainda está em revisão no PR #28.
- **Se der no-go:** o PR 2 é mergeado mesmo assim, com os experimentos registrados, e a gente conversa antes do PR 3. Um teste cru (mediana por CBO × UF × escolaridade) só ganhou 2,5%, então os 15% não estão garantidos. *Minha decisão.*

## Faixas e `estimar_faixa`

```python
estimar_faixa(
    cbo: str,                          # 6 dígitos
    uf: str,
    escolaridade: str,                 # mesmos valores de `escolaridade` no dicionário
    experiencia_anos: float,           # experiência na carreira; vira experiencia_potencial
    horas_semanais: float | None = None,  # jornada contratada; sem ela, só a base de 40 h
    tempo_empresa_anos: float | None = None,  # vira tempo_emprego_meses
    setor: str | None = None,          # divisão da CNAE (2 dígitos)
    porte: str | None = None,          # faixa de tamanho do estabelecimento
    mes_referencia: str | None = None, # "AAAA-MM"; padrão: último mês do IPCA disponível
) -> EstimativaFaixa
```

- **Faixa de mercado:** quantis calibrados previstos para **mulheres** com o perfil informado. Como a função não recebe a raça da usuária, as previsões por raça são combinadas com pesos iguais à distribuição nacional de raça entre as mulheres no treino (média ponderada dos quantis em log, que é uma aproximação). *Minha decisão; ver pergunta 2.*
- **Faixa de referência:** quantis calibrados para o **grupo de referência** configurado, com o padrão `("masculino", "branca")` em `config/`. Aceita `("masculino", "todas")`, que combina as raças dos homens do mesmo jeito.
- **Diferença:** `p50_referencia / p50_mercado − 1`, em %.
- **Setor, porte e tempo de empresa ausentes:** usa o valor mais comum (a mediana, no caso do tempo de empresa) da CBO × UF no treino, guardado numa tabela que acompanha o modelo. *Minha decisão.*
- **Valores mensais:** sempre na base de 40 h (valor por hora × 40 × 52/12), como na página. Com `horas_semanais`, a saída traz também a faixa na jornada da usuária, que é com quem o salário informado deve ser comparado. Sem a jornada, a resposta avisa que a comparação com o salário informado supõe 40 h.
- **IPCA:** ver a próxima seção.
- **Diferença por raça como contexto:** uma tabela agregada, `data/agregados/diferenca_raca_<ano>.csv`, gerada no treino. Para cada família da CBO × região (N, NE, CO, SE, S) e Brasil, traz a diferença bruta entre a mediana por hora (base de 40 h) das mulheres de cada raça e a do grupo de referência. Uma célula só é publicada com pelo menos 30 vínculos em cada lado. É o `N_MINIMO` de `src/salarios.py`, mais rígido que k ≥ 10. A ferramenta mostra a linha da região da UF e, se faltar, a do Brasil. Não é uma faixa por perfil. **Na interface, o bruto tem que estar explícito:** o campo se chama `diferenca_bruta_por_raca`, cada linha carrega `tipo: "bruta"`, e o aviso fixo que vai junto diz que a diferença "compara medianas sem controlar ocupação exata, escolaridade, experiência ou jornada; não é a diferença para o seu perfil". A Validação do agente já reprova diferença sem o aviso de bruta. Na integração (#54), essa regra passa a valer também para esse campo. *Usar a diferença bruta, a região e o mínimo de 30 é decisão minha.*
- **Saída:** P25, P50 e P75 das duas faixas (só estas são mostradas à usuária), diferença, diferença por raça agregada, grupo de referência, mês de referência e fator do IPCA, base de 40 h (e a jornada da usuária, quando informada), fonte ("RAIS Vínculos 2025, MTE/PDET"), ano e avisos. Os avisos são fixos: a referência é um piso conservador, a experiência do treino é potencial (idade menos anos de estudo), só emprego formal privado, e há poucos dados quando a CBO × UF tem menos de 30 vínculos no treino. O intervalo de 80% não sai na resposta.
- Os sexos e raças possíveis são os do treino. Valor desconhecido de CBO, UF ou escolaridade gera erro explícito.

## IPCA com um ano só

- **No treino e nas métricas, nada é corrigido.** Todos os vínculos são de 2025, e a `remuneracao_media` já é uma média mensal em reais nominais de 2025. O MAE sai em "R$ de 2025".
- **Na saída**, o valor é levado ao mês de referência por `fator = IPCA(mês_ref) / média do número-índice IPCA de jan a dez/2025`. Usei a média do ano como base porque a remuneração média também é uma média ao longo do ano.
- O número-índice vem da tabela 1737 do SIDRA/IBGE e fica num CSV pequeno em `config/ipca_numero_indice.csv`, atualizado à mão. Nada é baixado em tempo de execução. Se o mês pedido for depois do último do CSV, usa o último e avisa.
- **Limitação:** a inflação dentro de 2025 é ignorada (quem só trabalhou em dezembro tem preços de dezembro). Quando a RAIS 2026 chegar, os dois anos são deflacionados para a mesma base, e a validação ano a ano passa a ser possível.

## MLflow

- Experimento `modelo-faixa-salarial`, com uma execução para o baseline e uma para cada modelo.
- Endereço em `MLFLOW_TRACKING_URI` (no `.env.example`). Padrão local: `sqlite:///mlflow.db`, com os artefatos em `mlruns/`, os dois no `.gitignore`. Um servidor compartilhado (o DagsHub também oferece MLflow) fica para quando o remote do DVC existir.
- **Parâmetros:** variáveis, quantis, semente, proporções da divisão, filtros, grupo de referência, hiperparâmetros e o md5 do parquet (lido do `.dvc`).
- **Métricas:** todas da seção Avaliação, gerais e por sexo × raça, mais `ganho_mae` e `go` (0 ou 1).
- **Artefatos:** os modelos LightGBM, as margens do conformal por grupo, os pesos de raça, a tabela de valores padrão por CBO × UF (setor, porte, tempo de empresa e jornada) e a tabela de diferença por raça.
- O treino também salva o mesmo pacote em `models/faixa_salarial_2025/` (no `.gitignore`), que é de onde `estimar_faixa` lê.

## Código

Pacote novo `src/modelo_salarial/`, nas camadas do `codigo-limpo.md` e no mesmo formato de `src/agentes/`:

- `domain/`: tipos (`Perfil`, `Faixa`, `GrupoReferencia`, `EstimativaFaixa`) e regras puras: salário por hora, conversão para 40 h, fator do IPCA e combinação de quantis por pesos. Nada de I/O.
- `application/`: portas (`RegressorQuantilico`, `RegistroDeExperimentos`, `IndiceDePrecos`) e casos de uso: preparar, baseline, treinar e avaliar, calibrar e estimar a faixa. As métricas e o conformal usam numpy e pandas.
- `adapters/`: LightGBM, MLflow, leitura do parquet, CSV do IPCA e a CLI.
- **CLI:** `uv run python -m src.modelo_salarial treinar` (baseline e modelo, com registro no MLflow e o go/no-go na tela) e `uv run python -m src.modelo_salarial estimar --cbo 212405 --uf DF --escolaridade superior_completo --experiencia 5`.
- `src/salarios.py` e `ConsultaRais` não mudam.

## Testes (antes do código)

Só com dados sintéticos pequenos, gerados no teste. Nenhum dado real da RAIS em fixture (LGPD).

- Preparo: a imputação da jornada (CBO × UF, com recurso à CBO) e a marcação, o filtro de menos de 10 h, a conta do salário por hora e a da experiência potencial (incluindo o piso em 0); a divisão é reprodutível com a semente.
- Baseline: mediana por CBO × UF e recurso à CBO nacional quando a célula tem menos de 30.
- Métricas: MAE, MAPE, R² e cobertura em casos feitos à mão.
- Conformal: em dados sintéticos com ruído conhecido, a cobertura de teste fica perto da nominal; grupo pequeno usa a calibração do sexo.
- `estimar_faixa`: a assinatura não tem sexo, raça nem idade; trocar o grupo de referência muda só a faixa de referência; com `horas_semanais`, a faixa na jornada é a de 40 h × horas/40; uma célula de diferença por raça abaixo de 30 vínculos não aparece; o fator do IPCA e a base de 40 h dão os valores esperados; CBO desconhecida gera erro; recorte pequeno gera aviso.
- Go/no-go calculado certo nos dois lados do limite.
- Um teste ponta a ponta treina num dataset sintético minúsculo, com o MLflow apontando para uma pasta temporária.

## Dependências e ADR

- `lightgbm` nas dependências principais, porque `estimar_faixa` precisa dele. `mlflow` num grupo de dependências `ml`, porque só o treino usa. Sem scikit-learn: a divisão e as métricas são curtas.
- **ADR-012 (rascunho no `artemishub_docs`):** LightGBM quantílico com CQR, MLflow para os experimentos e a abordagem de Oaxaca-Blinder com o grupo de referência configurável. A equipe aprova no PR.

## Docs a atualizar

- `artemishub_agents`: README (comandos de treino e estimativa, `MLFLOW_TRACKING_URI`) e `docs/` com uma página curta sobre o modelo e os resultados.
- `artemishub_docs`: página `arquitetura/modelo-salarial.md` (grupo de referência configurável com homem branco como padrão, divisão dentro de 2025 como limitação, como o IPCA é tratado, os números reais no lugar do exemplo inventado), ADR-012 e a tabela de `docs/adr/index.md`. O R² em `metricas.md` fica como está até o PR #28 fechar.

## Entrega em PRs

Passa de 400 linhas, então proponho dividir. Cada PR leva os testes dele.

| PR | Repo | Conteúdo | Tamanho estimado |
|---|---|---|---|
| PR | Issue | Conteúdo | Tamanho estimado |
|---|---|---|---|
| 1 | #51 | Spec e plano, preparo dos dados (imputação da jornada, experiência potencial), baseline, métricas, adaptador e CLI do MLflow (só o baseline registrado) | ~380 linhas |
| 2 | #52 | LightGBM quantílico, CQR por grupo, avaliação factual e sem jornada, go/no-go, métricas por grupo e pacote do modelo salvo | ~400 linhas |
| 3 | #53 | `estimar_faixa` (grupo de referência, combinação por raça, 40 h e jornada da usuária, IPCA, diferença por raça agregada), CLI `estimar`, README e docs. Só depois do go. | ~400 linhas |
| docs | — | ADR-012 (aberto junto com o PR 1) e a página atualizada (junto com o PR 3), citados nos PRs do agents | |

Cada PR fecha a sub-issue dele, e o PR 3 leva também `Closes #4`. As branches seguem o número da sub-issue (`feat/51-...`, `feat/52-...`, `feat/53-...`). A worktree atual, `feat/4-modelo-faixa-salarial`, é renomeada para `feat/51-...` antes do primeiro push.

## Limitações

- **Sem validação temporal.** Treino e teste são de 2025, então não sabemos como o modelo envelhece. A RAIS pública não tem identificador de pessoa, então a mesma pessoa com dois vínculos pode cair no treino e no teste.
- **Experiência não existe na RAIS.** O treino usa a experiência potencial (idade menos anos de estudo menos 6), e a usuária informa a experiência real. A potencial superestima a real de quem teve pausas na carreira, mais comuns entre mulheres (maternidade). Por isso, no treino, uma mulher com a mesma experiência potencial de um homem tende a ter menos experiência real. Parte disso pode cair no efeito de sexo, e não no de perfil.
- **A referência é um piso.** Parte da desigualdade fica "explicada" pela própria CBO e pelo nível em que as mulheres são enquadradas.
- **IPCA dentro de 2025 ignorado**, e a combinação por pesos de raça é uma média de quantis, que aproxima o quantil da mistura.
- Só emprego formal do setor privado. A jornada de 4,74% dos vínculos é imputada, e 0,15% saem por jornada abaixo de 10 h.
- A faixa de mercado das mulheres de todas as raças subestima a diferença para mulheres negras. A diferença por raça agregada é o contexto que compensa isso, sem perguntar a raça.

## Referências

- Mincer, J. (1974). *Schooling, Experience, and Earnings.* New York: NBER / Columbia University Press. (Experiência potencial e a equação salarial em log.)
- Oaxaca, R. (1973) e Blinder, A. (1973), como na página de arquitetura.
- Romano, Y., Patterson, E. e Candès, E. (2019). *Conformalized Quantile Regression.* NeurIPS.
- Layout da RAIS Vínculos (MTE/PDET), para os códigos de escolaridade.
- IBGE, SIDRA, tabela 1737 (IPCA, número-índice).

## Riscos para a #5

**A falta de jornada não é igual entre os grupos** (RAIS STEM 2025, lido em 22/11):

| Sexo | Raça/cor | Vínculos | Sem jornada | Abaixo de 10 h |
|---|---|---:|---:|---:|
| feminino | amarela | 8.350 | 9,33% | 0,11% |
| feminino | branca | 275.088 | 6,09% | 0,18% |
| feminino | indígena | 786 | 6,74% | 0,00% |
| feminino | não identificada | 5.598 | 2,52% | 0,27% |
| feminino | parda | 143.934 | 3,53% | 0,14% |
| feminino | preta | 27.515 | 4,71% | 0,10% |
| masculino | amarela | 26.488 | 7,55% | 0,11% |
| masculino | branca | 1.096.377 | 5,56% | 0,16% |
| masculino | indígena | 4.324 | 4,53% | 0,10% |
| masculino | não identificada | 29.636 | 2,10% | 0,24% |
| masculino | parda | 724.915 | 3,32% | 0,14% |
| masculino | preta | 135.793 | 4,00% | 0,11% |
| **feminino** | todas | 461.271 | **5,22%** | |
| **masculino** | todas | 2.017.533 | **4,63%** | |

- Faltam mais jornadas para mulheres do que para homens e para pessoas brancas e amarelas do que para pardas e pretas.
- Os vínculos sem jornada são outro perfil: 22% estão em gestão, contra 5,7% no total. A mediana da remuneração deles é de **R$ 11.013 (mulheres) e R$ 11.138 (homens)**, contra R$ 4.556 e R$ 4.939 nos demais. Quase não há diferença por sexo entre eles.
- **Consequência:** tirar esses vínculos apagaria um grupo bem pago, mais branco e quase sem diferença de sexo. Isso aumentaria a diferença medida e mudaria o erro por grupo. Por isso a spec imputa a jornada em vez de tirar. Mas a imputação também é uma suposição (que gestores com jornada ausente seguem a mediana da CBO × UF). A #5 deve comparar as métricas por grupo com e sem os vínculos de jornada imputada, e o MLflow já registra os dois casos.
- **Experiência potencial:** ver Limitações. As pausas na carreira são desiguais entre os sexos, e isso pode inflar o efeito de sexo.
