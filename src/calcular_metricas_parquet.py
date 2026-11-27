#!/usr/bin/env python3
"""Processamento estatístico otimizado da base RAIS STEM 2025.

Lê o arquivo parquet com as colunas da base RAIS STEM (PR #19) e calcula
as métricas da EDA, decomposição de Oaxaca-Blinder e baseline de R²,
salvando o resultado em `reports/reports_eda_real.json`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

PARQUET_PATH_PADRAO = Path("data/processed/rais_stem_2025_brasil.parquet")
OUTPUT_JSON_PADRAO = Path("reports/reports_eda_real.json")

COLUNAS_NECESSARIAS = [
    "remuneracao_media",
    "remuneracao_media_sm",
    "sexo",
    "nivel",
    "stem_area",
    "raca_cor",
    "cbo_familia",
    "uf",
    "tempo_emprego_meses",
    "idade",
    "horas_contratuais",
    "escolaridade",
]


def _preparar_colunas_categoricas(df: pd.DataFrame) -> pd.DataFrame:
    """Converte colunas de texto recorrentes em categóricas para reduzir memória."""
    cat_cols = ["sexo", "nivel", "stem_area", "raca_cor", "cbo_familia", "uf", "escolaridade"]
    for col in cat_cols:
        if col in df.columns:
            df[col] = df[col].astype("category")
    return df


def calcular_oaxaca_blinder(df: pd.DataFrame, n_amostra: int = 60000) -> dict[str, Any]:
    """Calcula a decomposição de Oaxaca-Blinder para o nível superior a partir do DataFrame."""
    try:
        import statsmodels.api as sm
    except ImportError as exc:
        return {"error": f"Dependência ausente para Oaxaca-Blinder: {exc}"}

    sub_sup = df[df["nivel"] == "superior"].copy()
    if sub_sup.empty:
        return {"error": "Nenhum registro encontrado para nivel == 'superior'."}

    sample_sup = sub_sup.sample(n=min(n_amostra, len(sub_sup)), random_state=42)
    sample_sup["log_rem"] = np.log(sample_sup["remuneracao_media"].clip(lower=100))
    sample_sup["tempo_emprego_meses"] = pd.to_numeric(sample_sup["tempo_emprego_meses"], errors="coerce").fillna(24)
    sample_sup["idade"] = pd.to_numeric(sample_sup["idade"], errors="coerce").fillna(32)
    sample_sup["horas_contratuais"] = pd.to_numeric(sample_sup["horas_contratuais"], errors="coerce").fillna(40)

    x_sup = pd.get_dummies(sample_sup[["stem_area", "uf"]], drop_first=True, dtype=float)
    x_sup["tempo_emprego_meses"] = sample_sup["tempo_emprego_meses"]
    x_sup["idade"] = sample_sup["idade"]
    x_sup["horas_contratuais"] = sample_sup["horas_contratuais"]
    x_sup["const"] = 1.0

    y_sup = sample_sup["log_rem"]
    is_m = sample_sup["sexo"] == "masculino"
    is_f = sample_sup["sexo"] == "feminino"

    if int(is_m.sum()) < 2 or int(is_f.sum()) < 2:
        return {"error": "Amostra insuficiente de homens ou mulheres para regressão OLS."}

    try:
        model_m = sm.OLS(y_sup[is_m], x_sup[is_m]).fit()
        model_f = sm.OLS(y_sup[is_f], x_sup[is_f]).fit()

        mean_x_m = x_sup[is_m].mean()
        mean_x_f = x_sup[is_f].mean()

        raw_log_gap = float(y_sup[is_m].mean() - y_sup[is_f].mean())
        explained = float(np.dot(mean_x_m - mean_x_f, model_m.params))
        unexplained = float(np.dot(mean_x_f, model_m.params - model_f.params))

        pct_explained = round((explained / raw_log_gap) * 100, 2) if raw_log_gap != 0 else 0.0
        pct_unexplained = round((unexplained / raw_log_gap) * 100, 2) if raw_log_gap != 0 else 0.0
        unexplained_wage_gap_pct = round((np.exp(unexplained) - 1.0) * 100, 2)

        return {
            "n_amostra": int(len(sample_sup)),
            "gap_total_log": round(raw_log_gap, 4),
            "gap_bruto_pct_equivalente": round((np.exp(raw_log_gap) - 1.0) * 100, 2),
            "parcela_explicada_dotacoes_pct": pct_explained,
            "parcela_nao_explicada_pct": pct_unexplained,
            "gap_salario_liquido_nao_explicado_pct": unexplained_wage_gap_pct,
            "r2_modelo_masculino": round(float(model_m.rsquared), 4),
            "r2_modelo_feminino": round(float(model_f.rsquared), 4),
            "nota_interpretacao": (
                "Parcela não explicada (compatível com discriminação, mas não só; "
                "inclui variáveis omitidas como experiência real, fluência em idiomas e negociação)."
            ),
        }
    except Exception as exc:
        return {"error": str(exc)}


def calcular_meta_r2(df: pd.DataFrame, n_amostra: int = 80000) -> dict[str, Any]:
    """Estima o R² baseline (OLS) e não-linear (HistGradientBoostingRegressor) a partir do DataFrame."""
    try:
        import statsmodels.api as sm
        from sklearn.ensemble import HistGradientBoostingRegressor
        from sklearn.metrics import r2_score
        from sklearn.model_selection import train_test_split
    except ImportError as exc:
        return {"error": f"Dependência ausente para estimativa de R²: {exc}"}

    if len(df) < 10:
        return {"error": "Amostra insuficiente para dividir em treino e teste."}

    try:
        sample_all = df.sample(n=min(n_amostra, len(df)), random_state=42).copy()
        sample_all["log_rem"] = np.log(sample_all["remuneracao_media"].clip(lower=100))
        sample_all["tempo_emprego_meses"] = pd.to_numeric(
            sample_all["tempo_emprego_meses"], errors="coerce"
        ).fillna(24)
        sample_all["idade"] = pd.to_numeric(sample_all["idade"], errors="coerce").fillna(32)
        sample_all["horas_contratuais"] = pd.to_numeric(
            sample_all["horas_contratuais"], errors="coerce"
        ).fillna(40)

        cat_feats = ["sexo", "nivel", "stem_area", "raca_cor", "uf", "escolaridade"]
        for col in cat_feats:
            sample_all[col] = sample_all[col].astype("category").cat.codes

        features = [
            "sexo",
            "nivel",
            "stem_area",
            "raca_cor",
            "uf",
            "escolaridade",
            "tempo_emprego_meses",
            "idade",
            "horas_contratuais",
        ]
        x_train, x_test, y_train, y_test = train_test_split(
            sample_all[features], sample_all["log_rem"], test_size=0.25, random_state=42
        )

        ols_all = sm.OLS(y_train, sm.add_constant(x_train, has_constant="add")).fit()
        y_pred_ols = ols_all.predict(sm.add_constant(x_test, has_constant="add"))
        r2_linear = r2_score(y_test, y_pred_ols)

        hgbr = HistGradientBoostingRegressor(max_iter=100, random_state=42)
        hgbr.fit(x_train, y_train)
        y_pred_gbt = hgbr.predict(x_test)
        r2_gbt = r2_score(y_test, y_pred_gbt)

        return {
            "r2_baseline_linear": round(float(r2_linear), 4),
            "r2_gradient_boosting": round(float(r2_gbt), 4),
            "faixa_meta_recomendada": "[0.55, 0.65]",
            "justificativa": (
                "Microdados salariais individuais possuem teto econométrico intrínseco "
                "(unobserved heterogeneity: soft skills, negociação, nicho técnico). "
                "R² acima de 0.70 na RAIS individual indica vazamento de dados (data leakage) ou overfitting."
            ),
        }
    except Exception as exc:
        return {"error": str(exc)}


def calcular_metricas_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """Calcula todas as métricas descritivas, gaps, small cells, Oaxaca-Blinder e R²."""
    res: dict[str, Any] = {}

    # 1. Estatísticas Globais
    rem = df["remuneracao_media"].dropna().to_numpy(dtype=float)
    q25 = float(np.percentile(rem, 25))
    q75 = float(np.percentile(rem, 75))
    iqr = q75 - q25

    res["global"] = {
        "total_vinculos": int(len(df)),
        "media": round(float(np.mean(rem)), 2),
        "mediana": round(float(np.median(rem)), 2),
        "std": round(float(np.std(rem, ddof=1)), 2) if len(rem) > 1 else 0.0,
        "p10": round(float(np.percentile(rem, 10)), 2),
        "p25": round(q25, 2),
        "p75": round(q75, 2),
        "p90": round(float(np.percentile(rem, 90)), 2),
        "p99": round(float(np.percentile(rem, 99)), 2),
        "min": round(float(np.min(rem)), 2),
        "max": round(float(np.max(rem)), 2),
        "iqr": round(iqr, 2),
    }

    rng = np.random.default_rng(42)
    sample_rem = rng.choice(rem, size=min(150000, len(rem)), replace=False)
    try:
        from scipy import stats

        res["global"]["assimetria"] = round(float(stats.skew(sample_rem)), 2)
        res["global"]["curtose"] = round(float(stats.kurtosis(sample_rem)), 2)
    except ImportError:
        serie_sample = pd.Series(sample_rem)
        res["global"]["assimetria"] = round(float(serie_sample.skew()), 2) if len(serie_sample) > 2 else 0.0
        res["global"]["curtose"] = round(float(serie_sample.kurt()), 2) if len(serie_sample) > 3 else 0.0

    # Outliers
    lim_sup = q75 + 1.5 * iqr
    n_outliers = int(np.sum(rem > lim_sup))
    res["outliers"] = {
        "limite_superior_iqr": round(lim_sup, 2),
        "n_outliers": n_outliers,
        "pct_outliers": round(n_outliers / len(rem) * 100, 2) if len(rem) > 0 else 0.0,
        "n_acima_50k": int(np.sum(rem > 50000)),
        "n_acima_100k": int(np.sum(rem > 100000)),
    }

    # 2. Distribuição por Sexo
    sex_dict: dict[str, Any] = {}
    for sexo in ["masculino", "feminino"]:
        sub_rem = df[df["sexo"] == sexo]["remuneracao_media"].dropna().to_numpy(dtype=float)
        if len(sub_rem) == 0:
            sex_dict[sexo] = {"n": 0, "pct": 0.0, "media": 0.0, "mediana": 0.0}
            continue
        sex_dict[sexo] = {
            "n": int(len(sub_rem)),
            "pct": round(len(sub_rem) / len(df) * 100, 2),
            "media": round(float(np.mean(sub_rem)), 2),
            "mediana": round(float(np.median(sub_rem)), 2),
            "std": round(float(np.std(sub_rem, ddof=1)), 2) if len(sub_rem) > 1 else 0.0,
            "p10": round(float(np.percentile(sub_rem, 10)), 2),
            "p25": round(float(np.percentile(sub_rem, 25)), 2),
            "p75": round(float(np.percentile(sub_rem, 75)), 2),
            "p90": round(float(np.percentile(sub_rem, 90)), 2),
            "iqr": round(float(np.percentile(sub_rem, 75) - np.percentile(sub_rem, 25)), 2),
        }

    med_m = sex_dict["masculino"]["mediana"]
    med_f = sex_dict["feminino"]["mediana"]
    mean_m = sex_dict["masculino"]["media"]
    mean_f = sex_dict["feminino"]["media"]

    sex_dict["gap_mediano_pct"] = round(((med_m - med_f) / med_m) * 100, 2) if med_m > 0 else 0.0
    sex_dict["gap_medio_pct"] = round(((mean_m - mean_f) / mean_m) * 100, 2) if mean_m > 0 else 0.0
    sex_dict["razao_paridade_mediana"] = round(med_f / med_m, 4) if med_m > 0 else 0.0
    sex_dict["razao_paridade_media"] = round(mean_f / mean_m, 4) if mean_m > 0 else 0.0
    res["sexo"] = sex_dict

    # 3. Por Nível Hierárquico e Sexo
    nivel_res: dict[str, Any] = {}
    for niv in ["gestao", "superior", "tecnico"]:
        sub = df[df["nivel"] == niv]
        m_vals = sub[sub["sexo"] == "masculino"]["remuneracao_media"].dropna().to_numpy(dtype=float)
        w_vals = sub[sub["sexo"] == "feminino"]["remuneracao_media"].dropna().to_numpy(dtype=float)

        med_m_n = float(np.median(m_vals)) if len(m_vals) > 0 else 0.0
        med_w_n = float(np.median(w_vals)) if len(w_vals) > 0 else 0.0
        mean_m_n = float(np.mean(m_vals)) if len(m_vals) > 0 else 0.0
        mean_w_n = float(np.mean(w_vals)) if len(w_vals) > 0 else 0.0

        nivel_res[niv] = {
            "total": int(len(sub)),
            "pct_do_total": round(len(sub) / len(df) * 100, 2) if len(df) > 0 else 0.0,
            "n_homens": int(len(m_vals)),
            "n_mulheres": int(len(w_vals)),
            "pct_mulheres": round(len(w_vals) / len(sub) * 100, 2) if len(sub) > 0 else 0.0,
            "mediana_homens": round(med_m_n, 2),
            "mediana_mulheres": round(med_w_n, 2),
            "media_homens": round(mean_m_n, 2),
            "media_mulheres": round(mean_w_n, 2),
            "p25_mulheres": round(float(np.percentile(w_vals, 25)), 2) if len(w_vals) > 0 else 0.0,
            "p75_mulheres": round(float(np.percentile(w_vals, 75)), 2) if len(w_vals) > 0 else 0.0,
            "gap_mediano_pct": round(((med_m_n - med_w_n) / med_m_n) * 100, 2) if med_m_n > 0 else 0.0,
            "gap_medio_pct": round(((mean_m_n - mean_w_n) / mean_m_n) * 100, 2) if mean_m_n > 0 else 0.0,
            "razao_paridade": round(med_w_n / med_m_n, 4) if med_m_n > 0 else 0.0,
        }
    res["nivel"] = nivel_res

    # 4. Por Área STEM
    area_res: dict[str, Any] = {}
    for area, sub in df.groupby("stem_area", observed=True):
        m_vals = sub[sub["sexo"] == "masculino"]["remuneracao_media"].dropna().to_numpy(dtype=float)
        w_vals = sub[sub["sexo"] == "feminino"]["remuneracao_media"].dropna().to_numpy(dtype=float)
        if len(m_vals) > 0 and len(w_vals) > 0:
            med_m_a = float(np.median(m_vals))
            med_w_a = float(np.median(w_vals))
            area_res[str(area)] = {
                "total": int(len(sub)),
                "pct_mulheres": round(len(w_vals) / len(sub) * 100, 2),
                "mediana_homens": round(med_m_a, 2),
                "mediana_mulheres": round(med_w_a, 2),
                "media_homens": round(float(np.mean(m_vals)), 2),
                "media_mulheres": round(float(np.mean(w_vals)), 2),
                "gap_mediano_pct": round(((med_m_a - med_w_a) / med_m_a) * 100, 2) if med_m_a > 0 else 0.0,
                "razao_paridade": round(med_w_a / med_m_a, 4) if med_m_a > 0 else 0.0,
            }
    res["stem_area"] = area_res

    # 5. Interseccionalidade: Sexo x Raça/Cor
    raca_res: dict[str, Any] = {}
    homem_branco_sub = df[(df["sexo"] == "masculino") & (df["raca_cor"] == "branca")][
        "remuneracao_media"
    ].dropna().to_numpy(dtype=float)
    homem_branco_med = float(np.median(homem_branco_sub)) if len(homem_branco_sub) > 0 else 0.0

    for (sexo_val, raca_val), sub in df.groupby(["sexo", "raca_cor"], observed=True):
        vals = sub["remuneracao_media"].dropna().to_numpy(dtype=float)
        if len(vals) > 0:
            med_sr = float(np.median(vals))
            mean_sr = float(np.mean(vals))
            raca_res[f"{sexo_val}_{raca_val}"] = {
                "n": int(len(vals)),
                "pct_total": round(len(vals) / len(df) * 100, 2),
                "mediana": round(med_sr, 2),
                "media": round(mean_sr, 2),
                "p25": round(float(np.percentile(vals, 25)), 2),
                "p75": round(float(np.percentile(vals, 75)), 2),
                "razao_vs_homem_branco": round(med_sr / homem_branco_med, 4) if homem_branco_med > 0 else 0.0,
            }
    res["interseccional"] = raca_res

    # 6. Distribuição por UF
    uf_res: dict[str, Any] = {}
    for uf_val, sub in df.groupby("uf", observed=True):
        m_vals = sub[sub["sexo"] == "masculino"]["remuneracao_media"].dropna().to_numpy(dtype=float)
        w_vals = sub[sub["sexo"] == "feminino"]["remuneracao_media"].dropna().to_numpy(dtype=float)
        if len(m_vals) > 0 and len(w_vals) > 0:
            med_m_u = float(np.median(m_vals))
            med_w_u = float(np.median(w_vals))
            uf_res[str(uf_val)] = {
                "total": int(len(sub)),
                "pct_mulheres": round(len(w_vals) / len(sub) * 100, 2),
                "mediana_homens": round(med_m_u, 2),
                "mediana_mulheres": round(med_w_u, 2),
                "gap_mediano_pct": round(((med_m_u - med_w_u) / med_m_u) * 100, 2) if med_m_u > 0 else 0.0,
            }
    res["uf"] = dict(sorted(uf_res.items(), key=lambda item: item[1]["total"], reverse=True))

    # 7. Análise de Small Cells (n < 10) para LGPD
    cells_cbo_uf_sex = df.groupby(["cbo_familia", "uf", "sexo"], observed=True).size()
    total_cells = int(len(cells_cbo_uf_sex))
    small_cells = int((cells_cbo_uf_sex < 10).sum())
    res["small_cells"] = {
        "cbo_uf_sexo": {
            "total_combinacoes_com_dados": total_cells,
            "n_menor_10": small_cells,
            "pct_menor_10": round(small_cells / total_cells * 100, 2) if total_cells > 0 else 0.0,
            "recomendacao_lgpd": "Obrigatoriedade de supressão diferencial ou agregação regional quando n < 10",
        }
    }

    # 8. Oaxaca-Blinder e 9. Meta de R²
    res["oaxaca_blinder_superior"] = calcular_oaxaca_blinder(df)
    res["proposta_meta_r2"] = calcular_meta_r2(df)

    return res


def processar_parquet(
    parquet_path: Path | str = PARQUET_PATH_PADRAO,
    output_json: Path | str = OUTPUT_JSON_PADRAO,
) -> dict[str, Any]:
    """Lê o parquet da RAIS STEM, calcula todas as métricas e grava o JSON em `reports/`."""
    caminho_parquet = Path(parquet_path)
    if not caminho_parquet.exists():
        raise FileNotFoundError(f"Arquivo parquet não encontrado: {caminho_parquet}")

    table = pq.read_table(caminho_parquet, columns=COLUNAS_NECESSARIAS)
    df = _preparar_colunas_categoricas(table.to_pandas())
    resultados = calcular_metricas_dataframe(df)

    caminho_saida = Path(output_json)
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho_saida, "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)

    return resultados


if __name__ == "__main__":
    print(f"Utilizando arquivo: {PARQUET_PATH_PADRAO}")
    resultados = processar_parquet()
    print(f"\n>>> Sucesso! Métricas extraídas e salvas em {OUTPUT_JSON_PADRAO}! <<<")
    print(f"Total vínculos processados: {resultados['global']['total_vinculos']:,}")
    print(f"Mediana Geral: R$ {resultados['global']['mediana']:.2f}")
    print(f"Gap Mediano Gestão: {resultados['nivel']['gestao']['gap_mediano_pct']}%")
    print(f"Gap Mediano Superior: {resultados['nivel']['superior']['gap_mediano_pct']}%")
    print(f"Gap Mediano Técnico: {resultados['nivel']['tecnico']['gap_mediano_pct']}%")
