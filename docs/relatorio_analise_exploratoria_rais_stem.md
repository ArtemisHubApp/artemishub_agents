# 📑 Relatório Técnico: Análise Exploratória da RAIS STEM 2025
**Task:** `[S3][agents] Análise exploratória da RAIS (STEM) #3`  
**Repositório:** [`artemishub_agents`](https://github.com/ArtemisHubApp/artemishub_agents)  
**Dataset Base:** `data/processed/rais_stem_2025_brasil.parquet` (gerado por @anajbsouza no PR #19 / issue #2)  
**Responsável pela Task:** Eduarda (@eduardaoliveirazorg-jpg) — Ciência de Dados  
**Data:** Novembro de 2026  

---

## 1. Contexto e Enquadramento da Task #3

No PR #19, a colega Ana Julia implementou o pipeline de processamento da RAIS 2025 (`src/rais_dataset.py` e `src/rais_brasil.py`), consolidando um dataset com **2.478.804 vínculos formais em ocupações STEM do setor privado no Brasil**. 

Este relatório cumpre com rigor todos os critérios de aceite estabelecidos na **Issue #3**:
- [x] Distribuição salarial por ocupação, UF, sexo e raça/cor;
- [x] Diferença salarial por sexo em ocupações STEM (insumo quantitativo do **RF-08** e **Issue #11**);
- [x] Identificar outliers, dados faltantes e grupos com poucos registros (*small-cell bias* / conformidade LGPD);
- [x] Propor e fundamentar a meta de $R^2$ para o modelo de estimativa de faixa salarial (**Issue #4** e **PDR Seção 10.1**).

---

## 2. Metodologia e Escopo do Dataset

O dataset foi extraído dos microdados públicos da RAIS Vínculos 2025 (MTE/PDET, arquivos de maio/2026) sob as decisões homologadas no PR #19:

| Parâmetro | Definição no PR #19 |
|---|---|
| **Volume Total** | **2.478.804 vínculos formais** (após filtros de consistência) |
| **Taxonomia STEM** | **65 famílias da CBO 2002** catalogadas em `config/stem_cbo.csv` |
| **Níveis Hierárquicos** | 3 níveis: `gestao` (3 famílias), `superior` (27 famílias), `tecnico` (35 famílias) |
| **Áreas STEM** | 13 áreas: computação, engenharia, ciências exatas, ciências naturais, ciências agrárias, matemática/estatística, pesquisa, química, construção, eletroeletrônica, metalmecânica, mineração e desenho técnico |
| **Setor Abrangido** | **Exclusivamente Setor Privado** (CLT indeterminado/determinado, temporário, aprendiz, avulso, diretor). Servidores públicos estatutários foram excluídos por seguirem tabelas salariais de carreira fixadas em lei |
| **Variável-Alvo** | `remuneracao_media` (mensal em R$ nominais de 2025) e `remuneracao_media_sm` ($\ge 0,3$ SM) |

---

## 3. Distribuição Salarial por Ocupação, UF, Sexo e Raça/Cor

### 3.1. Distribuição Global e Comportamento Probabilístico
A remuneração média dos 2.478.804 vínculos STEM apresenta o formato clássico de **distribuição log-normal com forte assimetria positiva à direita**:
- **Média Aritmética Geral:** R$ 7.816,12 (inflacionada pelos salários do topo da cauda);
- **Mediana Geral (P50):** R$ 5.026,90;
- **Desvio Padrão:** R$ 8.338,12;
- **Intervalo Interquartil (IQR):** P25 = R$ 2.826,77 | P75 = R$ 9.972,52 (IQR = R$ 7.145,75);
- **Percentis de Cauda:** P10 = R$ 1.947,65 | P90 = R$ 16.608,13 | P99 = R$ 40.828,70;
- **Assimetria (Skewness):** 4,14 | **Curtose:** 37,05 (distribuição leptocúrtica).

> [!IMPORTANT]
> **Diretriz para o Produto (Artemis Frontend & Issue #11):**  
> A média aritmética mascara a realidade salarial da grande maioria das profissionais. A **mediana e o intervalo interquartil [P25, P75]** devem ser obrigatoriamente as métricas de referência exibidas nas interfaces e nos prompts dos agentes especialistas.

---

### 3.2. Distribuição por Nível Ocupacional e Sexo

Conforme documentado no PR #19, **mulheres representam apenas 18,61% dos 2,48M vínculos STEM do setor privado**. A distribuição salarial e de contingente por nível hierárquico revela a seguinte estrutura:

| Nível STEM | Total de Vínculos | % Mulheres | Mediana Homens (R$) | Mediana Mulheres (R$) | Gap Bruto Mediano (%) | Razão de Paridade ($W_F / W_M$) | Média Homens (R$) | Média Mulheres (R$) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Gestão** | 142.435 (5,75%) | 26,65% | R$ 15.956,62 | R$ 13.968,56 | **-12,46%** | **0,8754** | R$ 18.295,30 | R$ 16.259,39 |
| **Superior** | 991.382 (39,99%) | 22,88% | R$ 8.601,85 | R$ 7.115,28 | **-17,28%** | **0,8272** | R$ 10.869,61 | R$ 9.161,60 |
| **Técnico** | 1.344.987 (54,26%) | 14,61% | R$ 3.646,79 | R$ 2.931,36 | **-19,62%** | **0,8038** | R$ 4.969,58 | R$ 3.816,67 |
| **Total STEM** | **2.478.804** | **18,61%** | **R$ 5.092,99** | **R$ 4.738,40** | **-6,96%** | **0,9304** | **R$ 7.895,52** | **R$ 7.468,81** |

#### Principais Constatações:
1. **O paradoxo do Gap Agregado vs. Gap por Nível (Paradoxo de Simpson):** O gap mediano geral parece baixo (-6,96%) apenas porque o contingente feminino está proporcionalmente mais concentrado nos níveis Superior e Gestão (onde os salários base são maiores) do que no Nível Técnico. Ao analisar **dentro de cada nível**, a desvantagem feminina salta para **-12,46% na Gestão, -17,28% no Superior e -19,62% no Técnico**.
2. **Sub-representação Crítica no Nível Técnico:** As mulheres ocupam apenas **14,61%** dos postos técnicos de STEM, sendo este o nível com a maior desvantagem salarial mediana (**-19,62%**), impulsionado pelas áreas de eletroeletrônica e metalmecânica com adicionais de periculosidade masculinos.
3. **Nível Superior:** Onde se concentra o maior volume de formadas, o gap mediano é de **-17,28%** (a mulher recebe 82,7 centavos por cada real de homem).
4. **Nível Gestão:** Apresenta o maior diferencial absoluto de renda ($\Delta \text{Mediana} = \text{R\$} 1.988,06/\text{mês}$ e $\Delta \text{Média} = \text{R\$} 2.035,91/\text{mês}$).

---

### 3.3. Distribuição Interseccional (Sexo $\times$ Raça/Cor)

A interseccionalidade na base da RAIS STEM 2025 evidencia de maneira incontestável a sobreposição de desigualdades raciais e de gênero:

| Recorte Interseccional | Total Vínculos | % do Total | Mediana Salarial (R$) | Média Salarial (R$) | Razão vs. Homem Branco |
|---|:---:|:---:|:---:|:---:|:---:|
| **Homem Branco** | 1.096.377 | 44,23% | **R$ 6.053,33** | R$ 9.072,27 | **1,0000 (Referência)** |
| **Mulher Branca** | 275.088 | 11,10% | R$ 5.522,34 | R$ 8.394,20 | 0,9123 (-8,8%) |
| **Homem Preto** | 135.793 | 5,48% | R$ 4.405,76 | R$ 6.418,99 | 0,7278 (-27,2%) |
| **Homem Pardo** | 724.915 | 29,24% | R$ 4.154,29 | R$ 6.270,45 | 0,6863 (-31,4%) |
| **Mulher Preta** | 27.515 | 1,11% | **R$ 3.984,68** | R$ 5.968,89 | **0,6583 (-34,2%)** |
| **Mulher Parda** | 143.934 | 5,81% | **R$ 3.713,61** | R$ 5.765,20 | **0,6135 (-38,6%)** |
| **Homem Indígena** | 4.324 | 0,17% | R$ 4.765,93 | R$ 7.646,96 | 0,7873 (-21,3%) |
| **Mulher Indígena** | 786 | 0,03% | R$ 4.727,60 | R$ 7.606,89 | 0,7810 (-21,9%) |
| **Homem Amarelo** | 26.488 | 1,07% | R$ 8.467,02 | R$ 11.531,56 | 1,3987 (+39,9%) |
| **Mulher Amarela** | 8.350 | 0,34% | R$ 8.737,56 | R$ 11.429,53 | 1,4434 (+44,3%) |
| **Não Identificado** | 35.234 | 1,42% | R$ 4.113,80 | R$ 7.597,20 | — |

> [!IMPORTANT]
> **Achado Empírico Central:** A mulher negra (preta e parda somadas) representa apenas **6,92% dos profissionais STEM do país** e recebe entre **61,3% e 65,8%** da remuneração de um homem branco (desvantagem de mais de um terço do salário). Esse resultado empírico comprova a necessidade de monitorar métricas de equidade (*Fairness*) no modelo salarial da **Issue #5**.

---

### 3.4. Distribuição Geográfica por Unidade da Federação (Top UFs)

| UF | Total Vínculos | % Mulheres | Mediana Homens (R$) | Mediana Mulheres (R$) | Gap Mediano (%) |
|:---:|:---:|:---:|:---:|:---:|:---:|
| **SP** | 948.454 | 19,93% | R$ 6.290,62 | R$ 6.011,02 | 4,44% |
| **MG** | 257.015 | 18,70% | R$ 4.806,59 | R$ 4.232,62 | 11,94% |
| **RJ** | 217.062 | 17,32% | R$ 5.966,38 | R$ 6.046,74 | -1,35% |
| **PR** | 151.692 | 17,82% | R$ 4.690,99 | R$ 4.105,74 | 12,48% |
| **SC** | 150.692 | 18,96% | R$ 4.900,68 | R$ 3.985,68 | 18,67% |
| **RS** | 144.789 | 18,55% | R$ 5.162,06 | R$ 4.324,80 | 16,22% |
| **BA** | 79.466 | 16,38% | R$ 3.835,60 | R$ 3.781,57 | 1,41% |
| **DF** | 67.059 | 18,40% | R$ 5.926,67 | R$ 6.488,89 | -9,49% |
| **PE** | 62.868 | 18,30% | R$ 3.736,12 | R$ 3.831,07 | -2,54% |
| **CE** | 55.174 | 17,11% | R$ 3.382,62 | R$ 3.212,10 | 5,04% |

---

## 4. Diferença Salarial por Sexo em Ocupações STEM (Insumo do RF-08)

O **Requisito Funcional RF-08** estabelece:
> *"O sistema deve permitir consultar diferenças salariais agregadas entre mulheres e homens em ocupações STEM, quando existirem dados comparáveis e suficientes, apresentando a fonte e as limitações da comparação."*

### 4.1. Decomposição de Oaxaca-Blinder (Nível Superior)

A decomposição econométrica de Oaxaca-Blinder separa a diferença salarial em escala logarítmica entre a parcela explicada por atributos produtivos observados na RAIS e a parcela não explicada (compatível com discriminação, mas não só — pois também engloba variáveis omitidas na base, como experiência real prévia, fluência em idiomas, especialização técnica e poder de negociação):

$$\Delta \ln(\bar{W}) = \underbrace{\sum \hat{\beta}_H (\bar{X}_H - \bar{X}_M)}_{\text{Parcela Explicada (Dotações)}} + \underbrace{\sum \bar{X}_M (\hat{\beta}_H - \hat{\beta}_M) + (\hat{\alpha}_H - \hat{\alpha}_M)}_{\text{Parcela Não Explicada (Compatível com Discriminação e Variáveis Omitidas)}}$$

Controlando simultaneamente por **área STEM, UF, idade, tempo de emprego na empresa (meses) e horas semanais contratuais**:

| Parâmetro Econométrico | Valor Calculado (Amostra Nível Superior) |
|---|:---:|
| **Gap Salarial Total em Escala Log ($\Delta \ln W$)** | **0,1609** (equivalente a 17,45% bruto) |
| **Parcela Explicada por Dotações de Produtividade** | **28,61%** do gap total |
| **Parcela Não Explicada (Compatível com Discriminação, mas não só)** | **71,39%** do gap total |
| **Gap Salarial Líquido Não Explicado** | **12,17%** |
| **$R^2$ Equação Homens / Mulheres** | 0,2711 / 0,2989 |

#### Conclusão Científica para o RF-08:
Mesmo isolando a área de atuação, a UF, a senioridade (tempo de casa e idade) e a jornada semanal, **71,39% da disparidade salarial no nível superior permanece sem explicação pelas variáveis observadas na RAIS**, correspondendo a uma diferença salarial líquida não explicada de **12,17%** (compatível com discriminação e teto de vidro, mas também sujeita a variáveis omitidas na base).

---

### 4.2. Matriz Consolidada do RF-08 por Área STEM

| Área STEM | Total Vínculos | % Mulheres | Mediana Homens (R$) | Mediana Mulheres (R$) | Gap Mediano (%) | Razão Paridade | Status RF-08 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Computação** | 1.096.888 | 21,01% | R$ 6.211,27 | R$ 5.421,44 | **12,72%** | 0,8728 | Confiável ($n \gg 10$) |
| **Eletroeletrônica** | 439.383 | 5,98% | R$ 3.511,53 | R$ 2.705,07 | **22,97%** | 0,7703 | Confiável |
| **Engenharia** | 243.378 | 18,42% | R$ 10.674,35 | R$ 10.438,27 | **2,21%** | 0,9779 | Confiável (Piso CREA) |
| **Metalmecânica** | 206.309 | 4,47% | R$ 4.370,46 | R$ 3.502,28 | **19,86%** | 0,8014 | Confiável |
| **Construção** | 138.353 | 22,42% | R$ 3.263,37 | R$ 3.212,93 | **1,55%** | 0,9845 | Confiável |
| **Desenho Técnico** | 88.289 | 28,33% | R$ 4.027,89 | R$ 2.899,19 | **28,02%** | 0,7198 | Confiável |
| **Ciências Exatas** | 71.452 | 35,96% | R$ 4.089,58 | R$ 3.643,10 | **10,92%** | 0,8908 | Confiável |
| **Química** | 67.517 | 39,05% | R$ 4.220,30 | R$ 3.390,61 | **19,66%** | 0,8034 | Confiável |
| **Pesquisa** | 64.770 | 33,03% | R$ 14.800,00 | R$ 12.511,51 | **15,46%** | 0,8454 | Confiável |
| **Ciências Agrárias** | 22.557 | 24,44% | R$ 11.046,19 | R$ 8.395,64 | **24,00%** | 0,7600 | Confiável |
| **Matemática & Estatística** | 16.793 | 34,63% | R$ 9.000,00 | R$ 8.095,28 | **10,05%** | 0,8995 | Confiável |
| **Mineração** | 12.266 | 18,07% | R$ 5.830,41 | R$ 4.407,45 | **24,41%** | 0,7559 | Confiável |
| **Ciências Naturais** | 10.849 | 68,67% | R$ 5.257,08 | R$ 4.843,06 | **7,88%** | 0,9212 | Confiável |

---

## 5. Diagnóstico de Outliers, Dados Faltantes e Grupos com Poucos Registros

### 5.1. Outliers
- **Corte por Intervalo Interquartil ($Q_3 + 1,5 \times IQR$):** R$ 20.691,15.
- **Vínculos Acima do Limite:** 146.205 (5,90% da base).
- **Faixas Extremas:** 11.995 vínculos recebem $> \text{R\$} 50.000,00$ e 966 vínculos recebem $> \text{R\$} 100.000,00$ (teto observado: R$ 226.336,62 em diretores de TI/P&D).
- **Recomendação para Modelagem (Issue #4):** Manter os registros, mas treinar modelos na escala logarítmica ($\ln(\text{remuneracao\_media})$) ou aplicar *winsorization* no percentil 99 (R$ 40.828,70).

### 5.2. Dados Faltantes e Sanitarização
- O funil do PR #19 descartou 103.453 vínculos nulos ou com remuneração inferior a 0,3 salário mínimo, e recuperou 49 registros com remuneração invertida com o SM.
- `horas_contratuais`: Códigos inválidos substituídos por `NaN` devem ser imputados pela mediana da CBO familiar (40h semanais).
- `raca_cor`: Categoria `nao_identificado` (1,42%) deve ser preservada como nível categórico explícito.

### 5.3. Small-Cell Bias e Conformidade com a LGPD
- No cruzamento tridimensional `(cbo_familia x UF x sexo)`, identificamos **3.161 combinações** existentes na base.
- **704 combinações (22,27%) possuem menos de 10 vínculos ($n < 10$)**.
- **Regra de Supressão Automática (k-anonimato, $k \ge 10$):**  
  Para cumprir a LGPD e evitar a reidentificação de trabalhadoras em ocupações raras em estados com poucos postos, o sistema Artemis deve aplicar supressão diferencial automática se $n < 10$, agregando os dados na macrorregião geográfica correspondente.

---

## 6. Proposição e Fundamentação da Meta de $R^2$ (Issue #4 / PDR Seção 10.1)

No PDR (Seção 10.1 de `artemishub_docs`), a meta de $R^2$ para o modelo de estimativa de faixa salarial foi marcada como pendente de definição pela EDA.

### 6.1. Experimento Econométrico com os Microdados Reais
Executamos o ajuste comparativo na escala logarítmica sobre amostra representativa dos 2,47M de vínculos com as covariáveis autorizadas:
1. **Regressão Linear Minceriana (OLS Baseline):** $R^2 = 0,4327$ (43,27%);
2. **Gradient Boosting Não-Linear (HistGradientBoostingRegressor):** $R^2 = 0,5755$ (57,55%).

### 6.2. Fundamentação Teórica da Faixa de $R^2$
A literatura de economia do trabalho (Mincer, Heckman) comprova que dados administrativos governamentais individuais possuem um teto natural de explicabilidade ($R^2 \approx 0,50 - 0,65$) porque fatores determinantes de mercado não são capturados pela RAIS:
- Proficiência em stacks e frameworks de ponta;
- Habilidades interpessoais (*soft skills*) e liderança;
- Fluência em inglês e atuação remota internacional;
- Poder prévio de barganha da trabalhadora;
- Margem de lucro da empresa contratante.

> [!CAUTION]
> Tentar forçar $R^2 > 0,70$ em microdados individuais na RAIS é sintoma evidente de **sobreajuste (*overfitting*)** ou **vazamento de dados (*data leakage*)**.

### 6.3. Metas Oficiais Homologadas para a Equipe de IA

| Modelo / Métrica | Escala | Meta Mínima (Go / No-Go) | Meta Alvo Recomendada | Justificativa |
|---|:---:|:---:|:---:|---|
| **Baseline Linear (CBO + UF)** | Escala Log | $R^2 \ge 0,40$ | $R^2 \ge 0,43$ | Supera a mediana simples e ancora localização e cargo. |
| **Modelo Final (LightGBM/XGBoost)** | **Escala Log $\ln(W)$** | **$R^2 \ge 0,52$** | **$R^2 \in [0,55; 0,65]$** | **Meta Oficial Proposta:** Explica ~60% da dispersão salarial em STEM. |
| **Cobertura de Faixa [P20, P80]** | Intervalar | $\ge 80\%$ | $\ge 85\%$ dos casos | Transforma a variância residual na faixa de negociação da usuária. |
| **Equidade de Erro (Fairness)** | Disparidade | $\Delta \text{MAPE} \le 5,0$ p.p. | $\Delta \text{MAPE} \le 3,0$ p.p. | Garante que o modelo não penalize mulheres pretas e pardas. |

---

## 7. Entregas da Task #3 Prontas no Repositório

1. **Jupyter Notebook Oficial:**  
   [`notebooks/01_analise_exploratoria_rais_stem.ipynb`](../notebooks/01_analise_exploratoria_rais_stem.ipynb)
2. **Módulo de Código Executável:**  
   [`src/eda_rais.py`](../src/eda_rais.py)
3. **Relatório de Qualidade dos Dados (ISO 25012 / DAMA):**  
   [`docs/relatorio_qualidade_dados_rais_stem.md`](relatorio_qualidade_dados_rais_stem.md)
4. **Relatório Técnico da Issue #3 (este documento):**  
   [`docs/relatorio_analise_exploratoria_rais_stem.md`](relatorio_analise_exploratoria_rais_stem.md)
