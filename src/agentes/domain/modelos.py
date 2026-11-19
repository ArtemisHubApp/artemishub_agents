"""Tipos do domínio dos agentes: o que circula entre os nós, sem depender de framework."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DadosSalariais = dict[str, Any]
"""Saída de `src.salarios.consultar`: números por sexo, diferença bruta, fonte e avisos."""


@dataclass(frozen=True)
class Evidencia:
    """Trecho recuperado do RAG. `id` é o rótulo citável (`FONTE 1`, `FONTE 2`...)."""

    id: str
    titulo: str
    url: str
    pagina: str | None
    artigo: str | None
    texto: str


@dataclass(frozen=True)
class Intencao:
    salario: bool
    direitos: bool

    @property
    def fora_de_escopo(self) -> bool:
        return not (self.salario or self.direitos)


@dataclass(frozen=True)
class Parametros:
    termo_ocupacao: str | None
    cbo_familia: str | None
    cbo_familia_nome: str | None
    uf: str
    salario: float | None


@dataclass(frozen=True)
class Validacao:
    aprovado: bool
    motivo: str | None = None


@dataclass(frozen=True)
class PedidoDeRascunho:
    """Tudo o que a Análise recebe para escrever o rascunho: só campos tipados, nunca texto livre de outro agente."""

    pergunta: str
    intencao: Intencao
    parametros: Parametros
    dados_salariais: DadosSalariais | None
    evidencias: list[Evidencia]
    motivo_reprovacao: str | None = None
