"""Adaptadores: RAG por subprocesso (com executor falso), RAIS real (CSVs versionados) e redatores."""

import json
import subprocess

import httpx
import openai
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from src.agentes.adapters.llm import RedatorLLM, RedatorPadrao, redator_de_ambiente
from src.agentes.adapters.rag_subprocesso import MARCADOR, BuscadorRagSubprocesso
from src.agentes.adapters.rastreio import criar_rastreador, rastrear_pergunta
from src.agentes.adapters.salarios_rais import ConsultaRais
from src.agentes.application.grafo import construir_grafo
from src.agentes.application.portas import FonteIndisponivel, RastreadorNulo
from src.agentes.domain.modelos import Evidencia, Intencao, Parametros, PedidoDeRascunho
from tests.agentes.test_dominio import DADOS, EVIDENCIAS, PERGUNTA_DEMO
from tests.agentes.test_grafo import BuscadorFake, ConsultaFake, RedatorFake

ACHADO = {"id": "FONTE 1", "titulo": "Lei 14.611/2023", "url": "https://planalto.gov.br/l14611", "pagina": None,
          "artigo": "art. 2", "texto": "A igualdade salarial..."}


class ExecutorFake:
    def __init__(self, stdout="", returncode=0, stderr="", erro=None):
        self.stdout, self.returncode, self.stderr, self.erro, self.chamadas = stdout, returncode, stderr, erro, []

    def __call__(self, comando, **kwargs):
        self.chamadas.append((comando, kwargs))
        if self.erro:
            raise self.erro
        return subprocess.CompletedProcess(comando, self.returncode, self.stdout, self.stderr)


def _buscador(executor, tmp_path, parcial=False):
    return BuscadorRagSubprocesso(tmp_path, parcial=parcial, executar=executor)


def test_rag_le_o_json_marcado_e_ignora_ruido(tmp_path):
    executor = ExecutorFake(stdout=f"Loading weights 100%\n{MARCADOR}{json.dumps([ACHADO])}\n")
    assert _buscador(executor, tmp_path).buscar("igualdade salarial", 5) == [Evidencia(**ACHADO)]


def test_rag_roda_no_ambiente_do_rag_com_a_pergunta_no_stdin(tmp_path):
    executor = ExecutorFake(stdout=f"{MARCADOR}[]")
    _buscador(executor, tmp_path, parcial=True).buscar("igualdade salarial", 3)
    comando, kwargs = executor.chamadas[0]
    assert comando[:4] == ["uv", "run", "--project", str(tmp_path)] and kwargs["cwd"] == tmp_path
    assert json.loads(kwargs["input"]) == {"tema": "igualdade salarial", "top_k": 3, "parcial": True}


@pytest.mark.parametrize("executor, trecho", [
    (ExecutorFake(returncode=1, stderr="Traceback...\nValueError: No published index"), "No published index"),
    (ExecutorFake(stdout="sem marcador"), "saída sem resultado"),
    (ExecutorFake(stdout=f"{MARCADOR}{{quebrado"), "JSON inválido"),
    (ExecutorFake(erro=FileNotFoundError("uv")), "uv não encontrado"),
    (ExecutorFake(erro=subprocess.TimeoutExpired(["uv"], 180)), "demorou mais de"),
])
def test_rag_transforma_falha_em_fonte_indisponivel(tmp_path, executor, trecho):
    with pytest.raises(FonteIndisponivel, match=trecho):
        _buscador(executor, tmp_path).buscar("x", 5)


