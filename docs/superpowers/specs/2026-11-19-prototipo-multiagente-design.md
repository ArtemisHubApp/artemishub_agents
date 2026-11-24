# Spec: primeiro protótipo multiagente (entrega de 20/11)

**Issues:** #27 (executor e integração), #8 (scaffold), #9 (Orquestrador e guardrails), #30 (Pesquisa), #11 (Análise salarial), #31 (Validação). A #32 (Comunicação) sai do escopo (decisão abaixo).
**Base:** `docs/multiagentes.md` (desenho fechado) e ADR-002 (LangGraph).

## Decisões (19/11)

1. **Sem agente de Comunicação.** Sugestão do professor: o Orquestrador formata a resposta final, sem uma chamada a mais ao LLM. A formatação é um template determinístico: texto aprovado + "Limites dos dados" + "Fontes". Números e citações não podem mudar depois da Validação, e o template garante isso por construção.
2. **Uma chamada ao LLM por pergunta** (duas se a Validação reprovar): só a síntese da Análise usa LLM. Orquestrador (intenção e guardrail), Pesquisa (busca no RAG), consulta salarial e Validação são código determinístico. Sem LLM configurado, a síntese usa um redator determinístico, e a demo roda mesmo assim.
3. **LangGraph** como no ADR-002, com **Langfuse** (SDK 5) desde já, a pedido da Amanda. O trace `responder-pergunta` tem como raiz um `agent` e usa o `CallbackHandler` nos nós. As etapas são tipadas: `guardrail`, `retriever`, `tool`, `generation` e `evaluator`. Sem chaves, o rastreio é nulo.
4. **RAG por subprocesso:** a Pesquisa depende de uma porta `BuscadorDeDireitos`. O adaptador roda o `Retriever` do `artemishub_rag` no ambiente dele (`uv run --project <rag>`) e lê JSON. Os dois repos usam o pacote `src`, e o RAG ainda não é importável (rag#23); quando for, troca só o adaptador.
5. **Camadas** (`codigo-limpo.md`): `src/agentes/domain` (regras puras), `application` (portas e grafo), `adapters` (RAG, RAIS, LLM, CLI). A montagem acontece no `demo.py`.

## Fluxo

```
pergunta → Orquestrador (guardrail + intenção) ─┬─ Pesquisa (RAG) ─┐
                                                └─ Dados (RAIS)  ──┴→ Análise (síntese) → Validação
Validação aprovada → Orquestrador formata a resposta
Validação reprovada → Análise refaz com o motivo (1 vez) → Validação → resposta ou abstenção
Guardrail bloqueia → Orquestrador responde direto, sem acionar ninguém
```

## Regras

- **Guardrail:** pergunta vazia, acima de 1.000 caracteres ou com padrão de injeção ("ignore as instruções", "system prompt", "você agora é"...) é bloqueada com uma mensagem fixa. Pergunta fora de escopo (sem tema de salário nem de direitos) recebe a mensagem de escopo.
- **Intenção:** `salario` se a pergunta fala de ganho, salário, remuneração ou valor em R$; `direitos` se fala de direitos, lei, igualdade, discriminação ou diferença para homens. Parâmetros: UF (sigla ou nome do estado), salário (`R$ 7.500`, `7500`, `7.500,00`) e ocupação (`buscar_ocupacao` da ferramenta salarial). Sem UF, usa `BR`.
- **Pesquisa:** top 5. Pergunta que mistura salário e direitos busca pelo tema fixo "igualdade salarial entre mulheres e homens na mesma função"; pergunta só sobre direitos busca pela própria pergunta. Cada evidência ganha o id `FONTE N`. Texto recuperado é dado, nunca instrução (vai delimitado no prompt).
- **Síntese:** recebe só campos tipados (números, avisos e evidências). Cada parágrafo cita `[FONTE N]` ou `[RAIS]`. Os números vêm prontos e formatados em reais.
- **Validação** (determinística) reprova com motivo exato quando:
  - cita `[FONTE N]` inexistente, ou um parágrafo não tem citação;
  - aparece um valor em R$ ou percentual que não está nos números permitidos;
  - há diferença salarial e falta o aviso de diferença **bruta**;
  - o texto está vazio.
- **Resposta final:** texto aprovado; seção "Limites dos dados" com os avisos da ferramenta; seção "Fontes" com `FONTE N: título, URL, página` e `RAIS: fonte e ano`. Abstenção: explica o que não deu para confirmar e lista o que foi encontrado.
- **Demo:** `uv run python -m src.agentes.demo "<pergunta>"` mostra o passo a passo (cada nó, entrada resumida e saída) e a resposta. Sem dados pessoais no log, além da própria pergunta.

## Fora de escopo hoje

Avaliadores e datasets no Langfuse, API para o backend (#36), memória entre conversas, agentes de perfil, oportunidades e negociação, e o pacote importável do RAG (rag#23).

## Critérios de sucesso

- A pergunta da demo ("Quanto ganha uma analista de sistemas no DF, qual a diferença para homens e quais são meus direitos?") sai com números da RAIS, citações do RAG e avisos.
- Testes determinísticos, sem LLM e sem RAG reais, passam no CI e cobrem: o guardrail, a intenção, cada regra da Validação, o retry e a abstenção, e o grafo de ponta a ponta com fakes.
- `docs/multiagentes.md`, o README, a página de arquitetura e um ADR no `artemishub_docs` refletem a decisão 1.
