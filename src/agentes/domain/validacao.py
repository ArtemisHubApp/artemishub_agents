"""Agente de Validação: confere citações, números e avisos do rascunho. Determinístico, sem LLM."""

from __future__ import annotations

import re

from src.agentes.domain.formatacao import numeros_permitidos
from src.agentes.domain.modelos import DadosSalariais, Evidencia, Validacao

CITACAO = re.compile(r"\[(FONTE\s+\d+|RAIS)\]")
_FONTE = re.compile(r"\[FONTE\s+(\d+)\]")
_REAIS = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?")
_PERCENTUAL = re.compile(r"(\d+(?:,\d+)?)\s?%")


def _valores_em_reais(texto: str) -> list[tuple[str, float]]:
    return [(m.group(0), float(f"{m.group(1).replace('.', '')}.{m.group(2) or '0'}")) for m in _REAIS.finditer(texto)]


def _percentuais(texto: str) -> list[tuple[str, float]]:
    return [(m.group(0), round(float(m.group(1).replace(",", ".")), 1)) for m in _PERCENTUAL.finditer(texto)]


def _paragrafos(texto: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", texto.strip()) if p.strip()]


def validar(rascunho: str, evidencias: list[Evidencia], dados: DadosSalariais | None) -> Validacao:
    """Aprova ou reprova com o motivo exato, para a Análise corrigir na nova tentativa."""
    if not rascunho.strip():
        return Validacao(False, "O rascunho está vazio.")

    ids = {int(e.id.split()[-1]) for e in evidencias}
    inexistentes = sorted({int(n) for n in _FONTE.findall(rascunho)} - ids)
    if inexistentes:
        citadas = ", ".join(f"FONTE {n}" for n in inexistentes)
        return Validacao(False, f"Cita {citadas}, que não está entre as evidências recuperadas.")

    for numero, paragrafo in enumerate(_paragrafos(rascunho), start=1):
        if not CITACAO.search(paragrafo):
            return Validacao(False, f"O parágrafo {numero} não tem citação ([FONTE N] ou [RAIS]).")

    if "[RAIS]" in rascunho and not dados:
        return Validacao(False, "Cita [RAIS], mas a consulta salarial não trouxe dados.")

    valores, percentuais = numeros_permitidos(dados)
    for evidencia in evidencias:  # números que estão no próprio trecho citado também valem
        valores |= {v for _, v in _valores_em_reais(evidencia.texto)}
        percentuais |= {v for _, v in _percentuais(evidencia.texto)}
    for texto, valor in _valores_em_reais(rascunho):
        if round(valor, 2) not in valores:
            return Validacao(False, f"O valor {texto} não veio da consulta salarial nem das evidências.")
    for texto, valor in _percentuais(rascunho):
        if valor not in percentuais:
            return Validacao(False, f"O percentual {texto} não veio da consulta salarial nem das evidências.")

    if dados and dados.get("diferenca_bruta_mediana_pct") is not None and "bruta" not in rascunho.lower():
        return Validacao(False, "Falta avisar que a diferença entre mulheres e homens é bruta (sem controles).")
    return Validacao(True)
