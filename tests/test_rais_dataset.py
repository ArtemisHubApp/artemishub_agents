import pandas as pd

from src.rais_dataset import (
    COLUNAS,
    ETAPAS,
    carregar_stem,
    codigo,
    numero,
    tratar_bloco,
)

PADRAO = {
    "CBO 2002 Ocupação - Código": "212405", "CNAE 2.0 Classe - Código": "62015",
    "Ind Vínculo Ativo 31/12 - Código": "1", "Ind Vínculo Abandonado - Código": "0",
    "Tipo Vínculo - Código": "10", "Escolaridade Após 2005 - Código": "9", "Qtd Hora Contr": "40",
    "Idade": "29", "Tempo Emprego": "24.5", "Município Trab - Código": "530010",
    "Município - Código": "530010", "Raça Cor - Código": "8", "Sexo - Código": "2",
    "Tamanho Estabelecimento - Código": "7", "Vl Rem Média Nom": "8500.00", "Vl Rem Média (SM)": "5.60",
}


def bloco(*linhas):
    return pd.DataFrame([{**PADRAO, **linha} for linha in linhas], columns=list(COLUNAS))


def rodar(df):
    contagem = dict.fromkeys(ETAPAS, 0)
    return tratar_bloco(df, carregar_stem(), 2025, "centro_oeste", contagem), contagem


def test_codigo_recupera_zero_a_esquerda_e_ignora_lixo():
    assert codigo(pd.Series(["21210", "212405", " 99999", "-1", None]), 6).tolist()[:3] == ["021210", "212405", "099999"]
    assert codigo(pd.Series(["-1"]), 6).isna().all()


def test_numero_aceita_ponto_virgula_e_vazio():
    assert numero(pd.Series(["8500.00", ".00", "1.234,56", " "])).tolist()[:3] == [8500.0, 0.0, 1234.56]
    assert numero(pd.Series([" "])).isna().all()


def test_militar_com_zero_perdido_nao_vira_stem():
    # 21210 = 021210 (soldado da PM); sem o zfill seria confundido com a família 2121
    saida, contagem = rodar(bloco({"CBO 2002 Ocupação - Código": "21210"}))
    assert saida.empty and contagem["apos_filtro_stem"] == 0


def test_filtros_removem_publico_abandonado_e_remuneracao_zero():
    saida, contagem = rodar(bloco(
        {},                                        # fica
        {"Tipo Vínculo - Código": "30"},           # estatutário: sai
        {"Ind Vínculo Abandonado - Código": "1"},  # abandonado: sai
        {"Vl Rem Média Nom": ".00"},               # remuneração zero: sai
        {"Vl Rem Média Nom": "5.00", "Vl Rem Média (SM)": ".00"},  # R$ 5/mês, abaixo de 0,3 SM: sai
        {"Tipo Vínculo - Código": "55", "Ind Vínculo Ativo 31/12 - Código": "0"},  # aprendiz desligado: fica
    ))
    assert len(saida) == 2
    assert contagem == {"lidas": 6, "apos_filtro_stem": 6, "apos_filtro_setor_privado": 5,
                        "apos_tirar_abandonados": 4, "apos_tirar_remuneracao_zero": 3,
                        "apos_tirar_remuneracao_abaixo_0_3_sm": 2, "remuneracao_reais_e_sm_destrocadas": 0}
    assert saida["tipo_contrato"].tolist() == ["clt_indeterminado", "aprendiz"]
    assert saida["ativo_31_12"].tolist() == [True, False]


def test_padroniza_rotulos_uf_e_ignorados():
    saida, _ = rodar(bloco(
        {},
        {"Sexo - Código": "-1", "Raça Cor - Código": "-1", "Escolaridade Após 2005 - Código": "-1",
         "Município Trab - Código": "999999", "Município - Código": "520870", "CBO 2002 Ocupação - Código": "317110"},
    ))
    primeira, segunda = saida.iloc[0], saida.iloc[1]
    assert (primeira["sexo"], primeira["raca_cor"], primeira["escolaridade"], primeira["uf"]) == (
        "feminino", "parda", "superior_completo", "DF")
    assert (primeira["stem_area"], primeira["nivel"]) == ("computacao", "superior")
    assert pd.isna(segunda["sexo"]) and pd.isna(segunda["raca_cor"]) and pd.isna(segunda["escolaridade"])
    assert segunda["uf"] == "GO" and segunda["nivel"] == "tecnico"


def test_horas_aceitam_jornada_especial_e_descartam_99():
    saida, _ = rodar(bloco({"Qtd Hora Contr": "48"}, {"Qtd Hora Contr": "99"}, {"Qtd Hora Contr": "0"}))
    assert saida["horas_contratuais"].tolist()[0] == 48
    assert saida["horas_contratuais"].iloc[1:].isna().all()


def test_destroca_reais_e_salarios_minimos_trocados():
    # a linha normal (R$ 8.500 = 5,6 SM) ensina o salário mínimo do bloco; a segunda veio trocada
    saida, contagem = rodar(bloco({}, {"Vl Rem Média Nom": "3.70", "Vl Rem Média (SM)": "5617.52"}))
    assert (saida["remuneracao_media"].iloc[1], saida["remuneracao_media_sm"].iloc[1]) == (5617.52, 3.70)
    assert contagem["remuneracao_reais_e_sm_destrocadas"] == 1
