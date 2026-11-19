"""Consulta salarial da Análise: usa a ferramenta `src.salarios` e os agregados versionados em `data/agregados/`."""

from __future__ import annotations

from functools import cached_property

import pandas as pd

from src import salarios
from src.agentes.domain.modelos import DadosSalariais


class ConsultaRais:
    def __init__(self, ano: int = 2025) -> None:
        self.ano = ano

    @cached_property
    def _tabela(self) -> pd.DataFrame:
        return salarios.carregar_tabela(self.ano)

    @cached_property
    def _ocupacoes(self) -> pd.DataFrame:
        return salarios.carregar_ocupacoes()

    def buscar_ocupacao(self, termo: str) -> list[dict[str, str]]:
        return salarios.buscar_ocupacao(termo, self._ocupacoes)

    def consultar(self, cbo_familia: str, uf: str, salario: float | None) -> DadosSalariais:
        return salarios.consultar(cbo_familia, uf, salario=salario, tabela=self._tabela, ano=self.ano)
