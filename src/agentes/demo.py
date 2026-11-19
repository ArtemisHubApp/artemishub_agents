"""Executor da demonstração: monta os agentes com os adaptadores reais e responde uma pergunta.

Uso:
    uv run python -m src.agentes.demo "Quanto ganha uma analista de sistemas no DF, qual a diferença para homens e
    quais são meus direitos?"

Lê o `.env` deste repo e, como reserva, o do `artemishub_rag` (`ARTEMIS_RAG_DIR`), sem sobrescrever variáveis.
Com as chaves do Langfuse, cada pergunta vira um trace `responder-pergunta`.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from pathlib import Path

from dotenv import load_dotenv

from src.agentes.adapters.rag_subprocesso import RAIZ_AGENTS, BuscadorRagSubprocesso
from src.agentes.adapters.rastreio import AMBIENTES, configurar_ambiente, criar_rastreador, rastrear_pergunta
from src.agentes.adapters.salarios_rais import ConsultaRais
from src.agentes.application.grafo import Estado, construir_grafo
from src.agentes.application.portas import MemoriaDaConversa

PERGUNTA_DEMO = ("Quanto ganha uma analista de sistemas no DF, qual a diferença para homens e quais são meus "
                 "direitos?")


def carregar_ambiente() -> None:
    load_dotenv(RAIZ_AGENTS / ".env")
    rag_dir = Path(os.getenv("ARTEMIS_RAG_DIR", RAIZ_AGENTS.parent / "artemishub_rag"))
    load_dotenv(rag_dir / ".env")  # não sobrescreve o que já veio do agents ou do shell


Responder = Callable[[str], tuple[Estado, str | None]]


def montar(sessao: str | None = None, interface: str = "demo",
           memoria: MemoriaDaConversa | None = None) -> Responder:
    """Monta os agentes uma vez e devolve a função que responde cada pergunta (estado final e link do trace)."""
    from src.agentes.adapters.llm import RedatorLLM, redator_de_ambiente

    rastreador = criar_rastreador()
    redator = redator_de_ambiente()
    buscador = BuscadorRagSubprocesso.de_ambiente()
    grafo = construir_grafo(buscador, ConsultaRais(), redator, rastreador, memoria=memoria)
    contexto = {
        "interface": interface,
        "redator": type(redator).__name__,
        "modelo": os.getenv("LLM_MODEL", "") if isinstance(redator, RedatorLLM) else "rascunho-padrao",
        "rag": "subprocesso-parcial" if buscador.parcial else "subprocesso",
        "prompt_label": os.getenv("LANGFUSE_PROMPT_LABEL", "production"),
    }

    def responder(pergunta: str) -> tuple[Estado, str | None]:
        return rastrear_pergunta(rastreador, grafo, pergunta, contexto, sessao=sessao)

    return responder


def executar(pergunta: str) -> tuple[Estado, str | None]:
    """Responde a pergunta e devolve o estado final e o link do trace (ou `None` sem Langfuse)."""
    return montar()(pergunta)


def main() -> None:
    parser = argparse.ArgumentParser(description="Demonstração do sistema multiagente do Artemis")
    parser.add_argument("pergunta", nargs="?", default=PERGUNTA_DEMO)
    parser.add_argument("--ambiente", choices=AMBIENTES, help="environment no Langfuse (padrão: o do .env)")
    args = parser.parse_args()
    carregar_ambiente()
    configurar_ambiente(args.ambiente)
    estado, link = executar(args.pergunta)
    print("=== PASSO A PASSO ===")
    for passo in estado["passos"]:
        print(f"- {passo}")
    print("\n=== RESPOSTA ===")
    print(estado["resposta_final"])
    if link:
        print(f"\nTrace no Langfuse: {link}")


if __name__ == "__main__":
    main()
