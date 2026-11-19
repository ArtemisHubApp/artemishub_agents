"""Chat no terminal: laço de conversa com entrada e saída simuladas, sem LLM nem RAG."""

from src.agentes.adapters.rastreio import rastrear_pergunta
from src.agentes.application.grafo import construir_grafo
from src.agentes.application.portas import RastreadorNulo
from src.agentes.chat import AJUDA, DESPEDIDA, conversar
from tests.agentes.test_dominio import PERGUNTA_DEMO
from tests.agentes.test_grafo import BuscadorFake, ConsultaFake, RedatorFake


class Terminal:
    """Entrada roteirizada; `None` simula Ctrl+D e `KeyboardInterrupt` simula Ctrl+C."""

    def __init__(self, *entradas):
        self.entradas, self.saida = list(entradas), []

    def ler(self, prompt):
        entrada = self.entradas.pop(0)
        if entrada is None:
            raise EOFError
        if entrada is KeyboardInterrupt:
            raise KeyboardInterrupt
        return entrada

    def escrever(self, texto=""):
        self.saida.append(str(texto))

    @property
    def texto(self):
        return "\n".join(self.saida)


def _responder():
    grafo = construir_grafo(BuscadorFake(), ConsultaFake(), RedatorFake(), RastreadorNulo())
    perguntas = []

    def responder(pergunta):
        perguntas.append(pergunta)
        return rastrear_pergunta(RastreadorNulo(), grafo, pergunta, contexto={"interface": "teste"})

    return responder, perguntas


def test_responde_e_sai_com_o_comando():
    responder, perguntas = _responder()
    terminal = Terminal(PERGUNTA_DEMO, "/sair")
    assert conversar(responder, terminal.ler, terminal.escrever) == 0
    assert perguntas == [PERGUNTA_DEMO]
    assert "R$ 7.000,00" in terminal.texto and DESPEDIDA in terminal.texto


def test_linha_vazia_nao_vira_pergunta():
    responder, perguntas = _responder()
    terminal = Terminal("", "   ", "/sair")
    conversar(responder, terminal.ler, terminal.escrever)
    assert perguntas == []


def test_passos_liga_e_desliga_o_passo_a_passo():
    responder, _ = _responder()
    terminal = Terminal(PERGUNTA_DEMO, "/passos", PERGUNTA_DEMO, "/passos", "/sair")
    conversar(responder, terminal.ler, terminal.escrever)
    assert terminal.texto.count("orquestrador: intenção") == 1  # só na pergunta com o passo a passo ligado


def test_ajuda_e_comando_desconhecido():
    responder, perguntas = _responder()
    terminal = Terminal("/ajuda", "/xyz", "/sair")
    conversar(responder, terminal.ler, terminal.escrever)
    assert AJUDA in terminal.texto and "Comando desconhecido: /xyz" in terminal.texto and perguntas == []


def test_ctrl_d_e_ctrl_c_saem_sem_erro():
    for fim in (None, KeyboardInterrupt):
        responder, _ = _responder()
        terminal = Terminal(fim)
        assert conversar(responder, terminal.ler, terminal.escrever) == 0
        assert DESPEDIDA in terminal.texto


def test_erro_numa_pergunta_nao_derruba_a_conversa():
    chamadas = []

    def responder(pergunta):
        chamadas.append(pergunta)
        raise RuntimeError("provedor fora do ar")

    terminal = Terminal("primeira", "segunda", "/sair")
    assert conversar(responder, terminal.ler, terminal.escrever) == 0
    assert chamadas == ["primeira", "segunda"] and "provedor fora do ar" in terminal.texto


def test_mostra_o_link_do_trace_quando_existe():
    terminal = Terminal("pergunta", "/sair")
    estado = {"resposta_final": "Resposta.", "passos": []}
    conversar(lambda _: (estado, "https://langfuse.example/trace/1"), terminal.ler, terminal.escrever)
    assert "https://langfuse.example/trace/1" in terminal.texto
