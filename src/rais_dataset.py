"""Gera o dataset salarial STEM a partir dos microdados da RAIS Vínculos (issue agents #2).

Uso:
    uv run python -m src.rais_dataset --arquivo data/raw/rais/2025/RAIS_VINC_PUB_CENTRO_OESTE.COMT --ano 2025

Saídas (em data/processed/):
    rais_stem_<ano>_<regiao>.parquet   uma linha por vínculo, colunas padronizadas
    rais_stem_<ano>_<regiao>.json      quantas linhas cada filtro removeu (para o dicionário de dados)

Regras (decididas com o grupo em 12/11/2026):
- só ocupações STEM, listadas por família da CBO em config/stem_cbo.csv;
- só vínculos do setor privado (CLT, temporário, aprendiz, avulso, diretor);
- sem vínculos abandonados e sem remuneração média abaixo de 0,3 salário mínimo (erro de declaração);
- desligados no ano entram, marcados em ativo_31_12.
"""
import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STEM_CBO = ROOT / "config" / "stem_cbo.csv"
CBO_OCUPACAO = ROOT / "data" / "raw" / "cbo" / "cbo2002-ocupacao.csv"
CBO_FAMILIA = ROOT / "data" / "raw" / "cbo" / "cbo2002-familia.csv"
SAIDA = ROOT / "data" / "processed"
REMUNERACAO_MINIMA_SM = 0.3  # abaixo disso (~R$ 455 em 2025) o valor mensal é tratado como erro
HORAS_VALIDAS = (1, 60)      # 99 = não informado; 45-60 h são jornadas especiais válidas
ETAPAS = ["lidas", "apos_filtro_stem", "apos_filtro_setor_privado", "apos_tirar_abandonados",
          "apos_tirar_remuneracao_zero", "apos_tirar_remuneracao_abaixo_0_3_sm",
          "remuneracao_reais_e_sm_destrocadas"]

# Nome da coluna no arquivo da RAIS 2025 -> nome no dataset
COLUNAS = {
    "CBO 2002 Ocupação - Código": "cbo",
    "CNAE 2.0 Classe - Código": "cnae_classe",
    "Ind Vínculo Ativo 31/12 - Código": "ativo_31_12",
    "Ind Vínculo Abandonado - Código": "abandonado",
    "Tipo Vínculo - Código": "tipo_vinculo",
    "Escolaridade Após 2005 - Código": "escolaridade",
    "Qtd Hora Contr": "horas_contratuais",
    "Idade": "idade",
    "Tempo Emprego": "tempo_emprego_meses",
    "Município Trab - Código": "municipio_trabalho",
    "Município - Código": "municipio_estabelecimento",
    "Raça Cor - Código": "raca_cor",
    "Sexo - Código": "sexo",
    "Tamanho Estabelecimento - Código": "tamanho_estabelecimento",
    "Vl Rem Média Nom": "remuneracao_media",
    "Vl Rem Média (SM)": "remuneracao_media_sm",
}

TIPO_CONTRATO = {
    "10": "clt_indeterminado", "15": "clt_indeterminado", "20": "clt_indeterminado", "25": "clt_indeterminado",
    "60": "clt_determinado", "65": "clt_determinado", "70": "clt_determinado", "75": "clt_determinado",
    "40": "avulso", "50": "temporario", "55": "aprendiz", "80": "diretor",
}
SEXO = {"1": "masculino", "2": "feminino"}
RACA_COR = {"1": "indigena", "2": "branca", "4": "preta", "6": "amarela", "8": "parda", "9": "nao_identificado"}
ESCOLARIDADE = {
    "1": "analfabeto", "2": "fundamental_i_incompleto", "3": "fundamental_i_completo",
    "4": "fundamental_ii_incompleto", "5": "fundamental_completo", "6": "medio_incompleto",
    "7": "medio_completo", "8": "superior_incompleto", "9": "superior_completo",
    "10": "mestrado", "11": "doutorado",
}
UF = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE", "29": "BA",
    "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS",
    "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}


