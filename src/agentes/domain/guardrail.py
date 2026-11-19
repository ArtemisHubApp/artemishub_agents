"""Guardrail de entrada do Orquestrador: barra pergunta vazia, longa demais ou com tentativa de injeção."""

from __future__ import annotations

import re

LIMITE_CARACTERES = 1000

MSG_VAZIA = "Escreva sua pergunta sobre salário ou direitos no trabalho para eu poder ajudar."
MSG_LONGA = f"Sua pergunta passou de {LIMITE_CARACTERES} caracteres. Pode resumir em poucas frases?"
MSG_INJECAO = (
    "Não posso seguir instruções que mudam as minhas regras. "
    "Posso ajudar com dúvidas sobre salário em carreiras STEM e sobre seus direitos no trabalho."
)

# Padrões de quem tenta trocar as regras do sistema em vez de perguntar algo.
_INJECAO = re.compile(
    r"ignor[ea]\w*\s+(as\s+|todas\s+as\s+|suas\s+|os\s+)?(instru|regras|orienta)"
    r"|esque[çc]\w*\s+(as\s+|todas\s+as\s+|suas\s+)?(instru|regras)"
    r"|\b(system|developer)\s+prompt"
    r"|voc[êe]\s+agora\s+[ée]"
    r"|a\s+partir\s+de\s+agora\s+voc[êe]"
    r"|ignore\s+(all\s+)?(previous|prior)\s+instructions"
    r"|jailbreak",
    re.IGNORECASE,
)


def verificar_entrada(pergunta: str) -> str | None:
    """Mensagem de bloqueio para a usuária, ou `None` se a pergunta pode seguir."""
    texto = pergunta.strip()
    if not texto:
        return MSG_VAZIA
    if len(texto) > LIMITE_CARACTERES:
        return MSG_LONGA
    if _INJECAO.search(texto):
        return MSG_INJECAO
    return None
