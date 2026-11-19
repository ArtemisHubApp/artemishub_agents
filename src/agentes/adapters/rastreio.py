"""Rastreio no Langfuse: um trace `responder-pergunta` por pergunta, com os nós do LangGraph e as etapas tipadas.

Só liga quando `LANGFUSE_PUBLIC_KEY` e `LANGFUSE_SECRET_KEY` existem; senão o rastreador nulo assume.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

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


def criar_rastreador() -> LangfuseRastreador | RastreadorNulo:
    if not langfuse_configurado():
        return RastreadorNulo()
    os.environ.setdefault("LANGFUSE_TRACING_ENVIRONMENT", "development")
    from langfuse import get_client  # importa depois do .env carregado, como pede a documentação

    return LangfuseRastreador(get_client())
