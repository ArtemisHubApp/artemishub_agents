"""Memória da conversa em processo: some quando o chat termina. O adaptador Postgres vem com o backend."""

from __future__ import annotations

from src.agentes.domain.modelos import Lembranca


class MemoriaEmProcesso:
    def __init__(self) -> None:
        self._sessoes: dict[str, Lembranca] = {}

    def recuperar(self, sessao: str) -> Lembranca | None:
        return self._sessoes.get(sessao)

    def lembrar(self, sessao: str, lembranca: Lembranca) -> None:
        self._sessoes[sessao] = lembranca

    def esquecer(self, sessao: str) -> None:
        self._sessoes.pop(sessao, None)
