"""Conversa com os agentes pelo terminal.

Uso:
    uv run python -m src.agentes.chat

Os agentes são montados uma vez só. Cada pergunta é respondida sozinha (sem memória entre perguntas, como no
protótipo), vira um trace no Langfuse, e a conversa inteira é uma sessão.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from src.agentes.demo import Responder, carregar_ambiente, montar

BOAS_VINDAS = (
    "Artemis: pergunte sobre salário em carreiras STEM ou sobre seus direitos no trabalho.\n"
    "Cada pergunta é respondida sozinha (ainda não há memória da conversa). Digite /ajuda para ver os comandos."
)
AJUDA = "Comandos: /passos liga ou desliga o passo a passo dos agentes; /ajuda mostra esta ajuda; /sair encerra."
DESPEDIDA = "Até logo!"
PROMPT = "\nvocê> "


def conversar(responder: Responder, ler: Callable[[str], str] = input,
              escrever: Callable[..., None] = print) -> int:
    """Laço da conversa. Devolve 0 ao sair (por /sair, Ctrl+D ou Ctrl+C)."""
    mostrar_passos = False
    escrever(BOAS_VINDAS)
    while True:
        try:
            entrada = ler(PROMPT).strip()
        except (EOFError, KeyboardInterrupt):
            escrever(f"\n{DESPEDIDA}")
            return 0
        if not entrada:
            continue
        if entrada.startswith("/"):
            comando = entrada.lower()
            if comando in ("/sair", "/exit", "/quit"):
                escrever(DESPEDIDA)
                return 0
            if comando == "/passos":
                mostrar_passos = not mostrar_passos
                escrever(f"Passo a passo {'ligado' if mostrar_passos else 'desligado'}.")
            elif comando == "/ajuda":
                escrever(AJUDA)
            else:
                escrever(f"Comando desconhecido: {entrada}. {AJUDA}")
            continue
        try:
            estado, link = responder(entrada)
        except Exception as erro:  # a conversa continua; o erro aparece para quem está testando
            escrever(f"artemis> Não consegui responder agora ({type(erro).__name__}: {erro}).")
            continue
        if mostrar_passos:
            escrever("\n".join(f"  · {passo}" for passo in estado.get("passos", [])))
        escrever(f"\nartemis> {estado['resposta_final']}")
        if link:
            escrever(f"\n(trace: {link})")


def main() -> None:
    carregar_ambiente()
    sessao = f"chat-{uuid.uuid4().hex[:12]}"
    print("Montando os agentes...")
    raise SystemExit(conversar(montar(sessao=sessao)))


if __name__ == "__main__":
    main()
