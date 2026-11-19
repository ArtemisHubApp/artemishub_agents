"""Rastreio no Langfuse: um trace `responder-pergunta` por pergunta, com os nós do LangGraph e as etapas tipadas.

Só liga quando `LANGFUSE_PUBLIC_KEY` e `LANGFUSE_SECRET_KEY` existem; senão o rastreador nulo assume.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from src.agentes.application.grafo import Estado, responder
from src.agentes.application.portas import Etapa, RastreadorNulo

NOME_TRACE = "responder-pergunta"
TAGS = ["prototipo-multiagente"]


def langfuse_configurado() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


class _EtapaLangfuse:
    def __init__(self, observacao: Any) -> None:
        self._observacao = observacao

    def registrar(self, saida: Any, metadata: dict[str, Any] | None = None) -> None:
        self._observacao.update(output=saida, metadata=metadata)


class LangfuseRastreador:
    def __init__(self, cliente: Any) -> None:
        self.cliente = cliente

    @contextmanager
    def etapa(self, nome: str, tipo: str, entrada: Any) -> Iterator[Etapa]:
        with self.cliente.start_as_current_observation(name=nome, as_type=tipo, input=entrada) as observacao:
            yield _EtapaLangfuse(observacao)


def _metadata_do_resultado(estado: Estado) -> dict[str, Any]:
    validacao = estado.get("validacao")
    return {
        "aprovado": bool(validacao and validacao.aprovado),
        "motivo_reprovacao": validacao.motivo if validacao and not validacao.aprovado else None,
        "tentativas": estado.get("tentativas", 0),
        "bloqueada": bool(estado.get("bloqueio")),
        "evidencias": len(estado.get("evidencias", [])),
        "falha_pesquisa": estado.get("falha_pesquisa"),
    }


def rastrear_pergunta(rastreador: LangfuseRastreador | RastreadorNulo, grafo: Any, pergunta: str,
                      redator: str) -> tuple[Estado, str | None]:
    """Roda o grafo dentro de um trace `responder-pergunta`: entrada é a pergunta, saída é a resposta final."""
    if not isinstance(rastreador, LangfuseRastreador):
        return responder(grafo, pergunta), None
    from langfuse import propagate_attributes
    from langfuse.langchain import CallbackHandler

    cliente = rastreador.cliente
    with cliente.start_as_current_observation(name=NOME_TRACE, as_type="agent", input=pergunta) as raiz:
        with propagate_attributes(trace_name=NOME_TRACE, tags=TAGS, metadata={"redator": redator}):
            estado = responder(grafo, pergunta, {"callbacks": [CallbackHandler()], "run_name": "fluxo-multiagente"})
        raiz.update(output=estado["resposta_final"], metadata=_metadata_do_resultado(estado))
        link = cliente.get_trace_url(trace_id=raiz.trace_id)
    cliente.flush()
    return estado, link


def criar_rastreador() -> LangfuseRastreador | RastreadorNulo:
    if not langfuse_configurado():
        return RastreadorNulo()
    os.environ.setdefault("LANGFUSE_TRACING_ENVIRONMENT", "development")
    from langfuse import get_client  # importa depois do .env carregado, como pede a documentação

    return LangfuseRastreador(get_client())
