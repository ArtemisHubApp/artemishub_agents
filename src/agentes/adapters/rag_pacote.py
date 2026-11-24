"""Pesquisa no RAG pelo pacote `artemis_rag` (API pública `buscar`), no mesmo processo dos agentes."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.agentes.application.portas import FonteIndisponivel
from src.agentes.domain.modelos import Evidencia

RAIZ_AGENTS = Path(__file__).resolve().parents[3]


def diretorio_do_rag() -> Path:
    """Checkout do `artemishub_rag`: `ARTEMIS_RAG_DIR` ou, por padrão, a pasta ao lado deste repo."""
    return Path(os.getenv("ARTEMIS_RAG_DIR") or RAIZ_AGENTS.parent / "artemishub_rag")


class BuscadorArtemisRag:
    def __init__(self, indice: Path, parcial: bool = False, buscar: Callable[..., list[Any]] | None = None) -> None:
        self.indice, self.parcial, self._buscar = Path(indice), parcial, buscar

    @classmethod
    def de_ambiente(cls) -> BuscadorArtemisRag:
        """`ARTEMIS_RAG_INDEX_DIR` (padrão: o `.chroma` do checkout do rag) e `ARTEMIS_RAG_PARCIAL=1`."""
        indice = os.getenv("ARTEMIS_RAG_INDEX_DIR") or diretorio_do_rag() / ".chroma"
        return cls(Path(indice), parcial=os.getenv("ARTEMIS_RAG_PARCIAL") == "1")

    def buscar(self, tema: str, top_k: int) -> list[Evidencia]:
        try:
            achados = self._funcao_de_busca()(tema, top_k=top_k, indice=self.indice, parcial=self.parcial)
        except (ValueError, OSError, RuntimeError) as erro:  # sem índice, modelo diferente do índice ou sem rede
            raise FonteIndisponivel(f"o RAG falhou: {erro}") from erro
        return [Evidencia(a.id, a.titulo, a.url, a.pagina, a.artigo, a.texto) for a in achados]

    def _funcao_de_busca(self) -> Callable[..., list[Any]]:
        if self._buscar is None:
            from artemis_rag import buscar  # importa só na primeira busca: carrega PyTorch e ChromaDB

            self._buscar = buscar
        return self._buscar
