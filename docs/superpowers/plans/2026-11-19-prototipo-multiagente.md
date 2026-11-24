# Plano: primeiro protótipo multiagente com Langfuse

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (escolhido pela Amanda: execução nesta sessão, com revisão final da branch).

**Goal:** fluxo Orquestrador → (Pesquisa ∥ Análise/dados) → Análise/síntese → Validação → resposta formatada pelo Orquestrador, rodando por um comando e rastreado no Langfuse.

**Architecture:** hexagonal em `src/agentes/`. `domain` tem as regras puras (guardrail, intenção, validação, formatação, rascunho padrão e prompt). `application` tem as portas e o grafo LangGraph. `adapters` tem o RAG por subprocesso, a RAIS (`src/salarios.py`), o LLM (`langchain-openai`, Gemini compatível com OpenAI) e o rastreio (Langfuse 5). A montagem acontece em `src/agentes/demo.py`.

**Tech Stack:** Python 3.12, LangGraph 1.2, langchain-openai 1.8, Langfuse 5.2, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-11-19-prototipo-multiagente-design.md`

## Global Constraints

- Uma chamada ao LLM por pergunta (duas com retry). Sem LLM configurado, usa o redator determinístico.
- O LLM nunca calcula números. Os números vêm de `src.salarios.consultar` e são formatados em `R$ 1.234,56` e `17,3%`.
- Validação determinística. Retry no máximo 1 vez; depois disso, abstenção.
- Texto do RAG e da usuária é dado, nunca instrução: entra no prompt entre delimitadores, e o roteamento não depende do LLM.
- Langfuse só liga com `LANGFUSE_PUBLIC_KEY` e `LANGFUSE_SECRET_KEY`. Testes e CI rodam sem ele.
- Nomes estáveis no Langfuse:
  - trace `responder-pergunta` (root `agent`);
  - nós do grafo `orquestrador`, `pesquisa`, `analise_dados`, `analise_sintese`, `validacao` e `resposta`;
  - observações `verificar-entrada` (guardrail), `buscar-direitos` (retriever), `consultar-rais` (tool), `redigir-rascunho` (generation) e `validar-rascunho` (evaluator).
- `.env`: lê o do agents e, como reserva, o do `artemishub_rag` (`ARTEMIS_RAG_DIR`, padrão `../artemishub_rag`), sem sobrescrever o que já existe.

## Review Focus

1. Pergunta com injeção ("ignore as instruções anteriores…"): bloqueada sem acionar RAG nem LLM.
2. LLM que inventa número ou cita `[FONTE 9]`: a Validação reprova, o retry corrige ou a resposta vira abstenção.
3. Ocupação ou UF não encontradas: a consulta usa `BR` ou avisa que não há dados, sem número inventado.
4. RAG indisponível (sem índice ou subprocesso falhou): a Pesquisa registra a falha e a resposta não cita fontes.
5. Sem chaves do Langfuse ou do LLM: a demo roda do mesmo jeito.

## Tasks

1. **Domínio** (`domain/modelos.py`, `guardrail.py`, `intencao.py`, `formatacao.py`, `validacao.py`, `resposta.py`, `rascunho.py`), com testes de cada regra do spec. TDD.
2. **Portas e grafo** (`application/portas.py`, `application/grafo.py`): teste de ponta a ponta com fakes cobrindo o fluxo feliz, o bloqueio, fora de escopo, o retry e a abstenção, além de chamadas paralelas.
3. **Adaptadores** (`adapters/rag_subprocesso.py`, `salarios_rais.py`, `llm.py`, `rastreio.py`): testes com executor de subprocesso falso e rastreador nulo.
4. **Demo e rastreio real** (`demo.py`): rodar a pergunta da demo com RAG e LLM reais e Langfuse ligado. Buscar o trace pelo CLI ou pela API, auditar contra as boas práticas (`langfuse.com/docs/observability/best-practices`) e corrigir.
5. **Docs**: `docs/multiagentes.md` (sem Comunicação, como rodar, Langfuse), README e `.env.example`; no `artemishub_docs`, o ADR-011 e a página de arquitetura. Fechar a #32 como "não será feito", com o motivo.
