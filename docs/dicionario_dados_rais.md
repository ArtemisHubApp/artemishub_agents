# Dicionário de dados: RAIS STEM 2025

Dataset salarial do Artemis (issue #2). Uma linha por vínculo de emprego formal em ocupação STEM no setor privado, em 2025, no Brasil todo. Alimenta o modelo de faixa salarial (#4), a avaliação de equidade (#5) e o agente salarial (#11).

| | |
|---|---|
| Arquivo | `data/processed/rais_stem_2025_brasil.parquet` (formato Parquet) |
| Linhas | 2.478.804 |
| Fonte | Microdados da RAIS Vínculos 2025, MTE/PDET (`ftp://ftp.mtps.gov.br/pdet/microdados/RAIS/2025/`), arquivos de 13/05/2026 no FTP |
| Nomes das ocupações | CBO 2002, tabelas de ocupação e família do MTE |
| Gerado em | 12/11/2026 |

## Como gerar de novo

1. Baixar os 6 arquivos `RAIS_VINC_PUB_<REGIAO>.7z` de 2025 para `data/raw/rais/2025/` e descompactar.
2. Baixar `cbo2002-ocupacao.csv` e `cbo2002-familia.csv` para `data/raw/cbo/`.
3. Para cada região: `uv run python -m src.rais_dataset --arquivo data/raw/rais/2025/RAIS_VINC_PUB_<REGIAO>.COMT --ano 2025`
4. Juntar: `uv run python -m src.rais_brasil --ano 2025`

Cada passo salva um `.json` ao lado do `.parquet` com o funil de filtros e um resumo.

## Regras de seleção

Aplicadas nesta ordem. Números do Brasil todo.

| Etapa | Regra | Vínculos depois |
|---|---|---|
| Arquivos lidos | 6 regiões; o arquivo `NI` (não identificado) fica de fora por não ter UF | 91.704.054 |
| Ocupação STEM | Família da CBO (4 primeiros dígitos) listada em `config/stem_cbo.csv` | 2.749.256 |
| Setor privado | Tipo de vínculo CLT, temporário, aprendiz, avulso ou diretor | 2.596.753 |
| Sem abandonados | `Ind Vínculo Abandonado` diferente de 1 | 2.582.257 |
| Remuneração positiva | Remuneração média nominal maior que zero | 2.478.804 |
| Remuneração plausível | Remuneração média de pelo menos 0,3 salário mínimo | 2.478.804 |

Antes dos dois filtros de remuneração, 49 vínculos tinham os valores em reais e em salários mínimos trocados (por exemplo, R$ 31,01 e 47.078,97 SM). Eles foram destrocados, e não excluídos: a troca é reconhecida quando a conta invertida dá o salário mínimo do ano, com margem de 5%.

## Decisões

- **Definição de STEM.** Não há lista oficial na CBO. A lista em `config/stem_cbo.csv` tem 65 famílias: gestão de TI e de P&D, ciências exatas e naturais, computação, engenharias, ciências agrárias e os técnicos de nível médio dessas áreas (inclusive química e construção civil). Ficaram de fora as famílias limítrofes (pesquisa em clínica médica, arquitetura, engenharia de segurança do trabalho, biomedicina), pesquisa em economia, perícia criminal, navegação e aviação, e técnicos sem base científica (têxtil, tintas, artes gráficas, móveis, vestuário).
- **Setor público fora.** Servidores estatutários (códigos 30, 31 e 35) e contratos públicos temporários (90 a 97) ficam fora porque o salário vem de tabela de carreira, e não de negociação.
- **Desligados dentro.** Quem saiu durante o ano entra, marcado em `ativo_31_12 = False`. A remuneração média é por mês trabalhado, então continua sendo um salário mensal válido.
- **Valores ignorados viram vazio.** Códigos `-1`, `{ñ class}` e afins, segundo o layout, ficam como vazio (`NaN`), e não como categoria.
- **Código da CBO com 6 dígitos.** A RAIS perde o zero à esquerda (`21210` é `021210`, soldado da PM). Sem a correção, militares seriam confundidos com a família de informática 2121.

## Colunas

| Coluna | Tipo | Descrição | Valores |
|---|---|---|---|
| `ano` | inteiro | Ano-base da RAIS | 2025 |
| `regiao_arquivo` | texto | Arquivo regional de origem | `norte`, `nordeste`, `centro_oeste`, `mg_es_rj`, `sp`, `sul` |
| `uf` | texto | UF onde a pessoa trabalha; se ausente, a do estabelecimento | sigla, ex.: `DF` |
| `municipio` | texto | Código IBGE do município, 6 dígitos, mesma regra da UF | ex.: `530010` |
| `cbo` | texto | Ocupação, CBO 2002, 6 dígitos | ex.: `212405` |
| `cbo_familia` | texto | Família da CBO (4 primeiros dígitos) | ex.: `2124` |
| `cbo_nome` | texto | Nome oficial da ocupação | ex.: `Analista de desenvolvimento de sistemas` |
| `cbo_familia_nome` | texto | Nome oficial da família | ex.: `Analistas de tecnologia da informação` |
| `stem_area` | texto | Área STEM da família (de `config/stem_cbo.csv`) | `computacao`, `engenharia`, `ciencias_exatas`, `ciencias_naturais`, `ciencias_agrarias`, `matematica_estatistica`, `pesquisa`, `quimica`, `construcao`, `eletroeletronica`, `metalmecanica`, `mineracao`, `desenho_tecnico` |
| `nivel` | texto | Nível da ocupação | `gestao`, `superior`, `tecnico` |
| `cnae_classe` | texto | Atividade econômica do estabelecimento, CNAE 2.0, 5 dígitos | ex.: `62015` |
| `tipo_vinculo` | texto | Código original do tipo de vínculo | ex.: `10`, `55` |
| `tipo_contrato` | texto | Tipo de vínculo agrupado | `clt_indeterminado` (10–25), `clt_determinado` (60–75), `temporario` (50), `aprendiz` (55), `avulso` (40), `diretor` (80) |
| `ativo_31_12` | booleano | Vínculo ativo em 31/12/2025 | `True`, `False` |
| `sexo` | texto | Sexo | `feminino`, `masculino`; vazio = ignorado |
| `raca_cor` | texto | Raça/cor | `branca`, `preta`, `parda`, `amarela`, `indigena`, `nao_identificado`; vazio = ignorado |
| `escolaridade_codigo` | número | Escolaridade em ordem, de 1 a 11 | 1 = analfabeto ... 9 = superior completo, 10 = mestrado, 11 = doutorado |
| `escolaridade` | texto | Escolaridade por extenso | `medio_completo`, `superior_completo`, `mestrado` etc. |
| `idade` | número | Idade em anos | 14 a 100; fora disso, vazio |
| `tempo_emprego_meses` | número | Tempo no vínculo, em meses | |
| `horas_contratuais` | número | Horas semanais contratadas | 1 a 60; `99` (não informado) e outros valores viram vazio |
| `tamanho_estabelecimento` | texto | Faixa de empregados ativos do estabelecimento em 31/12, código da RAIS (10 faixas; ver layout) | ex.: `05` |
| `remuneracao_media` | número | Remuneração média mensal no ano, em R$ nominais | **variável-alvo do modelo** |
| `remuneracao_media_sm` | número | A mesma remuneração em salários mínimos | ≥ 0,3 |

## Limitações

- **Só emprego formal.** A RAIS não tem PJ, freelance, trabalho por conta própria nem estágio. Esses casos devem vir de bases complementares (State of Data Brazil, PNAD Contínua).
- **Diferença bruta.** Comparar a mediana de mulheres e homens sem controlar ocupação, região, escolaridade e tempo de casa mistura discriminação com composição. Esse controle é papel da EDA (#3) e do modelo (#4).
- **Valores em reais nominais de 2025.** Para comparar com outros anos, é preciso corrigir pela inflação.
- **Layout de 2020.** O MTE não publicou layout para 2024 ou 2025. Os códigos foram conferidos com o layout de 2020 e com os próprios dados. As colunas novas (`Ind Vínculo Abandonado`, `Categoria Trabalhador`) foram interpretadas pelos dados.
- **Faltantes conhecidos.** `cbo_nome` vem vazio quando o código de 6 dígitos não está na tabela oficial da CBO (erro de declaração). Família, área e nível continuam preenchidos. `horas_contratuais` vem vazio quando a RAIS traz `99` ou valores fora de 1 a 60.
