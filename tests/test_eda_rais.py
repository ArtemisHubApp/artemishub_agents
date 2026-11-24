"""Testes unitários para os módulos de EDA da RAIS STEM (issue #3)."""

from __future__ import annotations

import json

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.calcular_metricas_parquet import calcular_metricas_dataframe, processar_parquet
from src.eda_rais import calcular_gap_salarial, calcular_percentil, estatisticas_descritivas


def test_calcular_percentil_casos_basicos() -> None:
    assert calcular_percentil([], 50) == 0.0
    assert calcular_percentil([42.0], 90) == 42.0
    assert calcular_percentil([10.0, 20.0, 30.0], 50) == 20.0
    assert calcular_percentil([10.0, 20.0, 30.0, 40.0], 25) == pytest.approx(17.5)


def test_estatisticas_descritivas_lista_vazia_e_valores() -> None:
    vazio = estatisticas_descritivas([])
    assert vazio["n"] == 0
    assert vazio["media"] == 0

    stats = estatisticas_descritivas([1000.0, 2000.0, 3000.0, 4000.0, 5000.0])
    assert stats["n"] == 5
    assert stats["media"] == 3000.0
    assert stats["mediana"] == 3000.0
    assert stats["p25"] == 2000.0
    assert stats["p75"] == 4000.0
    assert stats["iqr"] == 2000.0


def test_calcular_gap_salarial_suprime_amostra_pequena_lgpd() -> None:
    resultado = calcular_gap_salarial([5000.0] * 12, [4000.0] * 5, min_amostra=10)
    assert resultado["status"] == "amostra_insuficiente"
    assert resultado["confiavel"] is False
    assert resultado["gap_medio_pct"] is None
    assert resultado["gap_mediano_pct"] is None


def test_calcular_gap_salarial_amostra_confiavel() -> None:
    homens = [10000.0] * 10
    mulheres = [8000.0] * 10
    resultado = calcular_gap_salarial(homens, mulheres, min_amostra=10)
    assert resultado["status"] == "confiavel"
    assert resultado["confiavel"] is True
    assert resultado["gap_medio_pct"] == 20.0
    assert resultado["gap_mediano_pct"] == 20.0
    assert resultado["razao_paridade"] == 0.8


def _dataframe_sintetico() -> pd.DataFrame:
    linhas = []
    for i in range(12):
        linhas.append(
            {
                "remuneracao_media": 8000.0 + i * 100.0,
                "remuneracao_media_sm": 5.3,
                "sexo": "masculino",
                "nivel": "superior",
                "stem_area": "computacao",
                "raca_cor": "branca",
                "cbo_familia": "2124",
                "uf": "SP",
                "tempo_emprego_meses": 24.0 + i,
                "idade": 30 + (i % 5),
                "horas_contratuais": 40,
                "escolaridade": "superior_completo",
            }
        )
    for i in range(12):
        linhas.append(
            {
                "remuneracao_media": 6000.0 + i * 100.0,
                "remuneracao_media_sm": 4.0,
                "sexo": "feminino",
                "nivel": "superior",
                "stem_area": "computacao",
                "raca_cor": "parda",
                "cbo_familia": "2124",
                "uf": "SP",
                "tempo_emprego_meses": 20.0 + i,
                "idade": 29 + (i % 5),
                "horas_contratuais": 40,
                "escolaridade": "superior_completo",
            }
        )
    return pd.DataFrame(linhas)


def test_calcular_metricas_dataframe_sintetico() -> None:
    df = _dataframe_sintetico()
    metricas = calcular_metricas_dataframe(df)

    assert metricas["global"]["total_vinculos"] == 24
    assert metricas["sexo"]["masculino"]["n"] == 12
    assert metricas["sexo"]["feminino"]["n"] == 12
    assert metricas["sexo"]["gap_mediano_pct"] > 0
    assert metricas["nivel"]["superior"]["total"] == 24
    assert "cbo_uf_sexo" in metricas["small_cells"]
    assert "oaxaca_blinder_superior" in metricas
    assert "proposta_meta_r2" in metricas


def test_processar_parquet_sintetico(tmp_path) -> None:
    df = _dataframe_sintetico()
    parquet_path = tmp_path / "rais_sintetico.parquet"
    json_path = tmp_path / "reports" / "saida.json"

    pq.write_table(pa.Table.from_pandas(df), parquet_path)
    resultados = processar_parquet(parquet_path, json_path)

    assert json_path.exists()
    lido = json.loads(json_path.read_text(encoding="utf-8"))
    assert lido["global"]["total_vinculos"] == 24
    assert resultados["global"]["total_vinculos"] == 24
