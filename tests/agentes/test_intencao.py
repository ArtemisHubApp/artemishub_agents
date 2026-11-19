"""Intenção e parâmetros em formatos coloquiais (achados da revisão final)."""

import pytest

from src.agentes.domain.intencao import extrair_salario, extrair_uf, interpretar, termo_de_ocupacao
from src.agentes.domain.modelos import Intencao


@pytest.mark.parametrize("texto, valor", [
    ("ganho R$ 7 mil", 7000.0),
    ("meu salário é 7500", 7500.0),
    ("ganho 7 mil reais", 7000.0),
    ("ganho R$ 7", None),  # abaixo do piso: provavelmente "7 mil" mal escrito
])
def test_extrair_salario_formatos_coloquiais(texto, valor):
    assert extrair_salario(texto) == valor


def test_termo_de_ocupacao_ignora_mil_e_reais():
    assert termo_de_ocupacao("Sou analista e ganho R$ 7 mil reais") == "analista"


@pytest.mark.parametrize("pergunta, intencao", [
    ("Quanto tempo dura a licença-maternidade?", Intencao(False, True)),
    ("Sofri assédio no trabalho, o que faço?", Intencao(False, True)),
    ("Quanto ganha uma engenheira?", Intencao(True, False)),
])
def test_intencao_quanto_sozinho_nao_e_salario(pergunta, intencao):
    assert interpretar(pergunta) == intencao


@pytest.mark.parametrize("texto, termo", [
    ("Quanto ganha uma desenvolvedora em SP?", "desenvolvedor"),
    ("Sou engenheira de software", "engenheiro software"),
    ("quanto ganha uma programadora", "programador"),
    ("quanto ganha uma analista de sistemas", "analista sistemas"),
    ("quanto ganha uma cientista de dados", "cientista dados"),
])
def test_termo_de_ocupacao_usa_a_forma_da_cbo(texto, termo):
    assert termo_de_ocupacao(texto) == termo


@pytest.mark.parametrize("texto, uf", [
    ("quanto ganha uma analista em df?", "DF"),
    ("analista no rj", "RJ"),
    ("em se tratando de salário", None),  # "se" é palavra, não Sergipe
])
def test_extrair_uf_sigla_minuscula_depois_de_preposicao(texto, uf):
    assert extrair_uf(texto) == uf


@pytest.mark.parametrize("texto, palavras", [
    ("pesquisadora de biologia", {"pesquisador", "biologia"}),
    ("analista de engenharia", {"analista", "engenharia"}),
    ("quanto ganha uma técnica em eletrônica", {"tecnica", "tecnico", "eletronica", "eletronico"}),
])
def test_termo_de_ocupacao_mantem_a_palavra_original_alem_do_masculino(texto, palavras):
    assert palavras <= set(termo_de_ocupacao(texto).split())