def numero(serie):
    """Texto da RAIS ('1234.56', '.00', ' ', '1.234,56') -> float."""
    texto = serie.astype("string").str.strip()
    com_virgula = texto.str.contains(",", na=False)
    texto = texto.where(~com_virgula, texto.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(texto, errors="coerce")


def codigo(serie, digitos):
    """Código numérico como texto com zeros à esquerda (a RAIS perde o zero: 21210 -> 021210)."""
    texto = serie.astype("string").str.strip().str.split(".").str[0]
    return texto.where(texto.str.fullmatch(r"\d+", na=False)).str.zfill(digitos)


def carregar_stem(caminho=STEM_CBO):
    return pd.read_csv(caminho, dtype=str).set_index("familia")


def nomes_cbo():
    ocupacoes = pd.read_csv(CBO_OCUPACAO, sep=";", encoding="latin-1", dtype=str)
    familias = pd.read_csv(CBO_FAMILIA, sep=";", encoding="latin-1", dtype=str)
    return (dict(zip(ocupacoes["CODIGO"].str.zfill(6), ocupacoes["TITULO"].str.strip())),
            dict(zip(familias["CODIGO"].str.zfill(4), familias["TITULO"].str.strip())))


def tratar_bloco(bloco, stem, ano, regiao, contagem, nomes_ocupacao=None, nomes_familia=None):
    """Aplica filtros e padronização a um pedaço do arquivo; atualiza `contagem` (linhas por etapa)."""
    df = bloco.rename(columns=COLUNAS)[list(COLUNAS.values())]
    contagem["lidas"] += len(df)

    df["cbo"] = codigo(df["cbo"], 6)
    df["cbo_familia"] = df["cbo"].str[:4]
    df = df[df["cbo_familia"].isin(stem.index)]
    contagem["apos_filtro_stem"] += len(df)

    df["tipo_vinculo"] = df["tipo_vinculo"].astype("string").str.strip()
    df = df[df["tipo_vinculo"].isin(TIPO_CONTRATO.keys())]
    contagem["apos_filtro_setor_privado"] += len(df)

    df = df[df["abandonado"].astype("string").str.strip() != "1"]
    contagem["apos_tirar_abandonados"] += len(df)

    df["remuneracao_media"] = numero(df["remuneracao_media"])
    df["remuneracao_media_sm"] = numero(df["remuneracao_media_sm"])
    # Em alguns registros a RAIS troca as colunas (R$ 31 e 47.078 SM). É troca quando a conta inversa
    # bate com o salário mínimo do ano (47.078 / 31 ≈ 1.518): aí destrocamos em vez de excluir.
    reais, sm = df["remuneracao_media"], df["remuneracao_media_sm"]
    normais = (reais > sm) & (sm > 0)
    salario_minimo = (reais[normais] / sm[normais]).median() if normais.any() else float("nan")
    trocado = (reais > 0) & (sm > reais) & ((sm / reais) / salario_minimo).between(0.95, 1.05)
    df.loc[trocado, ["remuneracao_media", "remuneracao_media_sm"]] = (
        df.loc[trocado, ["remuneracao_media_sm", "remuneracao_media"]].to_numpy())
    contagem["remuneracao_reais_e_sm_destrocadas"] += int(trocado.sum())

    df = df[df["remuneracao_media"] > 0]
    contagem["apos_tirar_remuneracao_zero"] += len(df)

    df = df[df["remuneracao_media_sm"] >= REMUNERACAO_MINIMA_SM]
    contagem["apos_tirar_remuneracao_abaixo_0_3_sm"] += len(df)

    municipio = codigo(df["municipio_trabalho"], 6)
    municipio = municipio.where(~municipio.isin(["999999", "999997"]), codigo(df["municipio_estabelecimento"], 6))
    saida = pd.DataFrame({
        "ano": ano,
        "regiao_arquivo": regiao,
        "uf": municipio.str[:2].map(UF),
        "municipio": municipio,
        "cbo": df["cbo"],
        "cbo_familia": df["cbo_familia"],
        "cbo_nome": df["cbo"].map(nomes_ocupacao or {}),
        "cbo_familia_nome": df["cbo_familia"].map(nomes_familia or {}),
        "stem_area": df["cbo_familia"].map(stem["area"]),
        "nivel": df["cbo_familia"].map(stem["nivel"]),
        "cnae_classe": codigo(df["cnae_classe"], 5),
        "tipo_vinculo": df["tipo_vinculo"],
        "tipo_contrato": df["tipo_vinculo"].map(TIPO_CONTRATO),
        "ativo_31_12": df["ativo_31_12"].astype("string").str.strip() == "1",
        "sexo": df["sexo"].astype("string").str.strip().map(SEXO),
        "raca_cor": df["raca_cor"].astype("string").str.strip().map(RACA_COR),
        "escolaridade_codigo": pd.to_numeric(df["escolaridade"], errors="coerce").where(lambda s: s.between(1, 11)),
        "escolaridade": df["escolaridade"].astype("string").str.strip().map(ESCOLARIDADE),
        "idade": numero(df["idade"]).where(lambda s: s.between(14, 100)),
        "tempo_emprego_meses": numero(df["tempo_emprego_meses"]),
        "horas_contratuais": numero(df["horas_contratuais"]).where(lambda s: s.between(*HORAS_VALIDAS)),
        "tamanho_estabelecimento": codigo(df["tamanho_estabelecimento"], 2),
        "remuneracao_media": df["remuneracao_media"],
        "remuneracao_media_sm": df["remuneracao_media_sm"],
    })
    return saida


def construir(arquivo, ano, saida_dir=SAIDA, tamanho_bloco=500_000):
    arquivo = Path(arquivo)
    regiao = arquivo.stem.replace("RAIS_VINC_PUB_", "").lower()
    stem = carregar_stem()
    nomes_ocupacao, nomes_familia = nomes_cbo()
    contagem = dict.fromkeys(ETAPAS, 0)
    leitor = pd.read_csv(arquivo, sep=",", encoding="latin-1", dtype=str, usecols=list(COLUNAS),
                         chunksize=tamanho_bloco)
    partes = [tratar_bloco(b, stem, ano, regiao, contagem, nomes_ocupacao, nomes_familia) for b in leitor]
    dataset = pd.concat(partes, ignore_index=True)

    saida_dir = Path(saida_dir)
    saida_dir.mkdir(parents=True, exist_ok=True)
    destino = saida_dir / f"rais_stem_{ano}_{regiao}.parquet"
    dataset.to_parquet(destino, index=False)
    relatorio = {
        "arquivo": arquivo.name, "ano": ano, "regiao": regiao, "linhas_por_etapa": contagem,
        "linhas_finais": len(dataset),
        "faltantes_por_coluna": {c: int(n) for c, n in dataset.isna().sum().items() if n},
        "por_sexo": dataset["sexo"].value_counts(dropna=False).to_dict(),
        "por_nivel": dataset["nivel"].value_counts(dropna=False).to_dict(),
    }
    destino.with_suffix(".json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino, relatorio


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arquivo", required=True, type=Path)
    parser.add_argument("--ano", required=True, type=int)
    args = parser.parse_args()
    destino, relatorio = construir(ROOT / args.arquivo, args.ano)
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    print(f"Dataset em {destino}")


if __name__ == "__main__":
    main()
