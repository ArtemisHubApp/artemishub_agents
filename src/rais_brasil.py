"""Junta os datasets por região (src.rais_dataset) num dataset único do Brasil.

Uso:
    uv run python -m src.rais_brasil --ano 2025

Saídas (em data/processed/):
    rais_stem_<ano>_brasil.parquet   todas as regiões juntas
    rais_stem_<ano>_brasil.json      funil de filtros somado + resumo por UF, sexo e nível
"""
import argparse
import json
from pathlib import Path

import pandas as pd

from src.rais_dataset import ETAPAS, SAIDA

REGIOES = ["norte", "nordeste", "centro_oeste", "mg_es_rj", "sp", "sul"]


def juntar(ano, pasta=SAIDA, regioes=REGIOES):
    pasta = Path(pasta)
    faltando = [r for r in regioes if not (pasta / f"rais_stem_{ano}_{r}.parquet").exists()]
    if faltando:
        raise FileNotFoundError(f"Faltam as regiões: {', '.join(faltando)}. Rode src.rais_dataset para elas.")

    dataset = pd.concat([pd.read_parquet(pasta / f"rais_stem_{ano}_{r}.parquet") for r in regioes], ignore_index=True)
    funil = dict.fromkeys(ETAPAS, 0)
    for r in regioes:
        relatorio = json.loads((pasta / f"rais_stem_{ano}_{r}.json").read_text(encoding="utf-8"))
        for etapa, n in relatorio["linhas_por_etapa"].items():
            funil[etapa] = funil.get(etapa, 0) + n

    destino = pasta / f"rais_stem_{ano}_brasil.parquet"
    dataset.to_parquet(destino, index=False)
    mediana = dataset.pivot_table(index="nivel", columns="sexo", values="remuneracao_media", aggfunc="median")
    resumo = {
        "ano": ano,
        "regioes": regioes,
        "linhas_por_etapa": funil,
        "linhas_finais": len(dataset),
        "ufs": int(dataset["uf"].nunique()),
        "sem_uf": int(dataset["uf"].isna().sum()),
        "por_sexo": dataset["sexo"].value_counts(dropna=False).to_dict(),
        "por_nivel": dataset["nivel"].value_counts(dropna=False).to_dict(),
        "por_uf": dataset["uf"].value_counts(dropna=False).to_dict(),
        "mediana_remuneracao_por_nivel_e_sexo": mediana.round(2).to_dict(orient="index"),
    }
    destino.with_suffix(".json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino, resumo


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ano", required=True, type=int)
    args = parser.parse_args()
    destino, resumo = juntar(args.ano)
    print(json.dumps({k: v for k, v in resumo.items() if k != "por_uf"}, ensure_ascii=False, indent=2))
    print(f"Dataset em {destino}")


if __name__ == "__main__":
    main()