def test_rag_de_ambiente_usa_a_variavel(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTEMIS_RAG_DIR", str(tmp_path))
    monkeypatch.setenv("ARTEMIS_RAG_PARCIAL", "1")
    buscador = BuscadorRagSubprocesso.de_ambiente()
    assert buscador.rag_dir == tmp_path and buscador.parcial is True


def test_consulta_rais_usa_os_agregados_versionados():
    consulta = ConsultaRais()
    assert consulta.buscar_ocupacao("analista sistemas")[0]["cbo_familia"] == "2124"
    dados = consulta.consultar("2124", "DF", 7500.0)
    assert dados["suficiente"] and dados["por_sexo"]["feminino"]["p50"] > 0 and dados["salario_informado"]


def _pedido():
    return PedidoDeRascunho("pergunta", Intencao(True, True), Parametros("analista", "2124", "TI", "DF", None),
                            DADOS, EVIDENCIAS)


def test_redator_padrao_nao_usa_llm():
    assert "[RAIS]" in RedatorPadrao().redigir(_pedido())


class PromptFake:
    """Imita o prompt chat do Langfuse: `get_langchain_prompt` devolve as mensagens com {variavel}."""

    def get_langchain_prompt(self):
        return [("system", "SISTEMA-DE-TESTE"),
                ("user", "{pergunta}|{ocupacao}|{dados_salariais}|{evidencias}|{correcao}")]


class FontePromptFake:
    def __init__(self, falha=False):
        self.falha = falha

    def obter(self):
        if self.falha:
            raise RuntimeError("Langfuse fora do ar")
        return PromptFake()


class ModeloQueGrava(GenericFakeChatModel):
    """Modelo falso que guarda as mensagens que recebeu."""

    recebidas: list = []

    def _generate(self, messages, *args, **kwargs):
        ModeloQueGrava.recebidas = messages
        return super()._generate(messages, *args, **kwargs)


def test_redator_llm_compila_o_prompt_do_langfuse_com_as_variaveis():
    modelo = ModeloQueGrava(messages=iter([AIMessage(content="Texto do modelo [RAIS].")]))
    assert RedatorLLM(modelo, FontePromptFake()).redigir(_pedido()) == "Texto do modelo [RAIS]."
    sistema, usuario = ModeloQueGrava.recebidas
    assert sistema.content == "SISTEMA-DE-TESTE" and "R$ 8.462,79" in usuario.content


def _falha(_):
    raise openai.APIConnectionError(request=httpx.Request("POST", "https://llm.example/v1"))


def test_redator_llm_usa_o_rascunho_padrao_se_o_provedor_falhar():
    redator = RedatorLLM(RunnableLambda(_falha), FontePromptFake())
    assert redator.redigir(_pedido()) == RedatorPadrao().redigir(_pedido())


def test_redator_llm_usa_o_rascunho_padrao_se_o_prompt_nao_vier_do_langfuse():
    modelo = GenericFakeChatModel(messages=iter([AIMessage(content="nunca usado")]))
    assert RedatorLLM(modelo, FontePromptFake(falha=True)).redigir(_pedido()) == RedatorPadrao().redigir(_pedido())


def test_redator_de_ambiente_sem_chave_e_o_padrao(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert isinstance(redator_de_ambiente(), RedatorPadrao)


def test_sem_chaves_do_langfuse_o_rastreio_e_nulo_e_o_fluxo_roda(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    rastreador = criar_rastreador()
    assert isinstance(rastreador, RastreadorNulo)
    grafo = construir_grafo(BuscadorFake(), ConsultaFake(), RedatorFake(), rastreador)
    estado, link = rastrear_pergunta(rastreador, grafo, PERGUNTA_DEMO, redator="RedatorFake")
    assert link is None and estado["validacao"].aprovado


def test_redator_de_ambiente_sem_langfuse_e_o_padrao_mesmo_com_chave_do_llm(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "chave-de-teste")
    monkeypatch.setenv("LLM_MODEL", "modelo-de-teste")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    assert isinstance(redator_de_ambiente(), RedatorPadrao)  # sem Langfuse não há prompt: nada de cópia no repo


def test_redator_de_ambiente_com_chave_usa_o_llm(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-teste")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-teste")
    monkeypatch.setenv("LLM_API_KEY", "chave-de-teste")
    monkeypatch.setenv("LLM_MODEL", "modelo-de-teste")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example/v1")
    assert isinstance(redator_de_ambiente(), RedatorLLM)


@pytest.mark.parametrize("termo, familia", [
    ("cientsita cientsito dados", "2112"),   # erro de digitação de "cientista"
    ("cientista dados", "2112"),
    ("analista sistemas", "2124"),
])
def test_consulta_rais_corrige_erro_de_digitacao_pelas_palavras_da_cbo(termo, familia):
    assert ConsultaRais().buscar_ocupacao(termo)[0]["cbo_familia"] == familia
