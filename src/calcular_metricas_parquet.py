#!/usr/bin/env python3
"""
Script de processamento estatístico otimizado da base RAIS STEM 2025.
Lê o arquivo parquet com as colunas exatas da base de Ana Julia (PR #19).
Gera o arquivo json com todas as métricas exatas para a EDA, relatórios e notebook.
"""

import os
import json
import numpy as np
import pyarrow.parquet as pq
import pandas as pd
from scipy import stats
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score
import statsmodels.api as sm

PARQUET_PATH = "data/processed/rais_stem_2025_brasil.parquet"
if not os.path.exists(PARQUET_PATH):
    PARQUET_PATH = "/home/eduardairineu/EDArtemis/rais_stem_2025_brasil.parquet"

print(f"Utilizando arquivo: {PARQUET_PATH}")

needed_cols = [
    'remuneracao_media', 'remuneracao_media_sm', 'sexo', 'nivel', 'stem_area', 
    'raca_cor', 'cbo_familia', 'uf', 'tempo_emprego_meses', 'idade', 
    'horas_contratuais', 'escolaridade'
]

print("Lendo colunas selecionadas via pyarrow...")
table = pq.read_table(PARQUET_PATH, columns=needed_cols)
print(f"Tabela carregada com sucesso: {table.num_rows:,} linhas e {table.num_columns} colunas.")

df = table.to_pandas()
cat_cols = ['sexo', 'nivel', 'stem_area', 'raca_cor', 'cbo_familia', 'uf', 'escolaridade']
for c in cat_cols:
    if c in df.columns:
        df[c] = df[c].astype('category')

print(f"Uso de memória otimizado: {df.memory_usage(deep=True).sum() / 1e6:.1f} MB")

res = {}

# 1. Estatísticas Globais
rem = df['remuneracao_media'].dropna().values
res['global'] = {
    'total_vinculos': int(len(df)),
    'media': round(float(np.mean(rem)), 2),
    'mediana': round(float(np.median(rem)), 2),
    'std': round(float(np.std(rem, ddof=1)), 2),
    'p10': round(float(np.percentile(rem, 10)), 2),
    'p25': round(float(np.percentile(rem, 25)), 2),
    'p75': round(float(np.percentile(rem, 75)), 2),
    'p90': round(float(np.percentile(rem, 90)), 2),
    'p99': round(float(np.percentile(rem, 99)), 2),
    'min': round(float(np.min(rem)), 2),
    'max': round(float(np.max(rem)), 2),
    'iqr': round(float(np.percentile(rem, 75) - np.percentile(rem, 25)), 2)
}

# Assimetria e Curtose (amostra de 150k)
sample_rem = np.random.choice(rem, size=min(150000, len(rem)), replace=False)
res['global']['assimetria'] = round(float(stats.skew(sample_rem)), 2)
res['global']['curtose'] = round(float(stats.kurtosis(sample_rem)), 2)

# Outliers
q25 = res['global']['p25']
q75 = res['global']['p75']
iqr = res['global']['iqr']
lim_sup = q75 + 1.5 * iqr
n_outliers = int(np.sum(rem > lim_sup))
res['outliers'] = {
    'limite_superior_iqr': round(lim_sup, 2),
    'n_outliers': n_outliers,
    'pct_outliers': round(n_outliers / len(rem) * 100, 2),
    'n_acima_50k': int(np.sum(rem > 50000)),
    'n_acima_100k': int(np.sum(rem > 100000))
}

# 2. Distribuição por Sexo
sex_dict = {}
for s in ['masculino', 'feminino']:
    sub_rem = df[df['sexo'] == s]['remuneracao_media'].dropna().values
    sex_dict[s] = {
        'n': int(len(sub_rem)),
        'pct': round(len(sub_rem) / len(df) * 100, 2),
        'media': round(float(np.mean(sub_rem)), 2),
        'mediana': round(float(np.median(sub_rem)), 2),
        'std': round(float(np.std(sub_rem, ddof=1)), 2),
        'p10': round(float(np.percentile(sub_rem, 10)), 2),
        'p25': round(float(np.percentile(sub_rem, 25)), 2),
        'p75': round(float(np.percentile(sub_rem, 75)), 2),
        'p90': round(float(np.percentile(sub_rem, 90)), 2),
        'iqr': round(float(np.percentile(sub_rem, 75) - np.percentile(sub_rem, 25)), 2)
    }

