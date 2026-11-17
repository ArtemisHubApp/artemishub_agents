import pandas as pd
import pytest

from src.salarios import BRASIL, TODOS, agregar, buscar_ocupacao, consultar, listar_ocupacoes


def vinculos(familia, uf, sexo, n, salario, horas=40, cbo=None, nome=None):
    return pd.DataFrame({
        "cbo": [cbo or f"{familia}05"] * n,
        "cbo_nome": [nome or "Analista de desenvolvimento de sistemas"] * n,
        "cbo_familia": [familia] * n,
        "cbo_familia_nome": ["Analistas de tecnologia da informação"] * n,
        "uf": [uf] * n,
        "sexo": [sexo] * n,
        "remuneracao_media": [float(salario)] * n,
        "horas_contratuais": [horas] * n,
    })


@pytest.fixture
def dados():
    return pd.concat([
        vinculos("2124", "DF", "feminino", 40, 7000),
        vinculos("2124", "DF", "masculino", 60, 8000),
        vinculos("2124", "AC", "feminino", 5, 6000),       # poucas mulheres no AC
        vinculos("2124", "AC", "masculino", 50, 9000),
    ], ignore_index=True)


def linha(tabela, uf, sexo):
    return tabela[(tabela["uf"] == uf) & (tabela["sexo"] == sexo)].iloc[0]


def test_agrega_por_uf_e_sexo_com_totais(dados):
    tabela = agregar(dados, 2025)
    assert linha(tabela, "DF", "feminino")["p50"] == 7000
    assert linha(tabela, "DF", TODOS)["n"] == 100
    assert linha(tabela, BRASIL, "feminino")["n"] == 45
    assert linha(tabela, BRASIL, TODOS)["n"] == 155
    assert (tabela["ano"] == 2025).all()


def test_descarta_recortes_com_poucos_vinculos(dados):
    tabela = agregar(dados, 2025, n_minimo=30)
    assert tabela[(tabela["uf"] == "AC") & (tabela["sexo"] == "feminino")].empty
    assert not tabela[(tabela["uf"] == "AC") & (tabela["sexo"] == "masculino")].empty


def test_tempo_integral_ignora_jornada_parcial():
    dados = pd.concat([
        vinculos("2124", "DF", "feminino", 40, 8000, horas=40),
        vinculos("2124", "DF", "feminino", 40, 3000, horas=20),
    ], ignore_index=True)
    tabela = agregar(dados, 2025)
    df = linha(tabela, "DF", "feminino")
    assert df["n_integral"] == 40
    assert df["p50_integral"] == 8000


def test_consulta_calcula_diferenca_bruta_e_compara_salario(dados):
    resultado = consultar("2124", "df", salario=7500, tabela=agregar(dados, 2025))
    assert resultado["uf_usada"] == "DF"
    assert resultado["suficiente"]
    assert resultado["por_sexo"]["masculino"]["p50"] == 8000
    assert resultado["diferenca_bruta_mediana_pct"] == 12.5     # (8000 - 7000) / 8000
    assert resultado["salario_informado"]["vs_mediana_feminino_pct"] == 7.1
    assert resultado["salario_informado"]["vs_mediana_masculino_pct"] == -6.2
    assert any("bruta" in aviso for aviso in resultado["avisos"])


def test_consulta_usa_brasil_quando_a_uf_nao_tem_os_dois_sexos(dados):
    resultado = consultar("2124", "AC", tabela=agregar(dados, 2025))
    assert resultado["uf_usada"] == BRASIL
    assert resultado["por_sexo"]["feminino"]["n"] == 45
    assert any("Brasil todo" in aviso for aviso in resultado["avisos"])


def test_consulta_sem_dados_nao_inventa_numeros(dados):
    resultado = consultar("9999", "DF", salario=5000, tabela=agregar(dados, 2025))
    assert not resultado["suficiente"]
    assert resultado["por_sexo"] == {}
    assert resultado["diferenca_bruta_mediana_pct"] is None
    assert resultado["salario_informado"] is None


def test_busca_ocupacao_sem_acento_e_por_palavras():
    dados = pd.concat([
        vinculos("2124", "DF", "feminino", 10, 7000, cbo="212405"),
        vinculos("3171", "DF", "feminino", 30, 4000, cbo="317110",
                 nome="Desenvolvedor de sistemas de tecnologia da informação (técnico)"),
    ], ignore_index=True)
    ocupacoes = listar_ocupacoes(dados)
    achadas = buscar_ocupacao("ANALISTA de Sistemas", ocupacoes)
    assert achadas[0]["cbo"] == "212405"            # duas palavras batem
    assert achadas[1]["cbo"] == "317110"            # só "sistemas" bate
    assert buscar_ocupacao("informacao", ocupacoes)[0]["cbo"] == "317110"
    assert buscar_ocupacao("de", ocupacoes) == []
