# Modelo salarial 1/3: preparo, baseline e MLflow, plano de implementação

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para executar este plano tarefa por tarefa. Os passos usam checkbox (`- [ ]`).

**Objetivo:** preparar a RAIS STEM 2025 para o modelo (jornada imputada, salário por hora, experiência potencial, divisão 70/10/20), medir os dois baselines no teste e registrá-los no MLflow. É o PR 1 da #4, que fecha a #51.

**Arquitetura:** pacote novo `src/modelo_salarial/` em camadas (`domain` → `application` → `adapters`), no formato de `src/agentes/`. Uma única classe de mediana por recorte (CBO × UF, depois CBO, depois geral, com mínimo de vínculos) serve para imputar a jornada e para o baseline. O caso de uso só conhece a porta `RegistroDeExperimentos`; o MLflow é um adaptador.

**Stack:** Python 3.12+, pandas e pyarrow (já no projeto), `mlflow` num grupo de dependências `ml`, `tomllib` (biblioteca padrão) para a configuração e pytest.

**Spec:** `docs/superpowers/specs/2026-11-22-modelo-faixa-salarial-design.md` (aprovada em 22/11). Leia as seções Dados, Avaliação, MLflow e Riscos para a #5.

## Restrições globais

- Edite e rode comandos só dentro da worktree. Não rode `dvc pull` nem commite o parquet ou qualquer coisa de `data/processed/`.
- Nenhum dado real da RAIS em teste ou fixture. Use dados sintéticos gerados no próprio teste (LGPD).
- Sexo e raça só aparecem nas métricas por grupo. Neste PR, nenhuma conta de previsão usa os dois.
- Valores de configuração ficam em `config/` (sem números mágicos): horas mínimas `10`, mínimo de vínculos por recorte `30`, divisão `0.7 / 0.1 / 0.2`, semente `42`, experimento `modelo-faixa-salarial` e URI padrão `sqlite:///mlflow.db`.
- `SEMANAS_POR_MES = 52 / 12` é definição, não configuração, e fica no domínio.
- Experiência potencial = `max(0, idade − anos_de_estudo − 6)`, com a tabela de anos de estudo da spec.
- Type hints em toda função pública; o domínio não importa pandas nem I/O; ruff com `line-length = 120`.
- Commits em Conventional Commits, em português, terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- `src/salarios.py`, `src/agentes/` e os testes existentes não mudam.

## Pontos de atenção na revisão

1. **CBO do teste que não aparece no treino:** a mediana cai no valor geral, e nenhuma previsão ou jornada fica `NaN`. Teste na Tarefa 2.
2. **CBO em que nenhum vínculo do treino tem jornada:** a imputação usa a mediana geral de jornada do treino. Teste na Tarefa 3.
3. **Experiência potencial negativa** (aprendiz de 15 anos com médio incompleto: 15 − 10 − 6 = −1): vira 0. Teste na Tarefa 3.
4. **Código de escolaridade fora da tabela:** erro explícito (`ValueError`) que cita o código, em vez de `NaN` silencioso. Teste na Tarefa 3.
5. **Grupo de sexo × raça sem nenhum vínculo no teste:** some do dicionário de métricas, em vez de virar `NaN` ou quebrar o MLflow. Teste na Tarefa 4.

---

### Tarefa 1: branch, configuração e divisão

**Arquivos:**
- Criar: `config/modelo_salarial.toml`, `config/anos_estudo.csv`, `src/modelo_salarial/__init__.py`, `src/modelo_salarial/domain/__init__.py`, `src/modelo_salarial/domain/modelos.py`, `src/modelo_salarial/application/__init__.py`, `src/modelo_salarial/application/preparo.py`
- Testar: `tests/modelo_salarial/test_preparo.py`

