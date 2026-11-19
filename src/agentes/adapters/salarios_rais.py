"""Consulta salarial da Análise: usa a ferramenta `src.salarios` e os agregados versionados em `data/agregados/`."""

from __future__ import annotations

import re
from difflib import get_close_matches
from functools import cached_property

import pandas as pd

from src import salarios
from src.agentes.domain.modelos import DadosSalariais

SEMELHANCA_MINIMA = 0.8  # "cientsita" → "cientista"; abaixo disso a palavra fica como veio


class ConsultaRais:
    def __init__(self, ano: int = 2025) -> None:
        self.ano = ano

    @cached_property
    def _tabela(self) -> pd.DataFrame:
        return salarios.carregar_tabela(self.ano)

    @cached_property
    def _ocupacoes(self) -> pd.DataFrame:
        return salarios.carregar_ocupacoes()

    @cached_property
    def _vocabulario(self) -> list[str]:
        """Palavras (sem acento, 4+ letras) que aparecem nos nomes das ocupações da CBO."""
        nomes = " ".join(self._ocupacoes["cbo_nome"].map(salarios._normalizar))
        return sorted(set(re.findall(r"[a-z]{4,}", nomes)))

    def _corrigir(self, termo: str) -> str:
        """Troca cada palavra que não existe na CBO pela mais parecida que existe, se for bem parecida."""
        corrigidas = []
        for palavra in termo.split():
            if len(palavra) < 4 or palavra in self._vocabulario:
                corrigidas.append(palavra)
                continue
            parecidas = get_close_matches(palavra, self._vocabulario, n=1, cutoff=SEMELHANCA_MINIMA)
            corrigidas.append(parecidas[0] if parecidas else palavra)
        return " ".join(dict.fromkeys(corrigidas))  # sem repetir ("cientsita cientsito" → "cientista")

    def buscar_ocupacao(self, termo: str) -> list[dict[str, str]]:
        return salarios.buscar_ocupacao(self._corrigir(termo), self._ocupacoes)

    def consultar(self, cbo_familia: str, uf: str, salario: float | None) -> DadosSalariais:
        return salarios.consultar(cbo_familia, uf, salario=salario, tabela=self._tabela, ano=self.ano)
