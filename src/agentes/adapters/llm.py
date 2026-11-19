"""Redatores da Análise: LLM (Gemini pelo endpoint compatível com OpenAI) ou o rascunho padrão, sem LLM."""

from __future__ import annotations

import logging
import os
from typing import Any

import openai
from langchain_core.runnables.config import patch_config

from src.agentes.domain.modelos import PedidoDeRascunho
from src.agentes.domain.rascunho import montar_mensagens, rascunho_padrao

NOME_GERACAO = "redigir-rascunho"
log = logging.getLogger(__name__)


class RedatorPadrao:
    def redigir(self, pedido: PedidoDeRascunho, config: Any = None) -> str:
        return rascunho_padrao(pedido)


class RedatorLLM:
    """Uma chamada ao modelo por rascunho. Se o provedor falhar, cai no rascunho padrão (a demo não para)."""

    def __init__(self, modelo: Any) -> None:
        self._modelo = modelo

    def redigir(self, pedido: PedidoDeRascunho, config: Any = None) -> str:
        try:
            resposta = self._modelo.invoke(montar_mensagens(pedido), config=patch_config(config, run_name=NOME_GERACAO))
        except openai.APIError as erro:
            log.warning("LLM indisponível (%s); usando o rascunho padrão.", type(erro).__name__)
            return rascunho_padrao(pedido)
        return resposta.text.strip()


def redator_de_ambiente() -> RedatorLLM | RedatorPadrao:
    """`LLM_API_KEY`, `LLM_MODEL` e `LLM_BASE_URL` (os mesmos nomes do artemishub_rag); sem chave, o padrão."""
    chave, modelo = os.getenv("LLM_API_KEY"), os.getenv("LLM_MODEL")
    if not chave or not modelo:
        return RedatorPadrao()
    from langchain_openai import ChatOpenAI  # só importa quando o LLM vai ser usado

    return RedatorLLM(ChatOpenAI(model=modelo, api_key=chave, base_url=os.getenv("LLM_BASE_URL"),
                                 temperature=0, timeout=60, max_retries=1))