**Interfaces:**
- Produz:
  - `domain.modelos.SEMANAS_POR_MES: float`
  - `domain.modelos.ConfiguracaoPreparo(horas_minimas: float, n_minimo: int, proporcao_treino: float, proporcao_calibracao: float, proporcao_teste: float, semente: int)`, frozen. `__post_init__` gera `ValueError` se as proporções não somarem 1 (tolerância de 1e-9).
  - `application.preparo.Divisao(treino: pd.DataFrame, calibracao: pd.DataFrame, teste: pd.DataFrame)`, frozen.
  - `application.preparo.filtrar_jornada_curta(dados: pd.DataFrame, horas_minimas: float) -> pd.DataFrame`
  - `application.preparo.dividir(dados: pd.DataFrame, config: ConfiguracaoPreparo) -> Divisao`

- [ ] **Passo 1: renomear a branch e commitar spec e plano**

```bash
git branch -m feat/4-modelo-faixa-salarial feat/51-preparo-baseline-mlflow
git add docs/superpowers/specs/2026-11-22-modelo-faixa-salarial-design.md docs/superpowers/plans/2026-11-22-modelo-salarial-1-preparo-baseline.md
git commit -m "docs: spec do modelo de faixa salarial e plano do PR 1 (#51)"
```

A pasta da worktree mantém o nome antigo, e isso não muda nada.

- [ ] **Passo 2: criar `config/modelo_salarial.toml` e `config/anos_estudo.csv`**

`modelo_salarial.toml` tem as seções `[preparo]` (`horas_minimas = 10`, `n_minimo = 30`), `[divisao]` (`treino = 0.7`, `calibracao = 0.1`, `teste = 0.2`, `semente = 42`) e `[mlflow]` (`experimento = "modelo-faixa-salarial"`, `uri_padrao = "sqlite:///mlflow.db"`).

`anos_estudo.csv` tem as colunas `escolaridade_codigo,anos_estudo` e as linhas `1,0` `2,2` `3,5` `4,7` `5,9` `6,10` `7,12` `8,14` `9,16` `10,18` `11,22`.

- [ ] **Passo 3: escrever os testes que falham**

```python
def test_filtra_jornada_curta_e_mantem_jornada_ausente():
    dados = pd.DataFrame({"horas_contratuais": [9, 10, 44, None]})
    filtrados = filtrar_jornada_curta(dados, horas_minimas=10)
    assert filtrados["horas_contratuais"].tolist()[:2] == [10, 44]
    assert filtrados["horas_contratuais"].isna().sum() == 1
    assert len(filtrados) == 3

def test_divide_70_10_20_sem_sobreposicao_e_reprodutivel():
    dados = pd.DataFrame({"id": range(1000)})
    config = ConfiguracaoPreparo(10, 30, 0.7, 0.1, 0.2, semente=42)
    a, b = dividir(dados, config), dividir(dados, config)
    assert (len(a.treino), len(a.calibracao), len(a.teste)) == (700, 100, 200)
    ids = set(a.treino.id) | set(a.calibracao.id) | set(a.teste.id)
    assert len(ids) == 1000
    assert a.teste.id.tolist() == b.teste.id.tolist()

def test_semente_diferente_muda_a_divisao(): ...  # teste com semente 7 != teste com semente 42

def test_proporcoes_que_nao_somam_1_geram_erro():
    with pytest.raises(ValueError):
        ConfiguracaoPreparo(10, 30, 0.7, 0.2, 0.2, semente=42)
```

- [ ] **Passo 4:** `uv run pytest tests/modelo_salarial/test_preparo.py -v`. Esperado: FAIL na importação.
- [ ] **Passo 5: implementar.** `dividir` usa `numpy.random.default_rng(semente).permutation(len(dados))` e corta nas contagens `round(n × proporção)`, com o teste ficando com o resto. Os índices originais são preservados.
- [ ] **Passo 6:** `uv run pytest tests/modelo_salarial -v && uv run ruff check .`. Esperado: tudo passa.
- [ ] **Passo 7: commit** `feat: configuração e divisão treino/calibração/teste do modelo salarial (#51)`

