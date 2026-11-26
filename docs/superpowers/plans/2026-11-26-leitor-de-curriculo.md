# Leitor de currículo (agents) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um serviço isolado que recebe um PDF ou uma foto de currículo, devolve o texto e os trechos que parecem dados pessoais, e roda só na CPU, com um modelo aberto escolhido pela Ana Julia.

**Architecture:** Imagem própria no `artemishub_agents`, separada da imagem dos agents. FastAPI com uma rota, `POST /v1/ler`, que implementa `contratos/leitor.v1.schema.json` do backend. Camadas hexagonais: o modelo de leitura de imagem fica atrás de uma porta (`ModeloDeLeitura`), para trocar de modelo sem mexer no resto. Sem banco, sem saída para a internet, sem gravar arquivo.

**Tech Stack:** Python 3.12, uv, FastAPI, PyMuPDF, Pillow, o modelo escolhido na Task 1 (candidatos: RapidOCR/PaddleOCR em ONNX, docTR, Florence-2), MLflow no DagsHub para o teste comparativo, pytest.

**Spec:** `artemishub_backend/docs/superpowers/specs/2026-11-26-curriculo-design.md` (o desenho mora no backend; este plano cobre só o leitor).

## Global Constraints

- Só CPU. Container de até 2 vCPU e 4 GiB.
- Arquivo só na memória: nada em disco, nada em log, nada em trace.
- Limites: até 5 páginas por PDF; até 25 megapixels por imagem (`Image.MAX_IMAGE_PIXELS`); até 30 s de leitura por página; tempo total até 85 s (o backend espera 90).
- Contrato: o de `artemishub_backend/contratos/leitor.v1.schema.json`. Copie o schema para `contratos/` neste repo e valide nos testes.
- Licença do modelo e das bibliotecas: permissiva (Apache, MIT ou BSD). GPL e licenças com restrição de uso ficam de fora.
- Dados de teste: currículos **fictícios**. Nenhum currículo real em fixture, no repositório ou no MLflow (LGPD).

## Review Focus

- **PDF com algumas páginas com texto e outras escaneadas**: origem `pdf_escaneado` e as páginas sem texto lidas pelo modelo. Teste na Task 2.
- **Foto de lado ou de cabeça para baixo** (EXIF de orientação): corrigida antes da leitura. Teste na Task 2.
- **PDF com senha ou corrompido, e imagem bomba** (dimensões gigantes): 422 rápido, sem estourar a memória. Teste na Task 2.
- **Currículo sem nenhum dado pessoal**: `trechos` vazio, sem erro. Teste na Task 3.
- **Duas leituras ao mesmo tempo**: as duas respondem, sem misturar resultados (o modelo carregado é compartilhado, o estado da leitura não). Teste na Task 2.

---

### Task 1: Teste comparativo e escolha do modelo (Ana Julia decide)

**Files:**
- Create: `avaliacao/leitor/README.md`, `avaliacao/leitor/comparar.py`, `avaliacao/leitor/gabarito/` (textos esperados), `data/leitor/.gitignore` (as imagens ficam no DVC)
- Create no `artemishub_docs`: `docs/adr/0NN-modelo-de-leitura-de-curriculo.md`

**Interfaces:**
- Produces: o nome do modelo escolhido e a configuração dele (pesos, idioma, parâmetros), usados na Task 2 como `MODELO_PADRAO`.

- [ ] **Step 1: Montar o conjunto fictício.** Pelo menos 10 currículos fictícios em português, com acentos, siglas (SQL, AWS, UnB) e layouts de uma e duas colunas. Cada um em três versões: PDF com texto, PDF escaneado e foto de celular em condições ruins (luz fraca, ângulo, papel amassado). Gabarito: o texto esperado de cada um. Imagens versionadas com DVC.
- [ ] **Step 2: Rodar os candidatos na CPU** do mesmo tamanho do container (2 vCPU, 4 GiB), com `comparar.py`: RapidOCR (PaddleOCR em ONNX), docTR e Florence-2 (base). Para cada um: erro por caractere (CER) e por palavra (WER), tempo por página (mediana e p95), memória máxima e tamanho da imagem do container.
- [ ] **Step 3: Registrar no MLflow** (servidor do DagsHub) um run por modelo, com as métricas e a versão dos pesos.
- [ ] **Step 4: A Ana decide.** Critérios sugeridos no desenho: p95 de até 10 s por página e memória de até 2 GiB. O limite de erro é dela. Ela registra a escolha num ADR no `artemishub_docs`, com a tabela de resultados e os modelos descartados.
- [ ] **Step 5: Commit**

```bash
git add avaliacao/leitor data/leitor/.gitignore *.dvc
git commit -m "feat: teste comparativo dos modelos de leitura de currículo"
```

---

### Task 2: Serviço `leitor` com extração de PDF e leitura de imagem

**Files:**
- Create: `src/leitor/domain/leitura.py`, `src/leitor/application/ler.py`, `src/leitor/application/portas.py`, `src/leitor/adapters/pdf.py`, `src/leitor/adapters/modelo_<escolhido>.py`, `src/leitor/adapters/api.py`, `contratos/leitor.v1.schema.json` (cópia do backend)
- Test: `tests/leitor/test_ler.py`, `tests/leitor/test_api.py`, `tests/leitor/test_contrato.py`

