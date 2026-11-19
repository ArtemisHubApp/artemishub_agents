"""Resposta final, formatada pelo Orquestrador (sem agente de Comunicação e sem chamada extra ao LLM)."""

from __future__ import annotations

from src.agentes.domain.modelos import DadosSalariais, Evidencia
from src.agentes.domain.validacao import CITACAO

MSG_FORA_DE_ESCOPO = (
    "Por enquanto eu respondo sobre salário em carreiras STEM, com dados da RAIS, e sobre seus direitos no trabalho, "
    "como a igualdade salarial. Você pode perguntar, por exemplo: \"Quanto ganha uma analista de sistemas no DF e "
    "quais são meus direitos?\""
)


def _referencia(evidencia: Evidencia) -> str:
    partes = [evidencia.titulo]
    if evidencia.artigo:
        partes.append(evidencia.artigo)
    if evidencia.pagina:
        partes.append(f"página {evidencia.pagina}")
    return f"{evidencia.id}: {', '.join(partes)}. {evidencia.url}"


def _fontes(texto: str, evidencias: list[Evidencia], dados: DadosSalariais | None) -> list[str]:
    citadas = {c.replace("  ", " ") for c in CITACAO.findall(texto)}
    linhas = [f"- {_referencia(e)}" for e in evidencias if e.id in citadas]
    if "RAIS" in citadas and dados:
        linhas.append(f"- RAIS: {dados['fonte']}, {dados['ano']}.")
    return linhas


def formatar_resposta(rascunho: str, evidencias: list[Evidencia], dados: DadosSalariais | None) -> str:
    """Texto aprovado pela Validação, sem alteração, seguido dos limites dos dados e das fontes citadas."""
    secoes = [rascunho.strip()]
    if dados and dados.get("avisos") and "[RAIS]" in rascunho:
        secoes.append("**Limites dos dados**\n" + "\n".join(f"- {aviso}" for aviso in dados["avisos"]))
    fontes = _fontes(rascunho, evidencias, dados)
    if fontes:
        secoes.append("**Fontes**\n" + "\n".join(fontes))
    return "\n\n".join(secoes)


def formatar_abstencao(motivo: str, evidencias: list[Evidencia], dados: DadosSalariais | None) -> str:
    """Quando a Validação reprova duas vezes: explica o que faltou e mostra o que foi encontrado."""
    secoes = [
        "Não consegui confirmar todas as informações com segurança "
        f"(última checagem: {motivo.rstrip('.')}). Para não te passar nada errado, preferi não montar a resposta."
    ]
    encontrado = [f"- {_referencia(e)}" for e in evidencias]
    if dados and dados.get("suficiente"):
        encontrado.append(f"- RAIS: {dados['fonte']}, {dados['ano']}.")
    if encontrado:
        secoes.append("**O que encontrei para você conferir**\n" + "\n".join(encontrado))
    return "\n\n".join(secoes)
