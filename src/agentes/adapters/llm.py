"""Redatores da Análise: LLM (Gemini pelo endpoint compatível com OpenAI) ou o rascunho padrão, sem LLM.

O texto do prompt mora só no Langfuse (repo público): o `RedatorLLM` busca o prompt chat pelo label e liga a
versão usada à generation do trace. Sem Langfuse ou sem o prompt, a Análise usa o rascunho padrão.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Protocol

import openai
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables.config import patch_config

from src.agentes.domain.modelos import PedidoDeRascunho
from src.agentes.domain.rascunho import rascunho_padrao, variaveis_do_prompt

NOME_GERACAO = "redigir-rascunho"
NOME_PROMPT = "artemis/analise-rascunho"
log = logging.getLogger(__name__)


class FontePrompt(Protocol):
    def obter(self) -> Any: ...


class PromptLangfuse:
    """Prompt chat do Langfuse pelo label (`LANGFUSE_PROMPT_LABEL`, padrão `production`); o SDK faz cache."""

    def __init__(self, cliente: Any, nome: str = NOME_PROMPT, label: str | None = None) -> None:
        self._cliente, self._nome = cliente, nome
        self._label = label or os.getenv("LANGFUSE_PROMPT_LABEL", "production")

    def obter(self) -> Any:
        return self._cliente.get_prompt(self._nome, label=self._label, type="chat")


class RedatorPadrao:
    def redigir(self, pedido: PedidoDeRascunho, config: Any = None) -> str:
        return rascunho_padrao(pedido)


class RedatorLLM:
    """Uma chamada ao modelo por rascunho. Se o prompt ou o provedor falharem, cai no rascunho padrão."""

    def __init__(self, modelo: Any, prompts: FontePrompt) -> None:
        self._modelo, self._prompts = modelo, prompts

    def redigir(self, pedido: PedidoDeRascunho, config: Any = None) -> str:
        try:
            prompt = self._prompts.obter()
        except Exception as erro:  # qualquer falha do Langfuse: sem prompt, sem LLM (nunca uma cópia no repo)
            log.warning("Prompt %s indisponível (%s); usando o rascunho padrão.", NOME_PROMPT, type(erro).__name__)
            return rascunho_padrao(pedido)
        # metadata langfuse_prompt liga a versão do prompt à generation (docs: link prompts to traces)
        cadeia = prompt_template(prompt) | self._modelo.with_config(run_name=NOME_GERACAO)
        try:
            resposta = cadeia.invoke(variaveis_do_prompt(pedido), config=patch_config(config))
        except openai.APIError as erro:
            log.warning("LLM indisponível (%s); usando o rascunho padrão.", type(erro).__name__)
            return rascunho_padrao(pedido)
        return resposta.text.strip()


def prompt_template(prompt: Any) -> ChatPromptTemplate:
    return ChatPromptTemplate(prompt.get_langchain_prompt(), metadata={"langfuse_prompt": prompt})


def redator_de_ambiente() -> RedatorLLM | RedatorPadrao:
    """LLM só com `LLM_API_KEY`/`LLM_MODEL` e com o Langfuse configurado (de onde vem o prompt)."""
    chave, modelo = os.getenv("LLM_API_KEY"), os.getenv("LLM_MODEL")
    langfuse = os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    if not chave or not modelo or not langfuse:
        return RedatorPadrao()
    from langchain_openai import ChatOpenAI  # só importa quando o LLM vai ser usado
    from langfuse import get_client

    llm = ChatOpenAI(model=modelo, api_key=chave, base_url=os.getenv("LLM_BASE_URL"), temperature=0, timeout=60,
                     max_retries=1)
    return RedatorLLM(llm, PromptLangfuse(get_client()))