### Tarefa 2: mediana por recorte

**Arquivos:**
- Criar: `src/modelo_salarial/application/mediana.py`
- Testar: `tests/modelo_salarial/test_mediana.py`

**Interfaces:**
- Produz: `MedianaPorRecorte`, frozen, com `por_cbo_uf: pd.Series`, `por_cbo: pd.Series` e `geral: float`.
  - `MedianaPorRecorte.ajustar(treino: pd.DataFrame, coluna: str, n_minimo: int) -> MedianaPorRecorte` (classmethod). Ignora os `NaN` de `coluna`. Só guarda os recortes com pelo menos `n_minimo` valores observados.
  - `MedianaPorRecorte.prever(dados: pd.DataFrame) -> pd.Series` devolve, na ordem: CBO × UF, depois CBO, depois geral. Mantém o índice de `dados` e nunca tem `NaN`.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_usa_cbo_uf_quando_tem_vinculos_suficientes():
    # 30 vínculos de 212405/DF a 5000 e 30 de 212405/SP a 9000; prever 212405/DF → 5000
def test_cai_na_cbo_quando_cbo_uf_tem_menos_que_o_minimo():
    # 212405/AC com 29 vínculos a 1000 e o resto como acima; prever AC → mediana nacional da CBO (≠ 1000)
def test_cai_na_mediana_geral_para_cbo_desconhecida():
    # prever cbo "999999" → mediana geral do treino; resultado sem NaN
def test_ignora_valores_ausentes_ao_contar_o_minimo():
    # 30 linhas de 212405/DF, 5 com coluna NaN → 25 observadas < 30 → não usa CBO × UF
