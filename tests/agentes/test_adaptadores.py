"""Adaptadores: pacote artemis_rag (busca falsa e pacote sem índice), RAIS real (CSVs versionados) e redatores."""

import artemis_rag
import httpx
import openai
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from src.agentes.adapters.llm import RedatorLLM, RedatorPadrao, redator_de_ambiente
from src.agentes.adapters.rag_pacote import BuscadorArtemisRag
from src.agentes.adapters.rastreio import criar_rastreador, rastrear_pergunta
from src.agentes.adapters.salarios_rais import ConsultaRais
from src.agentes.application.grafo import construir_grafo
from src.agentes.application.portas import FonteIndisponivel, RastreadorNulo
from src.agentes.domain.modelos import Evidencia, Intencao, Parametros, PedidoDeRascunho
from tests.agentes.test_dominio import DADOS, EVIDENCIAS, PERGUNTA_DEMO
from tests.agentes.test_grafo import BuscadorFake, ConsultaFake, RedatorFake


def _evidencia_rag(n):
    return artemis_rag.Evidencia(id=f"FONTE {n}", titulo="Lei 14.611/2023", url="https://planalto.gov.br/l14611",
                                 pagina=None, artigo="art. 2", texto="A igualdade salarial...", distancia=0.4)


def test_rag_converte_as_evidencias_do_pacote_para_o_dominio(tmp_path):
    chamadas = []

    def buscar(tema, **opcoes):
        chamadas.append((tema, opcoes))
        return [_evidencia_rag(1), _evidencia_rag(2)]

    evidencias = BuscadorArtemisRag(tmp_path, parcial=True, buscar=buscar).buscar("igualdade salarial", 2)
    assert chamadas == [("igualdade salarial", {"top_k": 2, "indice": tmp_path, "parcial": True})]
    assert evidencias == [Evidencia(f"FONTE {n}", "Lei 14.611/2023", "https://planalto.gov.br/l14611", None, "art. 2",
                                    "A igualdade salarial...") for n in (1, 2)]


@pytest.mark.parametrize("tipo", [artemis_rag.IndiceIndisponivel, ValueError, OSError, RuntimeError])
def test_rag_transforma_falha_em_fonte_indisponivel(tmp_path, tipo):
    def buscar(tema, **opcoes):
        raise tipo("No published index")

    with pytest.raises(FonteIndisponivel, match="No published index"):
        BuscadorArtemisRag(tmp_path, buscar=buscar).buscar("x", 5)


def test_rag_real_sem_indice_publicado_vira_fonte_indisponivel(tmp_path):
    with pytest.raises(FonteIndisponivel):  # pacote de verdade, sem rede: falha antes de carregar o modelo
        BuscadorArtemisRag(tmp_path).buscar("igualdade salarial", 5)


def test_rag_de_ambiente_prefere_o_indice_explicito(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTEMIS_RAG_INDEX_DIR", str(tmp_path / "indice"))
    monkeypatch.setenv("ARTEMIS_RAG_PARCIAL", "1")
    buscador = BuscadorArtemisRag.de_ambiente()
    assert buscador.indice == tmp_path / "indice" and buscador.parcial is True


def test_rag_de_ambiente_usa_o_indice_do_repo_do_rag_por_padrao(tmp_path, monkeypatch):
    monkeypatch.delenv("ARTEMIS_RAG_INDEX_DIR", raising=False)
    monkeypatch.delenv("ARTEMIS_RAG_PARCIAL", raising=False)
    monkeypatch.setenv("ARTEMIS_RAG_DIR", str(tmp_path))
    buscador = BuscadorArtemisRag.de_ambiente()
    assert buscador.indice == tmp_path / ".chroma" and buscador.parcial is False


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
    estado, link = rastrear_pergunta(rastreador, grafo, PERGUNTA_DEMO, contexto={"interface": "teste"})
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