med_m = sex_dict['masculino']['mediana']
med_f = sex_dict['feminino']['mediana']
mean_m = sex_dict['masculino']['media']
mean_f = sex_dict['feminino']['media']

sex_dict['gap_mediano_pct'] = round(((med_m - med_f) / med_m) * 100, 2)
sex_dict['gap_medio_pct'] = round(((mean_m - mean_f) / mean_m) * 100, 2)
sex_dict['razao_paridade_mediana'] = round(med_f / med_m, 4)
sex_dict['razao_paridade_media'] = round(mean_f / mean_m, 4)
res['sexo'] = sex_dict

# 3. Por Nível Hierárquico e Sexo
nivel_res = {}
for niv in ['gestao', 'superior', 'tecnico']:
    sub = df[df['nivel'] == niv]
    m_vals = sub[sub['sexo'] == 'masculino']['remuneracao_media'].dropna().values
    w_vals = sub[sub['sexo'] == 'feminino']['remuneracao_media'].dropna().values
    
    med_m_n = float(np.median(m_vals)) if len(m_vals) > 0 else 0
    med_w_n = float(np.median(w_vals)) if len(w_vals) > 0 else 0
    mean_m_n = float(np.mean(m_vals)) if len(m_vals) > 0 else 0
    mean_w_n = float(np.mean(w_vals)) if len(w_vals) > 0 else 0
    
    nivel_res[niv] = {
        'total': int(len(sub)),
        'pct_do_total': round(len(sub) / len(df) * 100, 2),
        'n_homens': int(len(m_vals)),
        'n_mulheres': int(len(w_vals)),
        'pct_mulheres': round(len(w_vals) / len(sub) * 100, 2),
        'mediana_homens': round(med_m_n, 2),
        'mediana_mulheres': round(med_w_n, 2),
        'media_homens': round(mean_m_n, 2),
        'media_mulheres': round(mean_w_n, 2),
        'p25_mulheres': round(float(np.percentile(w_vals, 25)), 2) if len(w_vals) > 0 else 0,
        'p75_mulheres': round(float(np.percentile(w_vals, 75)), 2) if len(w_vals) > 0 else 0,
        'gap_mediano_pct': round(((med_m_n - med_w_n) / med_m_n) * 100, 2) if med_m_n > 0 else 0,
        'gap_medio_pct': round(((mean_m_n - mean_w_n) / mean_m_n) * 100, 2) if mean_m_n > 0 else 0,
        'razao_paridade': round(med_w_n / med_m_n, 4) if med_m_n > 0 else 0
    }
res['nivel'] = nivel_res

# 4. Por Área STEM
area_res = {}
for area, sub in df.groupby('stem_area', observed=True):
    m_vals = sub[sub['sexo'] == 'masculino']['remuneracao_media'].dropna().values
    w_vals = sub[sub['sexo'] == 'feminino']['remuneracao_media'].dropna().values
    if len(m_vals) > 0 and len(w_vals) > 0:
        med_m_a = float(np.median(m_vals))
        med_w_a = float(np.median(w_vals))
        area_res[str(area)] = {
            'total': int(len(sub)),
            'pct_mulheres': round(len(w_vals) / len(sub) * 100, 2),
            'mediana_homens': round(med_m_a, 2),
            'mediana_mulheres': round(med_w_a, 2),
            'media_homens': round(float(np.mean(m_vals)), 2),
            'media_mulheres': round(float(np.mean(w_vals)), 2),
            'gap_mediano_pct': round(((med_m_a - med_w_a) / med_m_a) * 100, 2),
            'razao_paridade': round(med_w_a / med_m_a, 4)
        }
res['stem_area'] = area_res

# 5. Interseccionalidade: Sexo x Raça/Cor
raca_res = {}
homem_branco_sub = df[(df['sexo'] == 'masculino') & (df['raca_cor'] == 'branca')]['remuneracao_media'].dropna().values
homem_branco_med = float(np.median(homem_branco_sub))

