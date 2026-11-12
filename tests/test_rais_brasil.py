import json

import pandas as pd
import pytest

from src.rais_brasil import juntar


def salvar(pasta, regiao, linhas, sexo):
    df = pd.DataFrame({"uf": ["DF"] * linhas, "sexo": [sexo] * linhas, "nivel": ["superior"] * linhas,
                       "remuneracao_media": [5000.0] * linhas})
    df.to_parquet(pasta / f"rais_stem_2025_{regiao}.parquet", index=False)
    relatorio = {"linhas_por_etapa": {"lidas": linhas * 10, "apos_filtro_stem": linhas}}
    (pasta / f"rais_stem_2025_{regiao}.json").write_text(json.dumps(relatorio), encoding="utf-8")


def test_junta_regioes_e_soma_o_funil(tmp_path):
    salvar(tmp_path, "a", 2, "feminino")
    salvar(tmp_path, "b", 3, "masculino")
    destino, resumo = juntar(2025, pasta=tmp_path, regioes=["a", "b"])
    assert len(pd.read_parquet(destino)) == 5
    assert resumo["linhas_por_etapa"]["lidas"] == 50 and resumo["linhas_por_etapa"]["apos_filtro_stem"] == 5
    assert resumo["por_sexo"] == {"masculino": 3, "feminino": 2}


def test_avisa_quando_falta_regiao(tmp_path):
    salvar(tmp_path, "a", 1, "feminino")
    with pytest.raises(FileNotFoundError, match="b"):
        juntar(2025, pasta=tmp_path, regioes=["a", "b"])