**Interfaces:**
- Consumes: modelo escolhido na Task 1
- Produces:
  - `class ModeloDeLeitura(Protocol): nome: str; def ler_imagem(self, imagem: PIL.Image.Image) -> str`
  - `def ler(conteudo: bytes, tipo: Literal["pdf", "jpeg", "png"], modelo: ModeloDeLeitura) -> Leitura`, com `Leitura(texto: str, origem: Literal["pdf_texto", "pdf_escaneado", "foto"], modelo: str)` (o `modelo` é `"pymupdf"` quando nenhuma página precisou do modelo)
  - `class ArquivoIlegivel(ValueError)` → 422
  - `POST /v1/ler` com `Authorization: Bearer` (token em `ARTEMIS_LEITOR_TOKEN`), `GET /health`

- [ ] **Step 1: Write the failing tests** com um `ModeloFake` (devolve um texto fixo e conta as chamadas) e arquivos gerados no próprio teste (PDF com PyMuPDF, imagem com Pillow):
  - PDF só com texto: `origem == "pdf_texto"` e o modelo não é chamado.
  - PDF misto: só as páginas sem texto chamam o modelo; `origem == "pdf_escaneado"`.
  - JPEG com EXIF de rotação 90°: a imagem chega ao modelo já na orientação certa.
  - 6 páginas, PDF com senha, bytes corrompidos, imagem de 30 megapixels: `ArquivoIlegivel`.
  - API: sem token → 401; `Content-Type` fora dos três → 415; resposta válida contra o schema copiado; nenhum log com o texto lido (`caplog`).
  - Duas chamadas simultâneas à API com arquivos diferentes devolvem cada uma o seu texto.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/leitor -q`
Expected: FAIL

- [ ] **Step 3: Implement**: PyMuPDF por página (página com menos de 20 caracteres visíveis conta como escaneada e é renderizada a 200 dpi); `ImageOps.exif_transpose` antes do modelo; limites das Global Constraints; o modelo é carregado uma vez no startup e compartilhado.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/leitor -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/leitor contratos tests/leitor pyproject.toml uv.lock
git commit -m "feat: serviço leitor de currículo com PDF e imagem"
```

---

### Task 3: Detecção de trechos pessoais

**Files:**
- Create: `src/leitor/domain/trechos.py`
- Modify: `src/leitor/application/ler.py`, `src/leitor/adapters/api.py`
- Test: `tests/leitor/test_trechos.py`

**Interfaces:**
- Produces: `def trechos_pessoais(texto: str) -> list[TrechoPessoal]`, com `TrechoPessoal(categoria: Literal["email", "telefone", "cpf", "cep", "nome", "endereco"], texto: str)`, no máximo 50, cada `texto` com até 300 caracteres e aparecendo literalmente no texto lido.

- [ ] **Step 1: Write the failing tests**: e-mail, telefone, CPF e CEP nos formatos da Task 1 do plano do backend; **nome** = a primeira linha não vazia, se tiver de 2 a 6 palavras e nenhum dígito; **endereço** = linhas que começam com Rua, R., Avenida, Av., Travessa, Quadra, SQN, SQS, SHIS, QI, QL, Alameda ou Rodovia, ou que trazem CEP; currículo sem nada disso → lista vazia; nenhum trecho repetido.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/leitor/test_trechos.py -q`
Expected: FAIL

- [ ] **Step 3: Implement** com expressões regulares e as heurísticas acima. É uma sugestão para a tela de conferência: o backend aplica a máscara obrigatória de qualquer jeito.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/leitor -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/leitor tests/leitor
git commit -m "feat: sugestão de trechos pessoais para a conferência"
```

---

### Task 4: Imagem própria e isolamento

**Files:**
- Create: `leitor.Dockerfile`, `.dockerignore` (se não existir), seção no `README.md` e no `AGENTS.md`
- Modify: `docker-compose.yml` do orquestrador (PR separado no `artemishub_orchestration`): serviço `leitor` com `network_mode` interno e sem volume

- [ ] **Step 1:** Imagem baseada em `python:3.12-slim`, com só as dependências do leitor (sem LangGraph nem torch, a não ser que o modelo escolhido exija), usuário sem privilégios e pesos do modelo baixados no build, não em tempo de execução.
- [ ] **Step 2: Verify** com `docker build -f leitor.Dockerfile -t artemis-leitor .` e `docker run --network none -e ARTEMIS_LEITOR_TOKEN=teste -p 8002:8000 artemis-leitor`. Com um PDF fictício, `curl -H "Authorization: Bearer teste" -H "Content-Type: application/pdf" --data-binary @cv.pdf localhost:8002/v1/ler` responde 200. Registre no README o tamanho da imagem e o tempo de subida.
- [ ] **Step 3: Commit**

```bash
git add leitor.Dockerfile .dockerignore README.md AGENTS.md
git commit -m "ci: imagem isolada do leitor de currículo"
```