for (s, r), sub in df.groupby(['sexo', 'raca_cor'], observed=True):
    vals = sub['remuneracao_media'].dropna().values
    if len(vals) > 0:
        med_sr = float(np.median(vals))
        mean_sr = float(np.mean(vals))
        raca_res[f"{s}_{r}"] = {
            'n': int(len(vals)),
            'pct_total': round(len(vals) / len(df) * 100, 2),
            'mediana': round(med_sr, 2),
            'media': round(mean_sr, 2),
            'p25': round(float(np.percentile(vals, 25)), 2),
            'p75': round(float(np.percentile(vals, 75)), 2),
            'razao_vs_homem_branco': round(med_sr / homem_branco_med, 4)
        }
res['interseccional'] = raca_res

# 6. Distribuição por UF (Top 10 UFs)
uf_res = {}
for uf, sub in df.groupby('uf', observed=True):
    m_vals = sub[sub['sexo'] == 'masculino']['remuneracao_media'].dropna().values
    w_vals = sub[sub['sexo'] == 'feminino']['remuneracao_media'].dropna().values
    if len(m_vals) > 0 and len(w_vals) > 0:
        med_m_u = float(np.median(m_vals))
        med_w_u = float(np.median(w_vals))
        uf_res[str(uf)] = {
            'total': int(len(sub)),
            'pct_mulheres': round(len(w_vals) / len(sub) * 100, 2),
            'mediana_homens': round(med_m_u, 2),
            'mediana_mulheres': round(med_w_u, 2),
            'gap_mediano_pct': round(((med_m_u - med_w_u) / med_m_u) * 100, 2)
        }
res['uf'] = dict(sorted(uf_res.items(), key=lambda x: x[1]['total'], reverse=True))

# 7. Análise de Small Cells (n < 10) para LGPD e Privacidade Diferencial
cells_cbo_uf_sex = df.groupby(['cbo_familia', 'uf', 'sexo'], observed=True).size()
total_cells = int(len(cells_cbo_uf_sex))
small_cells = int((cells_cbo_uf_sex < 10).sum())
res['small_cells'] = {
    'cbo_uf_sexo': {
        'total_combinacoes_com_dados': total_cells,
        'n_menor_10': small_cells,
        'pct_menor_10': round(small_cells / total_cells * 100, 2),
        'recomendacao_lgpd': 'Obrigatoriedade de supressão diferencial ou agregação regional quando n < 10'
    }
}

# 8. Decomposição de Oaxaca-Blinder (Amostra estratificada do Nível Superior)
print("Executando Oaxaca-Blinder no Nível Superior...")
sub_sup = df[df['nivel'] == 'superior'].copy()
sample_sup = sub_sup.sample(n=min(60000, len(sub_sup)), random_state=42)

sample_sup['log_rem'] = np.log(sample_sup['remuneracao_media'].clip(lower=100))
sample_sup['tempo_emprego_meses'] = pd.to_numeric(sample_sup['tempo_emprego_meses'], errors='coerce').fillna(24)
sample_sup['idade'] = pd.to_numeric(sample_sup['idade'], errors='coerce').fillna(32)
sample_sup['horas_contratuais'] = pd.to_numeric(sample_sup['horas_contratuais'], errors='coerce').fillna(40)

X_sup = pd.get_dummies(sample_sup[['stem_area', 'uf']], drop_first=True, dtype=float)
X_sup['tempo_emprego_meses'] = sample_sup['tempo_emprego_meses']
X_sup['idade'] = sample_sup['idade']
X_sup['horas_contratuais'] = sample_sup['horas_contratuais']
X_sup['const'] = 1.0

y_sup = sample_sup['log_rem']
is_m = (sample_sup['sexo'] == 'masculino')
is_f = (sample_sup['sexo'] == 'feminino')

