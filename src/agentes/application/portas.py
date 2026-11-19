"""Portas: o que o grafo precisa do mundo de fora. Os adaptadores implementam; os testes usam dublês."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any, Protocol

from src.agentes.domain.modelos import DadosSalariais, Evidencia, Lembranca, PedidoDeRascunho


class FonteIndisponivel(RuntimeError):
    """O RAG não respondeu (sem índice, subprocesso falhou ou saída inválida)."""


class BuscadorDeDireitos(Protocol):
    def buscar(self, tema: str, top_k: int) -> list[Evidencia]: ...


class ConsultaSalarial(Protocol):
    def buscar_ocupacao(self, termo: str) -> list[dict[str, str]]: ...

    def consultar(self, cbo_familia: str, uf: str, salario: float | None) -> DadosSalariais: ...


class Redator(Protocol):
    """Escreve o rascunho da Análise. `config` é o RunnableConfig do LangGraph, para o rastreio aninhar a chamada."""

    def redigir(self, pedido: PedidoDeRascunho, config: Any = None) -> str: ...


class MemoriaDaConversa(Protocol):
    """Guarda a `Lembranca` de cada sessão. Hoje em memória; o adaptador Postgres vem com o backend."""

    def recuperar(self, sessao: str) -> Lembranca | None: ...

    def lembrar(self, sessao: str, lembranca: Lembranca) -> None: ...

    def esquecer(self, sessao: str) -> None: ...


class Etapa(Protocol):
    def registrar(self, saida: Any, metadata: dict[str, Any] | None = None) -> None: ...


class Rastreador(Protocol):
    """Abre uma observação (`guardrail`, `retriever`, `tool`, `evaluator`...) em volta de um passo do agente."""

    def etapa(self, nome: str, tipo: str, entrada: Any) -> AbstractContextManager[Etapa]: ...


class _EtapaNula:
    def registrar(self, saida: Any, metadata: dict[str, Any] | None = None) -> None:
        return None


class RastreadorNulo:
    """Rastreador que não faz nada: testes, CI e execução sem chaves do Langfuse."""

    @contextmanager
    def etapa(self, nome: str, tipo: str, entrada: Any) -> Iterator[Etapa]:
        yield _EtapaNula()
