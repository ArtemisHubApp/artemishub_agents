# Pipeline de CI/CD do artemishub_agents: plano de implementação

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para executar este plano tarefa por tarefa. Os passos usam checkbox (`- [ ]`) para acompanhamento.

**Objetivo:** todo PR e todo push na `main` passam por lint, testes e checagem de segurança; dados, avaliações dos agentes e imagem Docker entram em fases, conforme o roadmap (semanas 4 a 6).

**Arquitetura:** GitHub Actions com `uv`. Um workflow de CI rápido (sem segredos, sem LLM, sem dados do DVC) roda em todo PR. Workflows separados, mais caros, rodam sob demanda ou por agenda: dados (precisa do remote do DVC), avaliação dos agentes (precisa da chave do LLM) e entrega (imagem no GHCR).

**Stack:** GitHub Actions, uv, Ruff, pytest, DVC, Docker, GHCR, Dependabot.

**Referência:** [CI do artemishub_rag](https://github.com/ArtemisHubApp/artemishub_rag/blob/main/.github/workflows/ci.yml) e [docs/multiagentes.md](../../multiagentes.md).

## Situação atual (17/11/2026)

| Item | Estado |
|---|---|
| Testes | 16 testes passam com `uv run python -m pytest`, mas `uv run pytest` falha na coleta (`ModuleNotFoundError: No module named 'src'`): falta `pythonpath` no pytest |
| Lint | Ruff não está nas dependências; `ruff check .` acusa 1 erro (I001 em `tests/test_salarios.py`) |
| CI | nenhum workflow em `.github/workflows/` |
| DVC | `.dvc/config` vazio: **não há remote**. O parquet de 50 MB só existe na máquina de quem rodou o pipeline |
| Testes e dados | os testes atuais usam dados sintéticos e não dependem do parquet, então o CI básico não precisa do DVC |

## Restrições globais

- Python `>=3.12` (do `pyproject.toml`); a matriz de CI usa 3.12 e 3.13. O RAG testa 3.11, mas aqui 3.11 não é suportado.
- Dependências instaladas com `uv sync --locked`: o CI falha se o `uv.lock` estiver desatualizado.
- Workflows com `permissions: contents: read` por padrão; só o job de publicação recebe `packages: write`.
- Nenhum segredo (chave do LLM, credencial do DVC, Langfuse) é usado no workflow de PR: PRs de fork não têm acesso a segredos e o CI precisa passar mesmo assim.
- Testes de PR nunca chamam o LLM de verdade: os agentes recebem um cliente falso nos testes.

## Pontos de atenção da revisão

1. **`uv.lock` desatualizado:** quem adiciona dependência e esquece de commitar o lock deve ver o CI falhar com mensagem clara, não um erro de import em outro lugar.
2. **Teste que depende do parquet por engano:** um teste novo que leia `data/processed/` passa na máquina de quem tem o arquivo e quebra no CI. O CI precisa rodar num checkout limpo, sem o parquet.
3. **Tabelas agregadas defasadas:** `data/agregados/*.csv` são geradas a partir do parquet. Se alguém mudar `src/salarios.py` e não regenerar, o agente responde com números antigos. Coberto na Fase 2.
4. **Chave do LLM vazando em log:** avaliações online imprimem prompts e respostas; a chave não pode aparecer. Usar `secrets` e nunca dar `echo` em variável de ambiente.
5. **Avaliação online cara rodando em todo push:** fica atrás de rótulo no PR, `workflow_dispatch` ou agenda, nunca em todo commit.

---

## Fase 1: CI básico (agora, antes do código dos agentes)

### Tarefa 1: deixar lint e testes rodáveis com um comando

**Arquivos:**
- Modificar: `pyproject.toml`
- Modificar: `tests/test_salarios.py` (ordem dos imports)
- Modificar: `uv.lock`

- [ ] **Passo 1:** confirmar a falha atual. Rodar `uv run pytest -q`. Esperado: `ModuleNotFoundError: No module named 'src'` em 3 arquivos.
- [ ] **Passo 2:** em `pyproject.toml`, adicionar `[tool.pytest.ini_options]` com `pythonpath = ["."]` e `testpaths = ["tests"]`.
- [x] **Passo 3:** adicionar Ruff ao grupo dev com `uv add --dev ruff` e a seção `[tool.ruff]` com `line-length = 120` (o estilo atual do código), `target-version = "py312"` e `extend-exclude = [".claude"]` (as skills não são código do projeto); em `[tool.ruff.lint]`, `select = ["E", "F", "I", "B", "UP"]`.
- [x] **Passo 4:** rodar `uv run ruff check .`. Esperado: `All checks passed!`. Se a regra `B` ou `UP` apontar algo que não seja trivial, corrigir no código, não desligar a regra.
- [x] **Passo 5:** rodar `uv run pytest -q`. Esperado: `16 passed`.
- [x] **Passo 6:** commit `chore: configura pytest e ruff para rodar com uv`.

### Tarefa 2: workflow de CI

**Arquivos:**
- Criar: `.github/workflows/ci.yml`

O workflow tem dois jobs: `lint` (uma vez) e `test` (matriz 3.12 e 3.13).

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          enable-cache: true
      - run: uv sync --locked --dev
      - run: uv run ruff check .

  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          enable-cache: true
          python-version: ${{ matrix.python-version }}
      - run: uv sync --locked --dev
      - run: uv run pytest -q
```

- [x] **Passo 1:** `ruff format --check` fica de fora por enquanto: `uv run ruff format .` reescreveria 6 dos 10 arquivos (o código usa um estilo mais compacto que o do formatador) e causaria conflito com branches abertas. Adotar depois, num PR só de formatação (`style: aplica ruff format`), combinado com a equipe.
- [x] **Passo 2:** criar o arquivo acima.
- [x] **Passo 3:** abrir o PR e conferir na aba Actions que `lint`, `test (3.12)` e `test (3.13)` ficam verdes.
- [ ] **Passo 4 (ponto de atenção 1):** num branch descartável, adicionar uma dependência ao `pyproject.toml` sem atualizar o lock e confirmar que `uv sync --locked` falha. Apagar o branch.
- [ ] **Passo 5:** commit `ci: lint e testes com uv em Python 3.12 e 3.13`.

### Tarefa 3: proteção da main, Dependabot e segurança básica

**Arquivos:**
- Criar: `.github/dependabot.yml`
- Criar: `.github/pull_request_template.md`
- Modificar: `.github/workflows/ci.yml` (job `security`)

- [ ] **Passo 1:** `dependabot.yml` com dois ecossistemas, ambos semanais: `github-actions` (diretório `/`) e `uv` (diretório `/`).
- [ ] **Passo 2:** template de PR com: o que muda, como testar, `Closes #<número>` (regra do README) e checklist "rodei `uv run pytest` e `uv run ruff check .`".
- [ ] **Passo 3:** job `security` no `ci.yml`: gitleaks para segredos commitados (em repositório de organização, a `gitleaks-action@v2` exige a licença gratuita em `secrets.GITLEAKS_LICENSE`; a alternativa sem licença é rodar o binário do gitleaks direto, com `gitleaks git --redact`) e `uvx pip-audit` sobre as dependências exportadas (`uv export --no-hashes > req.txt && uvx pip-audit -r req.txt`).
- [x] **Passo 4:** ruleset `main` ativo (#33): bloqueia apagar a branch e force push, exige PR (0 aprovações) e os checks `lint`, `test (3.12)` e `test (3.13)`. Quando o job `security` existir, adicioná-lo aos checks obrigatórios em Settings → Rules → Rulesets → `main`.
- [ ] **Passo 5:** commit `ci: dependabot, template de PR e checagem de segurança`.

## Fase 2: dados versionados (depende de decisão da equipe)

### Tarefa 4: remote do DVC e checagem das tabelas agregadas

**Decisão (17/11/2026):** o remote do DVC é o **DagsHub** (plano gratuito, 10 GB, sem cartão). Ele foi feito para DVC, cada pessoa usa o próprio login e o CI só precisa de um token. Alternativas avaliadas: Google Drive (conta de serviço não tem cota, então não consegue fazer `dvc push`), Cloudflare R2 e S3/GCS (pedem cartão). Hoje `.dvc/config` está vazio: sem remote, nenhum outro computador (nem o CI) consegue baixar o parquet.

**Responsável:** Camila (Engenharia de Dados · DevOps).

**Arquivos:**
- Modificar: `.dvc/config` (remote padrão, só a URL)
- Modificar: `README.md` (como baixar os dados)
- Criar: `.github/workflows/data.yml`

- [ ] **Passo 1:** no DagsHub, criar o repositório conectado ao GitHub (New Repository → Connect a repository → GitHub → `ArtemisHubApp/artemishub_agents`) e dar acesso de escrita a quem roda o pipeline da RAIS.
- [ ] **Passo 2:** configurar o remote. A URL vai para o git e o login fica em `.dvc/config.local`, que não é commitado:

```bash
uv run dvc remote add -d origin https://dagshub.com/<dono>/artemishub_agents.dvc
uv run dvc remote modify origin --local auth basic
uv run dvc remote modify origin --local user <usuario-dagshub>
uv run dvc remote modify origin --local password <token-dagshub>
uv run dvc push
```

- [ ] **Passo 3:** conferir de outra máquina (ou de um clone limpo) com `uv run dvc pull`. Esperado: `data/processed/rais_stem_2025_brasil.parquet` com o md5 `9736758f3a0d4570a6547666df680861` do `.dvc`.
- [ ] **Passo 4:** criar um token só de leitura para o CI e salvar como `secrets.DAGSHUB_USER` e `secrets.DAGSHUB_TOKEN` no repositório; documentar no README o `dvc pull` para a equipe.
- [ ] **Passo 5:** `data.yml` roda só quando mudam `src/salarios.py`, `src/rais_*.py`, `data/**` ou `config/**` (filtro `paths`), e também por `workflow_dispatch`.
- [ ] **Passo 6 (ponto de atenção 3):** passos do job: configurar o login com `uv run dvc remote modify origin --local user/password` a partir dos `secrets`, depois `uv run dvc pull data/processed/rais_stem_2025_brasil.parquet.dvc`, depois `uv run python -m src.salarios gerar --ano 2025`, depois `git diff --exit-code data/agregados/`. Esperado: sem diferença. Se houver, o job falha com a mensagem "rode `python -m src.salarios gerar` e commite `data/agregados/`".
- [ ] **Passo 7:** commit `ci: confere se as tabelas agregadas batem com o parquet do DVC`.

## Fase 3: avaliação dos agentes (semanas 4 e 5)

### Tarefa 5: testes offline dos agentes no CI de PR

Entra junto com o código de `src/agents/`. Não muda o workflow: os testes ficam em `tests/` e rodam no job `test` existente.

- [ ] **Passo 1:** cada agente recebe o cliente de LLM por parâmetro; os testes usam um cliente falso que devolve respostas fixas.
- [ ] **Passo 2:** casos mínimos, tirados das regras de [multiagentes.md](../../multiagentes.md): a Validação reprova rascunho com citação que não está nas evidências; reprova número que não bate com a saída de `consultar`; reprova rascunho sem o aviso de diferença bruta; o Orquestrador para depois de 1 nova tentativa e devolve abstenção.
- [ ] **Passo 3:** conferir no PR que esses testes rodam sem nenhuma variável de ambiente de LLM definida.

### Tarefa 6: avaliação online com o LLM real

**Arquivos:**
- Criar: `.github/workflows/eval.yml`
- Criar: `evaluation/perguntas.jsonl` (no formato do `artemishub_rag/evaluation/`)

- [ ] **Passo 1 (ponto de atenção 5):** gatilhos: rótulo `run-evals` no PR, `workflow_dispatch` e agenda semanal (`cron: "0 6 * * 1"`).
- [ ] **Passo 2 (ponto de atenção 4):** a chave do LLM vem de `secrets.LLM_API_KEY`, exposta só no passo que roda a avaliação, num `environment` chamado `eval` com aprovação manual.
- [ ] **Passo 3:** métricas com limite mínimo que falham o job: proporção de citações válidas, números iguais aos da ferramenta, presença dos avisos de limitação e abstenção correta em perguntas sem evidência. Os limites são definidos pela equipe na primeira execução e registrados no próprio workflow.
- [ ] **Passo 4:** o relatório da execução é salvo como artefato do workflow (`actions/upload-artifact`) e, na semana 5, enviado ao Langfuse.
- [ ] **Passo 5:** na semana 5, incluir no mesmo conjunto as perguntas de injeção de prompt (via pergunta e via currículo).

## Fase 4: entrega contínua (semana 6, quando o orquestrador virar API)

### Tarefa 7: imagem Docker publicada no GHCR

**Arquivos:**
- Criar: `Dockerfile` (multi-stage com `uv`, imagem final sem ferramentas de build)
- Criar: `.dockerignore` (`.venv`, `data/raw`, `data/processed`, `.git`, `.claude`)
- Criar: `.github/workflows/release.yml`

- [ ] **Passo 1:** no CI de PR, um job `docker` só faz `docker build` (sem publicar) para pegar Dockerfile quebrado cedo.
- [ ] **Passo 2:** `release.yml` roda em push na `main` e em tags `v*`; publica `ghcr.io/artemishubapp/artemishub_agents` com as tags `sha-<commit>`, `main` e a versão. Só esse job tem `permissions: packages: write`.
- [ ] **Passo 3:** a imagem não leva o parquet. A API só precisa de `data/agregados/` (que está no git); se precisar do parquet no futuro, ele é baixado do remote do DVC na inicialização.
- [ ] **Passo 4:** o deploy em si (onde a API roda) é decidido com o `artemishub_backend` e registrado em ADR no `artemishub_docs`. Até lá, o CD termina na imagem publicada.

## Ordem sugerida

| Fase | Quando | Bloqueio |
|---|---|---|
| 1 (Tarefas 1 a 3) | já | nenhum |
| 2 (Tarefa 4) | semana 4 | nenhum: remote definido (DagsHub), implementação com a Camila |
| 3 (Tarefas 5 e 6) | semanas 4 e 5 | código de `src/agents/`; chave do LLM em `secrets` |
| 4 (Tarefa 7) | semana 6 | orquestrador exposto como API; ADR de deploy |