try:
    model_m = sm.OLS(y_sup[is_m], X_sup[is_m]).fit()
    model_f = sm.OLS(y_sup[is_f], X_sup[is_f]).fit()

    mean_X_m = X_sup[is_m].mean()
    mean_X_f = X_sup[is_f].mean()

    raw_log_gap = float(y_sup[is_m].mean() - y_sup[is_f].mean())
    explained = float(np.dot(mean_X_m - mean_X_f, model_m.params))
    unexplained = float(np.dot(mean_X_f, model_m.params - model_f.params))

    pct_explained = round((explained / raw_log_gap) * 100, 2)
    pct_unexplained = round((unexplained / raw_log_gap) * 100, 2)
    unexplained_wage_gap_pct = round((np.exp(unexplained) - 1.0) * 100, 2)

    res['oaxaca_blinder_superior'] = {
        'n_amostra': int(len(sample_sup)),
        'gap_total_log': round(raw_log_gap, 4),
        'gap_bruto_pct_equivalente': round((np.exp(raw_log_gap) - 1.0) * 100, 2),
        'parcela_explicada_dotacoes_pct': pct_explained,
        'parcela_inexplicada_discriminacao_pct': pct_unexplained,
        'gap_salario_liquido_discriminacao_pct': unexplained_wage_gap_pct,
        'r2_modelo_masculino': round(float(model_m.rsquared), 4),
        'r2_modelo_feminino': round(float(model_f.rsquared), 4)
    }
except Exception as e:
    res['oaxaca_blinder_superior'] = {'error': str(e)}

# 9. Estimativa de R² para Issue #4 / PDR 10.1
print("Calculando R² baseline e Gradient Boosting...")
try:
    sample_all = df.sample(n=min(80000, len(df)), random_state=42).copy()
    sample_all['log_rem'] = np.log(sample_all['remuneracao_media'].clip(lower=100))
    sample_all['tempo_emprego_meses'] = pd.to_numeric(sample_all['tempo_emprego_meses'], errors='coerce').fillna(24)
    sample_all['idade'] = pd.to_numeric(sample_all['idade'], errors='coerce').fillna(32)
    sample_all['horas_contratuais'] = pd.to_numeric(sample_all['horas_contratuais'], errors='coerce').fillna(40)

    cat_feats = ['sexo', 'nivel', 'stem_area', 'raca_cor', 'uf', 'escolaridade']
    for c in cat_feats:
        sample_all[c] = sample_all[c].astype('category').cat.codes

    features = ['sexo', 'nivel', 'stem_area', 'raca_cor', 'uf', 'escolaridade', 'tempo_emprego_meses', 'idade', 'horas_contratuais']
    X_train, X_test, y_train, y_test = train_test_split(
        sample_all[features], sample_all['log_rem'], test_size=0.25, random_state=42
    )

    ols_all = sm.OLS(y_train, sm.add_constant(X_train)).fit()
    y_pred_ols = ols_all.predict(sm.add_constant(X_test))
    r2_linear = r2_score(y_test, y_pred_ols)

    hgbr = HistGradientBoostingRegressor(max_iter=100, random_state=42)
    hgbr.fit(X_train, y_train)
    y_pred_gbt = hgbr.predict(X_test)
    r2_gbt = r2_score(y_test, y_pred_gbt)

    res['proposta_meta_r2'] = {
        'r2_baseline_linear': round(float(r2_linear), 4),
        'r2_gradient_boosting': round(float(r2_gbt), 4),
        'faixa_meta_recomendada': '[0.55, 0.65]',
        'justificativa': 'Microdados salariais individuais possuem teto econométrico intrínseco (unobserved heterogeneity: soft skills, negociação, nicho técnico). R² acima de 0.70 na RAIS individual indica vazamento de dados (data leakage) ou overfitting.'
    }
except Exception as e:
    res['proposta_meta_r2'] = {'error': str(e)}

output_json = "reports_eda_real.json"
with open(output_json, "w", encoding="utf-8") as f:
    json.dump(res, f, indent=2, ensure_ascii=False)

print(f"\n>>> Sucesso! Todas as métricas extraídas e salvas em {output_json}! <<<")
print(f"Total vínculos processados: {res['global']['total_vinculos']:,}")
print(f"Mediana Geral: R$ {res['global']['mediana']:.2f}")
print(f"Gap Mediano Gestão: {res['nivel']['gestao']['gap_mediano_pct']}%")
print(f"Gap Mediano Superior: {res['nivel']['superior']['gap_mediano_pct']}%")
print(f"Gap Mediano Técnico: {res['nivel']['tecnico']['gap_mediano_pct']}%")