```

Cada teste monta o DataFrame no próprio teste, com as colunas `cbo`, `uf` e `valor`, e verifica o valor exato devolvido.

- [ ] **Passo 2:** `uv run pytest tests/modelo_salarial/test_mediana.py -v`. Esperado: FAIL.
- [ ] **Passo 3: implementar** com `groupby(...).agg(["median", "count"])`, filtrando `count >= n_minimo`. O `prever` usa `map` por chave (CBO × UF como `MultiIndex`) e `fillna` em cascata.
- [ ] **Passo 4:** `uv run pytest tests/modelo_salarial -v`. Esperado: PASS.
- [ ] **Passo 5: commit** `feat: mediana por CBO × UF com recurso à CBO e ao geral (#51)`

### Tarefa 3: jornada imputada e variáveis derivadas

**Arquivos:**
- Modificar: `src/modelo_salarial/application/preparo.py`
- Testar: `tests/modelo_salarial/test_preparo.py`

**Interfaces:**
- Consome: `MedianaPorRecorte` (Tarefa 2), `Divisao`, `dividir` e `filtrar_jornada_curta` (Tarefa 1), `SEMANAS_POR_MES`.
- Produz:
  - `imputar_jornada(dados: pd.DataFrame, jornada: MedianaPorRecorte) -> pd.DataFrame` preenche `horas_contratuais` ausente e cria `jornada_imputada: bool`.
  - `derivar_variaveis(dados: pd.DataFrame, anos_estudo: Mapping[int, int]) -> pd.DataFrame` cria `salario_hora`, `ln_salario_hora`, `experiencia_potencial` e `cnae_divisao` (2 primeiros caracteres de `cnae_classe`). Gera `ValueError` se `horas_contratuais` tiver `NaN` ou se aparecer um `escolaridade_codigo` fora de `anos_estudo` (a mensagem cita o código).
  - `preparar(dados: pd.DataFrame, anos_estudo: Mapping[int, int], config: ConfiguracaoPreparo) -> Divisao` faz, nesta ordem: filtrar a jornada curta → dividir → ajustar a jornada **só no treino** (`MedianaPorRecorte.ajustar(treino, "horas_contratuais", config.n_minimo)`) → imputar nas três partes → derivar nas três partes.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_imputa_jornada_ausente_e_marca():
    # jornada da CBO × UF com mediana 40; linha sem horas → 40 e jornada_imputada True; linha com 44 → 44 e False
def test_cbo_sem_nenhuma_jornada_no_treino_usa_mediana_geral(): ...
def test_salario_hora_usa_52_semanas_por_12_meses():
    # remuneracao 4333.33, horas 40 → salario_hora == pytest.approx(25.0, rel=1e-3); ln_salario_hora == approx(log(25))
def test_experiencia_potencial_mincer():
    # idade 30, escolaridade 9 (16 anos) → 8; idade 15, escolaridade 6 (10 anos) → 0
def test_escolaridade_desconhecida_gera_erro():
    with pytest.raises(ValueError, match="12"):
        derivar_variaveis(dados_com_escolaridade_12, ANOS)
def test_cnae_divisao_sao_os_dois_primeiros_digitos():  # "62015" → "62"
def test_preparar_ajusta_jornada_so_no_treino():
    # monta os dados, roda dividir com a mesma config para saber quais índices caem no teste,
    # e põe 40 h em todo o treino e 20 h no teste, com uma linha do teste sem jornada.
    # Depois de preparar, essa linha tem 40 (mediana do treino), e não 20.
```

- [ ] **Passo 2:** `uv run pytest tests/modelo_salarial/test_preparo.py -v`. Esperado: FAIL nos testes novos.
- [ ] **Passo 3: implementar** as três funções em `preparo.py`.
- [ ] **Passo 4:** `uv run pytest tests/modelo_salarial -v && uv run ruff check .`. Esperado: PASS.
- [ ] **Passo 5: commit** `feat: jornada imputada, salário por hora e experiência potencial (#51)`

### Tarefa 4: métricas, geral e por recorte

**Arquivos:**
- Criar: `src/modelo_salarial/application/metricas.py`
- Modificar: `src/modelo_salarial/domain/modelos.py` (adicionar `Metricas`)
- Testar: `tests/modelo_salarial/test_metricas.py`

**Interfaces:**
- Produz:
  - `domain.modelos.Metricas(n: int, mae: float, mape: float, r2_log: float)`, frozen, com `como_dict(prefixo: str) -> dict[str, float]`, que devolve `{f"{prefixo}mae": ..., f"{prefixo}mape": ..., f"{prefixo}r2_log": ..., f"{prefixo}n": ...}`.
  - `application.metricas.calcular_metricas(real: pd.Series, previsto: pd.Series) -> Metricas`. A MAPE é uma fração (0,59, e não 59). `r2_log` é o R² entre `ln(real)` e `ln(previsto)`.
  - `application.metricas.metricas_por_recorte(dados: pd.DataFrame, previsto: pd.Series, coluna_real: str = "remuneracao_media") -> dict[str, Metricas]`, com as chaves `"geral"`, `"sem_jornada_imputada"` e `f"{sexo}__{raca_cor}"` (só grupos com pelo menos 1 vínculo).

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_mae_e_mape_feitos_a_mao():
    m = calcular_metricas(pd.Series([100.0, 200.0]), pd.Series([110.0, 150.0]))
    assert m.mae == pytest.approx(30.0)
    assert m.mape == pytest.approx((0.10 + 0.25) / 2)
    assert m.n == 2
def test_r2_log_perfeito_e_1():
    s = pd.Series([1000.0, 2000.0, 4000.0])
    assert calcular_metricas(s, s).r2_log == pytest.approx(1.0)
def test_por_recorte_separa_sexo_raca_e_sem_imputada():
    # 4 linhas: feminino/parda (2, uma imputada) e masculino/branca (2)
    r = metricas_por_recorte(dados, previsto)
    assert set(r) == {"geral", "sem_jornada_imputada", "feminino__parda", "masculino__branca"}
    assert r["sem_jornada_imputada"].n == 3
def test_grupo_sem_vinculos_nao_aparece():  # nenhuma linha feminino/indigena → chave ausente
def test_como_dict_usa_o_prefixo():
    assert set(Metricas(2, 1.0, 0.1, 0.5).como_dict("teste__")) == {"teste__mae", "teste__mape", "teste__r2_log", "teste__n"}
```

- [ ] **Passo 2:** `uv run pytest tests/modelo_salarial/test_metricas.py -v`. Esperado: FAIL.
- [ ] **Passo 3: implementar.** O R² é `1 − SS_res / SS_tot`, calculado à mão com numpy, sem scikit-learn.
- [ ] **Passo 4:** `uv run pytest tests/modelo_salarial -v`. Esperado: PASS.
- [ ] **Passo 5: commit** `feat: MAE, MAPE e R² em log, gerais e por sexo × raça (#51)`

### Tarefa 5: caso de uso do baseline, MLflow e CLI

**Arquivos:**
- Criar: `src/modelo_salarial/application/portas.py`, `src/modelo_salarial/application/experimento_baseline.py`, `src/modelo_salarial/adapters/__init__.py`, `src/modelo_salarial/adapters/arquivos.py`, `src/modelo_salarial/adapters/registro_mlflow.py`, `src/modelo_salarial/adapters/cli.py`, `src/modelo_salarial/__main__.py`
- Modificar: `pyproject.toml` e `uv.lock` (`uv add --group ml mlflow`), `.github/workflows/ci.yml` (job `test`: `uv sync --locked --dev --group ml`), `.gitignore` (`mlflow.db`, `mlruns/`, `models/`), `.env.example` (`MLFLOW_TRACKING_URI=` com um comentário de uma linha)
- Testar: `tests/modelo_salarial/test_experimento_baseline.py`, `tests/modelo_salarial/test_cli.py`

**Interfaces:**
- Consome: `preparar` (Tarefa 3), `MedianaPorRecorte` (Tarefa 2), `metricas_por_recorte` (Tarefa 4), `SEMANAS_POR_MES`.
- Produz:
  - `portas.RegistroDeExperimentos` (Protocol): `registrar(execucao: str, parametros: dict[str, str | int | float], metricas: dict[str, float]) -> str` devolve o id da execução.
  - `experimento_baseline.executar_baseline(dados: pd.DataFrame, anos_estudo: Mapping[int, int], config: ConfiguracaoPreparo, registro: RegistroDeExperimentos, versao_dados: str) -> dict[str, dict[str, Metricas]]` registra duas execuções e devolve `{"baseline-mediana-cbo-uf": ..., "baseline-mediana-hora": ...}`, cada uma com o resultado de `metricas_por_recorte` no **teste**.
    - `baseline-mediana-cbo-uf`: `MedianaPorRecorte.ajustar(treino, "remuneracao_media", n_minimo).prever(teste)`.
    - `baseline-mediana-hora`: `MedianaPorRecorte.ajustar(treino, "salario_hora", n_minimo).prever(teste) × teste.horas_contratuais × SEMANAS_POR_MES`.
    - Parâmetros em cada execução: os campos de `config`, `versao_dados`, `n_treino`, `n_calibracao` e `n_teste`, `pct_jornada_imputada_teste` e `modelo` (o nome da execução). Métricas: `como_dict(f"{recorte}__")` de cada recorte.
  - `arquivos.ler_rais(caminho: Path) -> pd.DataFrame` lê só as colunas `cbo, uf, escolaridade_codigo, idade, tempo_emprego_meses, cnae_classe, tamanho_estabelecimento, horas_contratuais, remuneracao_media, sexo, raca_cor`.
  - `arquivos.ler_anos_estudo(caminho: Path) -> dict[int, int]`, `arquivos.ler_configuracao(caminho: Path) -> tuple[ConfiguracaoPreparo, str, str]` (configuração, experimento e URI padrão) e `arquivos.md5_do_dvc(caminho: Path) -> str` (lê a linha `md5:` do `.dvc` com regex, sem PyYAML; gera `ValueError` se não houver).
  - `registro_mlflow.RegistroMlflow(uri: str, experimento: str)` implementa a porta com `mlflow.set_tracking_uri`, `set_experiment`, `start_run(run_name=execucao)`, `log_params` e `log_metrics`.
  - `cli.main(argv: list[str] | None = None) -> None`, com o subcomando `baseline [--parquet PATH] [--ano 2025]`. Padrões: `data/processed/rais_stem_{ano}_brasil.parquet` e o `.dvc` ao lado. A URI vem de `MLFLOW_TRACKING_URI` (carregada com `python-dotenv`) ou do padrão do `config`. No fim, imprime uma linha por baseline com o MAE, a MAPE (em %) e o R² em log do recorte `geral`, e a meta do go, `MAE ≤ 0,85 × MAE do baseline-mediana-cbo-uf`.

- [ ] **Passo 1: adicionar a dependência**

`uv add --group ml mlflow`. Depois, `uv sync --dev --group ml`. Esperado: `uv.lock` atualizado e `uv run python -c "import mlflow"` sem erro.

- [ ] **Passo 2: escrever os testes que falham**

```python
class RegistroFalso:
    def __init__(self): self.execucoes = []
    def registrar(self, execucao, parametros, metricas):
        self.execucoes.append((execucao, parametros, metricas)); return str(len(self.execucoes))

def test_executar_baseline_registra_as_duas_execucoes(dados_sinteticos):
    registro = RegistroFalso()
    resultado = executar_baseline(dados_sinteticos, ANOS, CONFIG, registro, versao_dados="abc123")
    assert [e[0] for e in registro.execucoes] == ["baseline-mediana-cbo-uf", "baseline-mediana-hora"]
    assert registro.execucoes[0][1]["versao_dados"] == "abc123"
    assert "geral__mae" in registro.execucoes[0][2]
    assert resultado["baseline-mediana-cbo-uf"]["geral"].n == registro.execucoes[0][1]["n_teste"]

def test_baseline_nao_usa_sexo_nem_raca(dados_sinteticos):
    # embaralhar sexo e raca_cor não muda o MAE geral de nenhuma das duas execuções

def test_md5_do_dvc_le_a_linha_md5(tmp_path):
    (tmp_path / "x.parquet.dvc").write_text("outs:\n- md5: 0123abcd\n  size: 10\n  path: x.parquet\n")
    assert md5_do_dvc(tmp_path / "x.parquet.dvc") == "0123abcd"

def test_cli_baseline_ponta_a_ponta(tmp_path, monkeypatch, dados_sinteticos):
    # grava dados_sinteticos em tmp_path/rais_stem_2025_brasil.parquet e um .dvc falso ao lado
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path}/mlflow.db")
    main(["baseline", "--parquet", str(tmp_path / "rais_stem_2025_brasil.parquet")])
    runs = mlflow.search_runs(experiment_names=["modelo-faixa-salarial"])
    assert set(runs["tags.mlflow.runName"]) == {"baseline-mediana-cbo-uf", "baseline-mediana-hora"}
    assert runs["metrics.geral__mae"].notna().all()
```

`dados_sinteticos` é uma fixture em `tests/modelo_salarial/conftest.py`: umas 600 linhas geradas com `numpy.random.default_rng(0)` e todas as colunas de `ler_rais`, incluindo umas jornadas ausentes, duas CBOs, três UFs, os dois sexos e três raças.

- [ ] **Passo 3:** `uv run pytest tests/modelo_salarial -v`. Esperado: FAIL nos testes novos.
- [ ] **Passo 4: implementar** a porta, o caso de uso, os adaptadores, a CLI e `__main__.py` (que só chama `cli.main()`). A montagem acontece só em `cli.main`.
- [ ] **Passo 5: atualizar** `.gitignore`, `.env.example` e `ci.yml`, como na lista de arquivos.
- [ ] **Passo 6:** `uv run pytest -q && uv run ruff check .`. Esperado: a suíte inteira passa, incluindo os testes antigos.
- [ ] **Passo 7: commit** `feat: baseline do modelo salarial registrado no MLflow (#51)`

### Tarefa 6: rodar no parquet real e documentar

**Arquivos:**
- Modificar: `README.md` (seção "Como executar": `uv sync --dev --group ml` e `uv run python -m src.modelo_salarial baseline`, com uma linha sobre `MLFLOW_TRACKING_URI` e o `uv run mlflow ui --backend-store-uri sqlite:///mlflow.db`)
- Criar: `docs/modelo_salarial.md` (página curta: para que serve, preparo, baseline, como rodar, os números do baseline com data, link para a spec e a tabela de jornada ausente por grupo, que é risco para a #5)

- [ ] **Passo 1: rodar no dado real**

`uv run python -m src.modelo_salarial baseline`. Esperado: duas linhas de resultado. O MAE geral do `baseline-mediana-cbo-uf` deve ficar perto de R$ 3.600, porque na exploração deu R$ 3.609 com 80/20 e sem imputação. Uma diferença acima de uns 10% é sinal de bug no preparo: **pare e investigue** com superpowers:systematic-debugging antes de seguir.

- [ ] **Passo 2:** `uv run mlflow ui --backend-store-uri sqlite:///mlflow.db` e conferir as duas execuções, com `versao_dados` igual ao md5 do `.dvc` e as métricas por grupo. Depois, `git status` não pode mostrar `mlflow.db`, `mlruns/` nem nada de `data/processed/`.
- [ ] **Passo 3: escrever** o README e `docs/modelo_salarial.md` com os números do Passo 1.
- [ ] **Passo 4: commit** `docs: como rodar o baseline do modelo salarial e resultados (#51)`

### Tarefa 7: rascunho do ADR-012 no `artemishub_docs`

**Arquivos (outro repo):** `docs/adr/012-modelo-salarial.md`, `docs/adr/index.md` e `mkdocs.yml` (nav), numa worktree criada a partir da raiz do orquestrador com `python scripts/worktree.py new docs docs/51-adr-modelo-salarial`.

- [ ] **Passo 1: escrever o ADR** no formato do ADR-002 (contexto, decisão, alternativas, consequências, status `Proposto`). Decisão: abordagem de Oaxaca-Blinder com o grupo de referência configurável (padrão homem branco, ainda a confirmar), LightGBM quantílico com CQR calibrado por sexo × raça, experiência potencial no lugar da idade, MLflow para os experimentos (local agora, DagsHub depois). Alternativas: o modelo cego (A), scikit-learn `HistGradientBoosting`, regressão quantílica linear.
- [ ] **Passo 2:** `mkdocs build --strict` no repo do docs. Esperado: sem avisos.
- [ ] **Passo 3: commit** `docs: ADR-012 (proposto) do modelo de faixa salarial` e push. O PR fica em draft e é citado no PR do agents.

A página `arquitetura/modelo-salarial.md` só muda no PR 3, como diz a spec.

---

## Ao terminar

- [ ] `uv run pytest -q && uv run ruff check .` verdes.
- [ ] superpowers:requesting-code-review na branch inteira.
- [ ] Push com `git push -u origin feat/51-preparo-baseline-mlflow` e PR em draft para `staging`. Título: `feat: preparo, baseline e MLflow do modelo salarial`. Descrição com `Closes #51`, `Parte de #4`, o link do PR do ADR, os números do baseline e o lembrete de que o parquet e o MLflow ficam fora do git.
