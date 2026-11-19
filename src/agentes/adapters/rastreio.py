"""Rastreio no Langfuse: um trace `responder-pergunta` por pergunta, com os nós do LangGraph e as etapas tipadas.

Só liga quando `LANGFUSE_PUBLIC_KEY` e `LANGFUSE_SECRET_KEY` existem; senão o rastreador nulo assume.
Cada execução tem ambiente (`development` ou `demo`) e release (hash do commit); o resultado vira metadata
e scores, para filtrar e montar painéis. O salário informado não entra na metadata nem nos scores (mas a
pergunta, que pode contê-lo, é a entrada do trace).
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from src.agentes.application.grafo import Estado, responder
from src.agentes.application.portas import Etapa, RastreadorNulo

NOME_TRACE = "responder-pergunta"
TAGS = ["prototipo-multiagente"]
AMBIENTES = ("development", "demo")  # production fica para a API do backend (#36)

Contexto = dict[str, str]
"""Como a pergunta foi atendida: interface (chat/demo), redator, modelo, modo do RAG, label do prompt."""


def langfuse_configurado() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def release_atual(executar: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> str:
    """Hash curto do commit em execução, para comparar versões no Langfuse."""
    try:
        resultado = executar(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False,
                             cwd=os.path.dirname(__file__))
    except (OSError, subprocess.SubprocessError):
        return "desconhecida"
    return resultado.stdout.strip() if resultado.returncode == 0 and resultado.stdout.strip() else "desconhecida"


def configurar_ambiente(ambiente: str | None, release: str | None = None) -> None:
    """Define o environment e o release do Langfuse. Precisa rodar antes do cliente ser criado."""
    escolhido = ambiente or os.getenv("LANGFUSE_TRACING_ENVIRONMENT") or "development"
    if escolhido not in AMBIENTES:
        raise ValueError(f"Ambiente {escolhido!r} não é aceito aqui; use {', '.join(AMBIENTES)} "
                         "(production fica para a API do backend).")
    os.environ["LANGFUSE_TRACING_ENVIRONMENT"] = escolhido
    os.environ.setdefault("LANGFUSE_RELEASE", release or release_atual())


def atributos_do_trace(contexto: Contexto, sessao: str | None) -> dict[str, Any]:
    """Atributos propagados a todas as observações: nome do trace, tags, sessão e metadata em texto."""
    atributos: dict[str, Any] = {
        "trace_name": NOME_TRACE,
        "tags": [*TAGS, contexto.get("interface", "desconhecida")],
        "metadata": {chave: str(valor) for chave, valor in contexto.items()},
    }
    if sessao:
        atributos["session_id"] = sessao
    return atributos


def metadata_do_resultado(estado: Estado) -> dict[str, Any]:
    """O que aconteceu na pergunta, sem dado pessoal: nada do valor do salário informado."""
    validacao, intencao, parametros = estado.get("validacao"), estado.get("intencao"), estado.get("parametros")
    dados = estado.get("dados_salariais") or {}
    return {
        "intencao": [nome for nome, ativo in (("salario", intencao and intencao.salario),
                                              ("direitos", intencao and intencao.direitos)) if ativo],
        "cbo_familia": parametros.cbo_familia if parametros else None,
        "ocupacao": parametros.ocupacao if parametros else None,
        "uf_pedida": parametros.uf if parametros else None,
        "uf_usada": dados.get("uf_usada"),  # pode ser BR quando a UF não tem vínculos suficientes
        "tem_salario_informado": bool(parametros and parametros.salario is not None),
        "evidencias": len(estado.get("evidencias", [])),
        "falha_pesquisa": estado.get("falha_pesquisa"),
        "motivo_reprovacao": validacao.motivo if validacao and not validacao.aprovado else None,
    }


def scores_do_resultado(estado: Estado) -> list[tuple[str, float, str]]:
    """Rótulos definidos depois da execução viram scores (nome, valor, tipo), como recomenda o Langfuse."""
    validacao, intencao = estado.get("validacao"), estado.get("intencao")
    bloqueada = bool(estado.get("bloqueio"))
    fora_de_escopo = bool(not bloqueada and intencao and intencao.fora_de_escopo)
    aprovada = bool(validacao and validacao.aprovado)
    abstencao = bool(validacao and not validacao.aprovado)
    return [
        ("validacao_aprovada", int(aprovada), "BOOLEAN"),
        ("tentativas", estado.get("tentativas", 0), "NUMERIC"),
        ("abstencao", int(abstencao), "BOOLEAN"),
        ("bloqueada", int(bloqueada), "BOOLEAN"),
        ("fora_de_escopo", int(fora_de_escopo), "BOOLEAN"),
    ]


class _EtapaLangfuse:
    def __init__(self, observacao: Any) -> None:
        self._observacao = observacao

    def registrar(self, saida: Any, metadata: dict[str, Any] | None = None) -> None:
        self._observacao.update(output=saida, metadata=metadata)


class LangfuseRastreador:
    def __init__(self, cliente: Any) -> None:
        self.cliente = cliente

    @contextmanager
    def etapa(self, nome: str, tipo: str, entrada: Any) -> Iterator[Etapa]:
        with self.cliente.start_as_current_observation(name=nome, as_type=tipo, input=entrada) as observacao:
            yield _EtapaLangfuse(observacao)


def rastrear_pergunta(rastreador: LangfuseRastreador | RastreadorNulo, grafo: Any, pergunta: str,
                      contexto: Contexto, sessao: str | None = None) -> tuple[Estado, str | None]:
    """Roda o grafo dentro de um trace `responder-pergunta`: entrada é a pergunta, saída é a resposta final.

    `sessao` agrupa os traces de uma mesma conversa (chat no terminal) no Sessions view do Langfuse.
    """
    if not isinstance(rastreador, LangfuseRastreador):
        return responder(grafo, pergunta, sessao=sessao), None
    from langfuse import propagate_attributes
    from langfuse.langchain import CallbackHandler

    cliente = rastreador.cliente
    try:
        with cliente.start_as_current_observation(name=NOME_TRACE, as_type="agent", input=pergunta) as raiz:
            with propagate_attributes(**atributos_do_trace(contexto, sessao)):
                estado = responder(grafo, pergunta,
                                   {"callbacks": [CallbackHandler()], "run_name": "fluxo-multiagente"}, sessao=sessao)
            raiz.update(output=estado["resposta_final"], metadata=metadata_do_resultado(estado))
            for nome, valor, tipo in scores_do_resultado(estado):
                raiz.score_trace(name=nome, value=valor, data_type=tipo)
            link = cliente.get_trace_url(trace_id=raiz.trace_id)
    finally:
        cliente.flush()  # script curto: sem flush, o trace (inclusive o de erro) não chega ao Langfuse
    return estado, link


def criar_rastreador() -> LangfuseRastreador | RastreadorNulo:
    if not langfuse_configurado():
        return RastreadorNulo()
    configurar_ambiente(None)  # sem escolha explícita: o do .env ou development
    from langfuse import get_client  # importa depois do .env carregado, como pede a documentação

    return LangfuseRastreador(get_client())
