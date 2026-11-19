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

# Padrões de quem tenta trocar as regras do sistema em vez de perguntar algo. O comando precisa ser dirigido
# ao sistema (imperativo + "instruções", ou "regras anteriores/do sistema"): "empresas podem ignorar as regras
# da lei?" é pergunta de direitos e não pode ser bloqueada.
_ALVO = (
    r"(todas\s+)?(as\s+|suas\s+|tuas\s+|os\s+|seus\s+)?"
    r"(instru[çc]|orienta[çc]|comandos|regras\s+(anteriores|acima|do\s+sistema))"
)
_INJECAO = re.compile(
    rf"\b(ignore|ignora|desconsidere|desconsidera|esque[çc]a|esquece|descarte)\s+{_ALVO}"
    r"|\b(system|developer)\s+prompt|\bprompt\s+(do|de)\s+sistema"
    r"|voc[êe]\s+agora\s+[ée]|a\s+partir\s+de\s+agora\s+voc[êe]"
    r"|\bfinja\s+(que|ser)\b|\baja\s+como\b|\bmodo\s+desenvolvedor|\bDAN\b"
    r"|\bignore\s+(all\s+|your\s+|the\s+)?(previous\s+|prior\s+)?instructions"
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
