"""Formatação de valores no padrão brasileiro e o conjunto de números que um texto pode citar."""

from __future__ import annotations

from src.agentes.domain.modelos import DadosSalariais

_CAMPOS_EM_REAIS = ("p25", "p50", "p75", "p50_tempo_integral")


def brl(valor: float) -> str:
    """`8462.79` → `R$ 8.462,79`."""
    inteiro, centavos = f"{valor:,.2f}".split(".")
    return f"R$ {inteiro.replace(',', '.')},{centavos}"


def pct(valor: float) -> str:
    """`17.3` → `17,3%` (sempre positivo; o sentido vai no texto: acima/abaixo)."""
    return f"{abs(valor):.1f}".replace(".", ",") + "%"


def numeros_permitidos(dados: DadosSalariais | None) -> tuple[set[float], set[float]]:
    """Valores em reais e percentuais que saíram da ferramenta salarial e podem aparecer na resposta."""
    if not dados:
        return set(), set()
    valores: set[float] = set()
    percentuais: set[float] = set()
    for numeros in dados.get("por_sexo", {}).values():
        valores |= {round(float(numeros[c]), 2) for c in _CAMPOS_EM_REAIS if numeros.get(c) is not None}
    if dados.get("diferenca_bruta_mediana_pct") is not None:
        percentuais.add(round(abs(float(dados["diferenca_bruta_mediana_pct"])), 1))
    informado = dados.get("salario_informado") or {}
    if informado.get("valor") is not None:
        valores.add(round(float(informado["valor"]), 2))
    percentuais |= {round(abs(float(v)), 1) for k, v in informado.items() if k.startswith("vs_mediana_")}
    return valores, percentuais
