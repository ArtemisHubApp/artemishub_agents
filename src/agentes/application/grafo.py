"""Grafo LangGraph do protótipo: Orquestrador → (Pesquisa ∥ Análise/dados) → Análise/síntese → Validação → resposta.

O roteamento é código, nunca decisão do LLM. Cada nó escreve só nos seus campos do estado.
"""

from __future__ import annotations

import operator
from dataclasses import asdict
from typing import Annotated, Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from src.agentes.application.portas import (
    BuscadorDeDireitos,
    ConsultaSalarial,
    FonteIndisponivel,
    MemoriaDaConversa,
    Rastreador,
    RastreadorNulo,
    Redator,
)
from src.agentes.domain.guardrail import verificar_entrada
from src.agentes.domain.intencao import extrair_salario, extrair_uf, interpretar, termo_de_ocupacao
from src.agentes.domain.modelos import (
    DadosSalariais,
    Evidencia,
    Intencao,
    Lembranca,
    Parametros,
    PedidoDeRascunho,
    Validacao,
)
from src.agentes.domain.resposta import MSG_FORA_DE_ESCOPO, formatar_abstencao, formatar_resposta
from src.agentes.domain.validacao import normalizar_citacoes, validar

TEMA_IGUALDADE = "igualdade salarial entre mulheres e homens na mesma função"
TOP_K = 5
MAX_TENTATIVAS = 2  # a primeira e mais uma, se a Validação reprovar


class Estado(TypedDict, total=False):
    pergunta: str
    sessao: str | None
    bloqueio: str | None
    intencao: Intencao
    parametros: Parametros
    evidencias: list[Evidencia]
    falha_pesquisa: str | None
    dados_salariais: DadosSalariais | None
    rascunho: str
    validacao: Validacao
    tentativas: int
    resposta_final: str
    passos: Annotated[list[str], operator.add]


