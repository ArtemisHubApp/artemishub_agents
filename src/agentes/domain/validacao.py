"""Agente de Validação: confere citações, números, avisos e o sentido da diferença. Determinístico, sem LLM."""

from __future__ import annotations

import re

from src.agentes.domain.formatacao import numeros_permitidos
from src.agentes.domain.modelos import DadosSalariais, Evidencia, Validacao

CITACAO = re.compile(r"\[(FONTE\s+\d+|RAIS)\]")
_FONTE = re.compile(r"\[FONTE\s+(\d+)\]")
# "[FONTE 1, FONTE 2]", "[Fonte 1, 2]", "[fonte 01]" e "[rais]", como os LLMs escrevem na prática.
_CITACAO_SOLTA = re.compile(r"\[\s*fonte\s+(\d+(?:\s*,\s*(?:fonte\s+)?\d+)*)\s*\]", re.IGNORECASE)
_RAIS_SOLTA = re.compile(r"\[\s*rais\s*\]", re.IGNORECASE)

_NUMERO = r"(\d{1,3}(?:[.\s]\d{3})+|\d+)(?:,(\d{1,2}))?"
# "R$ 7.000,00", "R$ 7 mil", "7.000 reais", "7 mil reais"
_REAIS = re.compile(rf"R\$\s?{_NUMERO}(\s+mil\b)?|\b{_NUMERO}(\s+mil)?\s+reais\b", re.IGNORECASE)
# "17,3%", "17.3%", "25 por cento"
_PERCENTUAL = re.compile(r"(\d+(?:[.,]\d+)?)\s?(?:%|por\s+cento\b)", re.IGNORECASE)
# Título markdown ou linha curta de abertura ("Resumo:") não precisam de citação.
_TITULO = re.compile(r"^\s*(#{1,6}\s.*|[^\[\]]{1,60}:\s*)$")
# Diferença no sentido contrário ao dos dados (mulheres ganham menos).
_SENTIDO_INVERTIDO = re.compile(
    r"mulheres[^.]{0,60}\b(ganham\s+mais|recebem\s+mais|acima\s+dos?\s+homens|mais\s+(que|do\s+que)\s+(os\s+)?homens)"
    r"|homens[^.]{0,40}\b(ganham|recebem)\s+[^.]{0,20}\bmenos\b",
    re.IGNORECASE,
)


def normalizar_citacoes(texto: str) -> str:
    """Uma fonte por colchete, em maiúsculas e sem zero à esquerda: `[FONTE 1] [FONTE 2]`, `[RAIS]`."""
    def separar(achado: re.Match[str]) -> str:
        return " ".join(f"[FONTE {int(n)}]" for n in re.findall(r"\d+", achado.group(1)))

    return _RAIS_SOLTA.sub("[RAIS]", _CITACAO_SOLTA.sub(separar, texto))


def _valor(inteiro: str, centavos: str | None, mil: str | None) -> float:
    numero = float(f"{re.sub(r'[.\s]', '', inteiro)}.{centavos or '0'}")
    return numero * 1000 if mil else numero


def _valores_em_reais(texto: str) -> list[tuple[str, float]]:
    valores = []
    for m in _REAIS.finditer(texto):
        inteiro, centavos, mil = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(4), m.group(5),
                                                                                           m.group(6))
        valores.append((m.group(0).strip(), _valor(inteiro, centavos, mil)))
    return valores


def _percentuais(texto: str) -> list[tuple[str, float]]:
    return [(m.group(0), round(float(m.group(1).replace(",", ".")), 1)) for m in _PERCENTUAL.finditer(texto)]


def _linhas(texto: str) -> list[str]:
    return [linha for linha in texto.strip().splitlines() if linha.strip() and not _TITULO.match(linha)]


def validar(rascunho: str, evidencias: list[Evidencia], dados: DadosSalariais | None) -> Validacao:
    """Aprova ou reprova com o motivo exato, para a Análise corrigir na nova tentativa.

    Espera o texto já normalizado por `normalizar_citacoes`.
    """
    if not rascunho.strip():
        return Validacao(False, "O rascunho está vazio.")

    ids = {int(e.id.split()[-1]) for e in evidencias}
    inexistentes = sorted({int(n) for n in _FONTE.findall(rascunho)} - ids)
    if inexistentes:
        citadas = ", ".join(f"FONTE {n}" for n in inexistentes)
        return Validacao(False, f"Cita {citadas}, que não está entre as evidências recuperadas.")

    for numero, linha in enumerate(_linhas(rascunho), start=1):
        if not CITACAO.search(linha):
            return Validacao(False, f"O parágrafo {numero} não tem citação ([FONTE N] ou [RAIS]) no fim.")

    if "[RAIS]" in rascunho and not dados:
        return Validacao(False, "Cita [RAIS], mas a consulta salarial não trouxe dados.")

    valores, percentuais = numeros_permitidos(dados)
    for evidencia in evidencias:  # números que estão no próprio trecho citado também valem
        valores |= {v for _, v in _valores_em_reais(evidencia.texto)}
        percentuais |= {v for _, v in _percentuais(evidencia.texto)}
    for texto, valor in _valores_em_reais(rascunho):
        if round(valor, 2) not in valores:
            return Validacao(False, f"O valor {texto} não veio da consulta salarial nem das evidências; "
                                    "use os valores exatamente como estão nos dados.")
    for texto, valor in _percentuais(rascunho):
        if valor not in percentuais:
            return Validacao(False, f"O percentual {texto} não veio da consulta salarial nem das evidências.")

    diferenca = dados.get("diferenca_bruta_mediana_pct") if dados else None
    if diferenca is not None:
        if "bruta" not in rascunho.lower():
            return Validacao(False, "Falta avisar que a diferença entre mulheres e homens é bruta (sem controles).")
        if diferenca > 0 and _SENTIDO_INVERTIDO.search(rascunho):
            return Validacao(False, "O sentido da diferença está invertido: nos dados, a mediana das mulheres é "
                                    "menor que a dos homens.")
    return Validacao(True)
