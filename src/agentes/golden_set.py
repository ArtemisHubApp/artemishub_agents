"""Roda o golden set dos agentes (#62) e confere cada caso campo por campo contra o gabarito.

Sem LLM (padrão): o grafo usa o rascunho padrão, então o resultado é determinístico e pode ir para o CI.
Confere ação, intenção, ocupação, UF, valores da RAIS, salário informado, fontes do RAG e se os pares
(casos que só trocam gênero ou raça) saem idênticos. Sem o índice do RAG, a ação dos casos de direitos e as
fontes ficam como "pulado", porque sem nenhum trecho de lei o agente se abstém de propósito.

    uv run python -m src.agentes.golden_set                 # desenvolvimento
    uv run python -m src.agentes.golden_set --holdout       # holdout: só nos marcos, nunca para ajustar
    uv run python -m src.agentes.golden_set --saida resultado.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.agentes.adapters.llm import RedatorPadrao
from src.agentes.adapters.memoria import MemoriaEmProcesso
from src.agentes.adapters.rag_pacote import RAIZ_AGENTS, BuscadorArtemisRag, diretorio_do_rag
from src.agentes.adapters.salarios_rais import ConsultaRais
from src.agentes.application.grafo import Estado, construir_grafo, responder
from src.agentes.application.portas import BuscadorDeDireitos, FonteIndisponivel

PASTA = RAIZ_AGENTS / "evaluation"
ARQUIVOS = {"development": PASTA / "golden_development.jsonl", "holdout": PASTA / "golden_holdout.jsonl"}
TOLERANCIA = 0.01  # reais e pontos percentuais: só arredondamento

OK, FALHA, PULADO = "ok", "falha", "pulado"


@dataclass
class Resultado:
    id: str
    categoria: str
    campos: dict[str, str] = field(default_factory=dict)  # campo -> ok | falha | pulado
    detalhes: list[str] = field(default_factory=list)  # o que veio, quando falhou

    @property
    def passou(self) -> bool:
        return FALHA not in self.campos.values()


def carregar_casos(caminho: Path) -> list[dict[str, Any]]:
    with caminho.open(encoding="utf-8") as arquivo:
        return [json.loads(linha) for linha in arquivo if linha.strip()]


def acao_do_estado(estado: Estado) -> str:
    if estado.get("bloqueio"):
        return "bloquear"
    if estado["intencao"].fora_de_escopo:
        return "fora_de_escopo"
    return "responder" if estado["validacao"].aprovado else "abster"


def observado(estado: Estado) -> dict[str, Any]:
    """O que o agente produziu, no mesmo formato do gabarito."""
    saida: dict[str, Any] = {"acao": acao_do_estado(estado)}
    intencao, parametros, dados = estado.get("intencao"), estado.get("parametros"), estado.get("dados_salariais")
    if intencao is not None:
        saida["intencao"] = {"salario": intencao.salario, "direitos": intencao.direitos}
    if parametros is not None:
        saida["cbo_familia"] = parametros.cbo_familia
        saida["salario_informado"] = parametros.salario
    if dados and dados.get("suficiente"):
        por_sexo = dados["por_sexo"]
        saida["uf_usada"] = dados["uf_usada"]
        saida["valores_rais"] = {
            "mediana_feminino": por_sexo.get("feminino", {}).get("p50"),
            "mediana_masculino": por_sexo.get("masculino", {}).get("p50"),
            "mediana_geral": por_sexo.get("todos", {}).get("p50"),
            "diferenca_bruta_pct": dados.get("diferenca_bruta_mediana_pct"),
        }
    saida["fontes"] = [evidencia.titulo for evidencia in estado.get("evidencias", [])]
    return saida


def _mesmo_numero(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is b
    return abs(float(a) - float(b)) <= TOLERANCIA


def conferir(caso: dict[str, Any], obs: dict[str, Any], com_rag: bool, titulos: dict[str, str]) -> Resultado:
    esperado = caso["esperado"]
    resultado = Resultado(caso["id"], caso["categoria"])

    def marcar(campo: str, certo: bool, veio: Any) -> None:
        resultado.campos[campo] = OK if certo else FALHA
        if not certo:
            resultado.detalhes.append(f"{campo}: veio {veio!r}")

    so_direitos = esperado.get("intencao", {}).get("direitos") and esperado["acao"] == "responder"
    if so_direitos and not com_rag and obs["acao"] == "abster":
        resultado.campos["acao"] = PULADO  # sem trecho de lei a abstenção é o comportamento certo
    else:
        marcar("acao", obs["acao"] == esperado["acao"], obs["acao"])

    if "intencao" in esperado:
        marcar("intencao", obs.get("intencao") == esperado["intencao"], obs.get("intencao"))
    if esperado.get("cbo_familia") is not None:
        marcar("cbo_familia", obs.get("cbo_familia") == esperado["cbo_familia"], obs.get("cbo_familia"))
    if esperado.get("uf_usada") is not None:
        marcar("uf_usada", obs.get("uf_usada") == esperado["uf_usada"], obs.get("uf_usada"))
    if esperado.get("valores_rais") is not None:
        veio = obs.get("valores_rais") or {}
        certo = all(_mesmo_numero(veio.get(chave), valor) for chave, valor in esperado["valores_rais"].items())
        marcar("valores_rais", certo, veio)
    elif esperado["acao"] in ("responder", "abster") and not esperado.get("intencao", {}).get("salario"):
        marcar("sem_valores_rais", obs.get("valores_rais") is None, obs.get("valores_rais"))
    if esperado.get("salario_informado") is not None:
        veio = obs.get("salario_informado")
        marcar("salario_informado", _mesmo_numero(veio, esperado["salario_informado"]), veio)

    if esperado.get("fontes"):
        if not com_rag or not titulos:
            resultado.campos["fontes"] = PULADO
        else:
            # pelo menos um dos documentos esperados entre os trechos recuperados
            esperados = {titulos.get(documento, documento) for documento in esperado["fontes"]}
            marcar("fontes", bool(esperados & set(obs["fontes"])), obs["fontes"])
    return resultado


def conferir_pares(casos: list[dict[str, Any]], observados: dict[str, dict[str, Any]]) -> list[Resultado]:
    """Os dois casos de um par têm que produzir exatamente o mesmo (tirando as fontes, que dependem do ranking)."""
    pares: dict[str, list[str]] = defaultdict(list)
    for caso in casos:
        if caso.get("par_id"):
            pares[caso["par_id"]].append(caso["id"])
    resultados = []
    for par_id, ids in sorted(pares.items()):
        resultado = Resultado(par_id, "par_identico")
        comparaveis = [{k: v for k, v in observados[i].items() if k != "fontes"} for i in ids]
        certo = len(ids) == 2 and comparaveis[0] == comparaveis[1]
        resultado.campos["identicos"] = OK if certo else FALHA
        if not certo:
            resultado.detalhes.append(f"{' x '.join(ids)}: {comparaveis}")
        resultados.append(resultado)
    return resultados


def titulos_do_rag() -> dict[str, str]:
    """document_id -> título, do `config/sources.json` do checkout do rag (o mesmo que o índice usa)."""
    caminho = diretorio_do_rag() / "config" / "sources.json"
    if not caminho.exists():
        return {}
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    fontes = dados if isinstance(dados, list) else dados.get("sources", [])
    return {fonte["id"]: fonte["title"] for fonte in fontes}


class _BuscadorQueAnota:
    """Repassa a busca e anota se o RAG respondeu alguma vez nesta rodada."""

    def __init__(self, buscador: BuscadorDeDireitos) -> None:
        self.buscador, self.funcionou = buscador, False

    def buscar(self, tema: str, top_k: int) -> list[Any]:
        evidencias = self.buscador.buscar(tema, top_k)
        self.funcionou = True
        return evidencias


def rodar(casos: Iterable[dict[str, Any]], buscador: BuscadorDeDireitos,
          consulta: Any = None, redator: Any = None) -> tuple[list[Resultado], bool]:
    """Roda cada caso numa conversa nova e devolve os resultados e se o RAG estava disponível."""
    casos = list(casos)
    anotador = _BuscadorQueAnota(buscador)
    consulta, redator = consulta or ConsultaRais(), redator or RedatorPadrao()
    observados: dict[str, dict[str, Any]] = {}
    for caso in casos:
        memoria = MemoriaEmProcesso()  # cada caso começa sem lembrança; a conversa dele usa a mesma sessão
        grafo = construir_grafo(anotador, consulta, redator, memoria=memoria)
        for pergunta in caso["conversa"]:
            estado = responder(grafo, pergunta, sessao=caso["id"])
        observados[caso["id"]] = observado(estado)
    com_rag, titulos = anotador.funcionou, titulos_do_rag()
    resultados = [conferir(caso, observados[caso["id"]], com_rag, titulos) for caso in casos]
    return resultados + conferir_pares(casos, observados), com_rag


class _BuscadorSeguro:
    """Sem índice publicado, a busca falha como `FonteIndisponivel` e o grafo segue sem fontes jurídicas."""

    def __init__(self) -> None:
        self.real = BuscadorArtemisRag.de_ambiente()

    def buscar(self, tema: str, top_k: int) -> list[Any]:
        try:
            return self.real.buscar(tema, top_k)
        except Exception as erro:  # import do artemis_rag ou modelo de embedding indisponível
            raise FonteIndisponivel(str(erro)) from erro


def relatorio(resultados: list[Resultado], com_rag: bool, escrever: Callable[[str], None] = print) -> None:
    for resultado in resultados:
        marcas = " ".join(f"{campo} {'✔' if v == OK else '✘' if v == FALHA else '–'}"
                          for campo, v in resultado.campos.items())
        escrever(f"{resultado.id:<5} {resultado.categoria:<20} {marcas}")
        for detalhe in resultado.detalhes:
            escrever(f"      ✘ {detalhe}")
    por_categoria: dict[str, Counter[bool]] = defaultdict(Counter)
    for resultado in resultados:
        por_categoria[resultado.categoria][resultado.passou] += 1
    escrever("")
    for categoria, contagem in sorted(por_categoria.items()):
        escrever(f"{categoria:<20} {contagem[True]}/{contagem[True] + contagem[False]}")
    passaram = sum(r.passou for r in resultados)
    escrever(f"\nTotal: {passaram}/{len(resultados)} passaram"
             + ("" if com_rag else " (sem índice do RAG: ação de direitos e fontes puladas)"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Golden set dos agentes (#62), sem LLM")
    parser.add_argument("--holdout", action="store_true", help="roda o holdout (só nos marcos)")
    parser.add_argument("--saida", type=Path, help="grava o resultado em JSON")
    args = parser.parse_args(argv)

    casos = carregar_casos(ARQUIVOS["holdout" if args.holdout else "development"])
    resultados, com_rag = rodar(casos, _BuscadorSeguro())
    relatorio(resultados, com_rag)
    if args.saida:
        args.saida.write_text(json.dumps([asdict(r) | {"passou": r.passou} for r in resultados],
                                         ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if all(r.passou for r in resultados) else 1


if __name__ == "__main__":
    sys.exit(main())