def construir_grafo(
    buscador: BuscadorDeDireitos,
    consulta: ConsultaSalarial,
    redator: Redator,
    rastreador: Rastreador | None = None,
    memoria: MemoriaDaConversa | None = None,
) -> Any:
    """Monta e compila o grafo. As dependências chegam prontas (a montagem fica em `demo.py`)."""
    rastreio = rastreador or RastreadorNulo()

    def orquestrador(estado: Estado) -> dict[str, Any]:
        pergunta = estado["pergunta"]
        with rastreio.etapa("verificar-entrada", "guardrail", {"pergunta": pergunta}) as etapa:
            bloqueio = verificar_entrada(pergunta)
            etapa.registrar({"bloqueada": bloqueio is not None, "mensagem": bloqueio})
        if bloqueio:
            return {"bloqueio": bloqueio, "passos": ["orquestrador: pergunta bloqueada pelo guardrail"]}
        sessao = estado.get("sessao")
        lembranca = memoria.recuperar(sessao) if memoria and sessao else None
        intencao, uf, termo = interpretar(pergunta), extrair_uf(pergunta), termo_de_ocupacao(pergunta)
        achadas = consulta.buscar_ocupacao(termo) if termo and (intencao.salario or lembranca) else []
        herdados: list[str] = []
        # "e no DF?": sem tema próprio, mas com lugar ou ocupação, continua o assunto da pergunta anterior
        if intencao.fora_de_escopo and lembranca and (uf or achadas):
            intencao = Intencao(lembranca.salario, lembranca.direitos)
            herdados.append("intenção")
        familia, nome, ocupacao = None, None, None
        if intencao.salario and achadas:
            familia, nome, ocupacao = achadas[0]["cbo_familia"], achadas[0]["cbo_familia_nome"], achadas[0]["cbo_nome"]
        elif intencao.salario and lembranca and lembranca.cbo_familia:
            familia, nome, ocupacao = lembranca.cbo_familia, lembranca.cbo_familia_nome, lembranca.ocupacao
            herdados.append("ocupação")
        if not uf and lembranca and lembranca.uf != "BR" and not intencao.fora_de_escopo:
            uf = lembranca.uf
            herdados.append("UF")
        parametros = Parametros(termo, familia, nome, uf or "BR", extrair_salario(pergunta), ocupacao=ocupacao)
        temas = [t for t, pedido in (("salário", intencao.salario), ("direitos", intencao.direitos)) if pedido]
        passo = f"orquestrador: intenção {' + '.join(temas) or 'fora de escopo'}"
        if intencao.salario:
            familia_texto = f"família {familia}: {nome}" if familia else "família não encontrada"
            passo += f"; ocupação {ocupacao or termo} ({familia_texto}), UF {parametros.uf}"
        if herdados:
            passo += f" ({', '.join(herdados)} {'lembradas' if len(herdados) > 1 else 'lembrada'} da conversa)"
        return {"bloqueio": None, "intencao": intencao, "parametros": parametros, "tentativas": 0, "passos": [passo]}

    def rotear_entrada(estado: Estado) -> str | list[str]:
        intencao = estado.get("intencao")
        if estado.get("bloqueio") or intencao is None or intencao.fora_de_escopo:
            return "resposta"
        return [no for no, ativo in (("pesquisa", intencao.direitos), ("analise_dados", intencao.salario)) if ativo]

    def pesquisa(estado: Estado) -> dict[str, Any]:
        # Pergunta só sobre direitos: busca pela própria pergunta. Pergunta mista: pelo tema de igualdade salarial.
        tema = TEMA_IGUALDADE if estado["intencao"].salario else estado["pergunta"]
        with rastreio.etapa("buscar-direitos", "retriever", {"tema": tema, "top_k": TOP_K}) as etapa:
            try:
                evidencias = buscador.buscar(tema, TOP_K)
            except FonteIndisponivel as erro:
                etapa.registrar({"erro": str(erro)}, {"falhou": True})
                return {"evidencias": [], "falha_pesquisa": str(erro), "passos": [f"pesquisa: falhou ({erro})"]}
            etapa.registrar([asdict(e) for e in evidencias], {"quantidade": len(evidencias)})
        titulos = "; ".join(f"{e.id} {e.titulo}" for e in evidencias) or "nenhum trecho"
        return {"evidencias": evidencias, "falha_pesquisa": None, "passos": [f"pesquisa: {titulos}"]}

    def analise_dados(estado: Estado) -> dict[str, Any]:
        parametros = estado["parametros"]
        if not parametros.cbo_familia:
            return {"dados_salariais": None, "passos": ["analise_dados: ocupação não encontrada na CBO"]}
        entrada = {"cbo_familia": parametros.cbo_familia, "uf": parametros.uf, "salario": parametros.salario}
        with rastreio.etapa("consultar-rais", "tool", entrada) as etapa:
            dados = consulta.consultar(parametros.cbo_familia, parametros.uf, parametros.salario)
            etapa.registrar(dados)
        if not dados.get("suficiente"):
            return {"dados_salariais": dados, "passos": ["analise_dados: sem vínculos suficientes"]}
        mulheres = dados["por_sexo"].get("feminino", {}).get("p50")
        homens = dados["por_sexo"].get("masculino", {}).get("p50")
        return {"dados_salariais": dados,
                "passos": [f"analise_dados: {dados['uf_usada']}, mediana mulheres {mulheres}, homens {homens}"]}

    def analise_sintese(estado: Estado, config: RunnableConfig) -> dict[str, Any]:
        validacao = estado.get("validacao")
        pedido = PedidoDeRascunho(
            pergunta=estado["pergunta"],
            intencao=estado["intencao"],
            parametros=estado["parametros"],
            dados_salariais=estado.get("dados_salariais"),
            evidencias=estado.get("evidencias", []),
            motivo_reprovacao=validacao.motivo if validacao and not validacao.aprovado else None,
        )
        # o texto normalizado é o que a Validação confere e o que vai para a resposta
        rascunho = normalizar_citacoes(redator.redigir(pedido, config))
        tentativa = estado.get("tentativas", 0) + 1
        return {"rascunho": rascunho, "passos": [f"analise_sintese: rascunho {tentativa} ({len(rascunho)} caracteres)"]}

    def validacao(estado: Estado) -> dict[str, Any]:
        rascunho, evidencias = estado["rascunho"], estado.get("evidencias", [])
        with rastreio.etapa("validar-rascunho", "evaluator", {"rascunho": rascunho}) as etapa:
            resultado = validar(rascunho, evidencias, estado.get("dados_salariais"))
            etapa.registrar(asdict(resultado))
        tentativas = estado.get("tentativas", 0) + 1
        veredito = "aprovado" if resultado.aprovado else f"reprovado ({resultado.motivo})"
        return {"validacao": resultado, "tentativas": tentativas, "passos": [f"validacao: {veredito}"]}

    def rotear_validacao(estado: Estado) -> str:
        if estado["validacao"].aprovado or estado["tentativas"] >= MAX_TENTATIVAS:
            return "resposta"
        return "analise_sintese"

    def resposta(estado: Estado) -> dict[str, Any]:
        if estado.get("bloqueio"):
            texto = estado["bloqueio"]
        elif estado["intencao"].fora_de_escopo:
            texto = MSG_FORA_DE_ESCOPO
        elif estado["validacao"].aprovado:
            texto = formatar_resposta(estado["rascunho"], estado.get("evidencias", []), estado.get("dados_salariais"))
        else:
            texto = formatar_abstencao(estado.get("evidencias", []), estado.get("dados_salariais"))
        _lembrar(estado)
        return {"resposta_final": texto, "passos": ["resposta: formatada pelo Orquestrador"]}

    def _lembrar(estado: Estado) -> None:
        """Guarda intenção, ocupação e UF da pergunta atendida; pergunta bloqueada ou fora de escopo não muda nada."""
        sessao, intencao, parametros = estado.get("sessao"), estado.get("intencao"), estado.get("parametros")
        if not memoria or not sessao or estado.get("bloqueio") or not intencao or intencao.fora_de_escopo:
            return
        memoria.lembrar(sessao, Lembranca(intencao.salario, intencao.direitos, parametros.cbo_familia,
                                          parametros.cbo_familia_nome, parametros.ocupacao, parametros.uf))

    grafo = StateGraph(Estado)
    for nome, funcao in (("orquestrador", orquestrador), ("pesquisa", pesquisa), ("analise_dados", analise_dados),
                         ("analise_sintese", analise_sintese), ("validacao", validacao), ("resposta", resposta)):
        grafo.add_node(nome, funcao)
    grafo.add_edge(START, "orquestrador")
    grafo.add_conditional_edges("orquestrador", rotear_entrada, ["pesquisa", "analise_dados", "resposta"])
    grafo.add_edge("pesquisa", "analise_sintese")
    grafo.add_edge("analise_dados", "analise_sintese")
    grafo.add_edge("analise_sintese", "validacao")
    grafo.add_conditional_edges("validacao", rotear_validacao, ["analise_sintese", "resposta"])
    grafo.add_edge("resposta", END)
    return grafo.compile()


def responder(grafo: Any, pergunta: str, config: RunnableConfig | None = None, sessao: str | None = None) -> Estado:
    """Roda o grafo para uma pergunta e devolve o estado final (a resposta está em `resposta_final`)."""
    return grafo.invoke({"pergunta": pergunta, "sessao": sessao, "passos": []}, config=config)
