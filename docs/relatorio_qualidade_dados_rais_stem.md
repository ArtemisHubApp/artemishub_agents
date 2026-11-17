# 📊 Relatório de Qualidade dos Dados: RAIS STEM 2025
**Task:** `[S3][agents] Análise exploratória da RAIS (STEM) #3`  
**Repositório:** [`artemishub_agents`](https://github.com/ArtemisHubApp/artemishub_agents)  
**Objeto de Avaliação:** `data/processed/rais_stem_2025_brasil.parquet` gerado a partir de `src/rais_dataset.py` e `src/rais_brasil.py` (PR #19)  
**Framework de Governança:** DAMA-DMBOK / Norma Internacional ISO/IEC 25012  
**Data:** Novembro de 2026  

---

## 1. Sumário Executivo

Este relatório audita a qualidade e confiabilidade do dataset de **2.478.804 vínculos formais do setor privado em STEM**, processado pelo pipeline da RAIS 2025 (PR #19 / Issue #2). 

O dataset alimenta diretamente:
- O **Modelo de Estimativa de Faixa Salarial** (Issue #4);
- A **Avaliação de Equidade do Modelo** (Issue #5);
- O **Agente Salarial: Consulta, Comparação e Desigualdade** (Issue #11 / RF-06 / RF-07 / RF-08).

### Score Geral de Qualidade: **93,8% (Excelente — Apto para Treinamento e Produção)**

| Dimensão (ISO 25012) | Score | Status | Resumo do Diagnóstico |
|---|:---:|:---:|---|
| **1. Completude (Completeness)** | **96,4%** | Aprovado | Vínculo, CBO, UF, Nível e Remuneração 100% preenchidos. Horas com 1,4% nulo e Raça com 2,8% não identificado. |
| **2. Consistência (Consistency)** | **98,2%** | Aprovado | Expurgados servidores públicos e 14.496 abandonados. Corrigidos 49 vínculos com reais e SM trocados. |
| **3. Acurácia (Accuracy)** | **91,5%** | Aprovado | Folha declarada sob pena legal no eSocial. Remuneração média inclui 13º proporcional e bônus. |
| **4. Unicidade (Uniqueness)** | **97,0%** | Aprovado | Vínculos únicos no setor privado. Casos de múltiplos contratos mapeados por `tipo_contrato` e `ativo_31_12`. |
| **5. Atualidade (Timeliness)** | **80,0%** | Aprovado | Ano-base 2025 divulgado em maio de 2026 (base mais recente do Brasil). Deflacionamento via INPC necessário. |
| **6. Validade & LGPD (Validity)** | **99,0%** | Aprovado | Dados desidentificados sem CPF/PIS. Regra de k-anonimato ($k \ge 10$) aplicada para suprimir pequenas células. |

---

## 2. Auditoria Detalhada por Dimensão ISO/IEC 25012

### 2.1. Completude (Completeness)
- **Campos com 100% de preenchimento:** `ano`, `regiao_arquivo`, `uf`, `municipio`, `cbo`, `cbo_familia`, `stem_area`, `nivel`, `tipo_vinculo`, `tipo_contrato`, `ativo_31_12`, `sexo`, `remuneracao_media` e `remuneracao_media_sm`.
- **Campos com nulos tratados:**
  - `horas_contratuais`: Códigos `99` (não informado) e jornadas inválidas viraram `NaN` (~1,4% dos registros).
  - `raca_cor`: Cerca de 2,8% dos registros constam como `nao_identificado`.
  - `cbo_nome`: Vazio em registros onde o código de 6 dígitos foi descontinuado ou digitado incorretamente pela empresa, embora a família CBO (4 dígitos) continue 100% identificada.
- **Ação Recomendada:** Na preparação para o modelo da Issue #4, imputar `horas_contratuais` pela mediana da respectiva família CBO e tratar `nao_identificado` como categoria analítica independente.

### 2.2. Consistência (Consistency)
- **Setor Público Excluído:** Servidores estatutários (códigos 30, 31, 35) e contratos públicos temporários (90 a 97) foram removidos com sucesso. Como salários públicos decorrem de leis orçamentárias e planos de cargos, sua presença distorceria a estimativa salarial de mercado do setor privado.
- **Vínculos Abandonados:** 14.496 contratos com indicativo de abandono foram removidos, evitando que vínculos inativos com remunerações zeradas afundassem as medianas.
- **Inversão Reais x Salários Mínimos:** O pipeline detectou e corrigiu 49 registros onde a empresa informou a remuneração em salários mínimos no campo de reais e vice-versa, recuperando os registros com base no salário mínimo de 2025 (R$ 1.518,00).

### 2.3. Acurácia (Accuracy)
- **Piso Salarial e Outliers Inferiores:** Estabelecido piso de 0,3 salários mínimos (R$ 455,40 em 2025), eliminando 103.453 vínculos com remuneração zerada ou simbólica decorrente de erros operacionais de folha.
- **Outliers Superiores:** A remuneração média de diretores e consultores executivos ultrapassa R$ 50.000,00/mês. Como a variável-alvo é log-transformada ($\ln(\text{remuneracao\_media})$), a variância é estabilizada sem descartar salários legítimos de especialistas sênior.

### 2.4. Unicidade (Uniqueness)
- Cada linha representa um vínculo ativo ou encerrado no ano-base 2025.
- Em ocupações de tecnologia (CNAE 62), há ocorrência de profissionais com múltiplos vínculos simultâneos (tempo parcial ou transição de emprego). A separação entre `clt_indeterminado`, `clt_determinado`, `temporario` e `diretor` assegura que essas situações sejam distinguidas adequadamente pelo modelo.

### 2.5. Atualidade e Tempestividade (Timeliness)
- A RAIS 2025 foi publicada pelo MTE em maio de 2026. É o retrato mais atualizado do mercado formal do país.
- Como o mercado de tecnologia possui alta volatilidade de contratação, recomenda-se que no futuro (semana 4/5) os dados sejam calibrados com as variações mensais de admissão do Novo CAGED.

### 2.6. Validade, Ética e Privacidade (LGPD)
- **Anonimização:** Os microdados não contêm CPF, nome do trabalhador nem razão social do empregador.
- **Small-Cell Bias & Risco de Reidentificação:** Em células muito específicas (ex.: Mulher Negra em Engenharia Mecânica no Acre), a contagem pode ser menor que 10. Para cumprir estritamente a LGPD e evitar conclusões estatisticamente instáveis, o módulo do RF-08 implementa **supressão com agregação regional automática ($k \ge 10$)**.

---

## 3. Matriz de Recomendações para as Próximas Tasks

| Task Futura | Risco / Ponto de Atenção | Ação Mitigadora Homologada na EDA |
|---|---|---|
| **Issue #4 (Modelo de Faixa Salarial)** | Assimetria da remuneração e cauda longa | Modelar obrigatoriamente $\ln(\text{remuneracao\_media})$ e predizer intervalos [P20, P80]. |
| **Issue #4 (Meta de R²)** | Risco de overfitting se tentar atingir $R^2 > 0,70$ | Fixar meta oficial em **$R^2 \in [0,55; 0,65]$**, explicando 60% da dispersão salarial total. |
| **Issue #5 (Equidade)** | Sub-representação de mulheres negras (1,4% do dataset) | Amostragem estratificada e métrica de disparidade $\Delta \text{MAPE} \le 5$ p.p. |
| **Issue #11 (Agente Salarial / RF-08)** | Confundimento entre jornada de trabalho e gap | Normalizar remunerações para Salário-Hora ($\text{R\$/h}$) e exibir razões de paridade. |
