"""Ferramenta de consulta salarial do agente de Análise (cronograma, tarefa 9).

Funciona em dois passos:

1. `gerar` agrega o parquet da RAIS em duas tabelas pequenas, versionadas no git, para que os agentes
   não dependam do arquivo de 50 MB:
       data/agregados/salarios_rais_<ano>.csv   percentis por família da CBO × UF × sexo
       data/agregados/ocupacoes_cbo.csv          ocupações (CBO de 6 dígitos) e suas famílias
2. `consultar` e `buscar_ocupacao` leem essas tabelas e devolvem números prontos para o agente explicar.
   O LLM nunca calcula valores: só repete e interpreta o que sai daqui.

Uso:
    uv run python -m src.salarios gerar --ano 2025
    uv run python -m src.salarios consultar --ocupacao "analista de sistemas" --uf DF --salario 7500
"""
import argparse
import json
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PARQUET = ROOT / "data" / "processed" / "rais_stem_{ano}_brasil.parquet"
AGREGADOS = ROOT / "data" / "agregados"
TABELA = AGREGADOS / "salarios_rais_{ano}.csv"
OCUPACOES = AGREGADOS / "ocupacoes_cbo.csv"

N_MINIMO = 30          # recortes com menos vínculos não são publicados
HORAS_INTEGRAL = 40    # jornada semanal mínima para entrar no recorte "tempo integral"
BRASIL = "BR"
TODOS = "todos"
SEXOS = ("feminino", "masculino", TODOS)
FONTE = "RAIS Vínculos {ano} (MTE/PDET), setor privado, ocupações STEM"
PALAVRAS_VAZIAS = {"de", "da", "do", "das", "dos", "e", "em", "a", "o"}


def _estatisticas(grupo):
    rem = grupo["remuneracao_media"]
    integral = rem[grupo["horas_contratuais"] >= HORAS_INTEGRAL]
    return pd.Series({
        "n": len(rem),
        "p25": rem.quantile(0.25),
        "p50": rem.quantile(0.50),
        "p75": rem.quantile(0.75),
        "n_integral": len(integral),
        "p50_integral": integral.median() if len(integral) else float("nan"),
    })


def agregar(dados, ano, n_minimo=N_MINIMO):
    """Percentis da remuneração média mensal por família da CBO × UF × sexo.

    Inclui as linhas de total (uf = "BR" e sexo = "todos") e descarta recortes com menos de `n_minimo`
    vínculos, que dariam números instáveis e poderiam expor pouquíssimas pessoas.
    """
    base = dados[dados["sexo"].notna()]
    partes = []
    for uf_total in (False, True):
        for sexo_total in (False, True):
            df = base.assign(
                uf=BRASIL if uf_total else base["uf"],
                sexo=TODOS if sexo_total else base["sexo"],
            )
            partes.append(df.groupby(["cbo_familia", "uf", "sexo"])[["remuneracao_media", "horas_contratuais"]]
                          .apply(_estatisticas))
    tabela = pd.concat(partes).reset_index()
    tabela = tabela[tabela["n"] >= n_minimo].copy()
    tabela.loc[tabela["n_integral"] < n_minimo, "p50_integral"] = float("nan")
    nomes = base.drop_duplicates("cbo_familia").set_index("cbo_familia")["cbo_familia_nome"]
    tabela.insert(1, "cbo_familia_nome", tabela["cbo_familia"].map(nomes))
    tabela.insert(0, "ano", ano)
    for coluna in ("n", "n_integral"):
        tabela[coluna] = tabela[coluna].astype(int)
    return tabela.round(2).sort_values(["cbo_familia", "uf", "sexo"]).reset_index(drop=True)


def listar_ocupacoes(dados):
    """Ocupações de 6 dígitos com nome oficial, para achar a família a partir do que a usuária escreve."""
    ocupacoes = (dados.dropna(subset=["cbo_nome"])
                 .groupby(["cbo", "cbo_nome", "cbo_familia", "cbo_familia_nome"]).size()
                 .rename("n").reset_index())
    return ocupacoes.sort_values("n", ascending=False).reset_index(drop=True)


def gerar(ano, parquet=None, destino=AGREGADOS, n_minimo=N_MINIMO):
    parquet = Path(parquet or str(PARQUET).format(ano=ano))
    colunas = ["cbo", "cbo_nome", "cbo_familia", "cbo_familia_nome", "uf", "sexo",
               "remuneracao_media", "horas_contratuais"]
    dados = pd.read_parquet(parquet, columns=colunas)
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    tabela = agregar(dados, ano, n_minimo)
    ocupacoes = listar_ocupacoes(dados)
    caminho_tabela = destino / f"salarios_rais_{ano}.csv"
    tabela.to_csv(caminho_tabela, index=False)
    ocupacoes.to_csv(destino / "ocupacoes_cbo.csv", index=False)
    return caminho_tabela, len(tabela), len(ocupacoes)


def carregar_tabela(ano=2025, caminho=None):
    return pd.read_csv(caminho or str(TABELA).format(ano=ano), dtype={"cbo_familia": str})


def carregar_ocupacoes(caminho=OCUPACOES):
    return pd.read_csv(caminho, dtype={"cbo": str, "cbo_familia": str})


def _normalizar(texto):
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return sem_acento.lower()


def buscar_ocupacao(termo, ocupacoes=None, limite=5):
    """Ocupações cujo nome contém as palavras do termo (sem acento e sem diferenciar maiúsculas).

    Ordena pelo número de palavras encontradas e, no empate, pelas ocupações com mais vínculos.
    """
    ocupacoes = carregar_ocupacoes() if ocupacoes is None else ocupacoes
    palavras = [p for p in _normalizar(termo).split() if p not in PALAVRAS_VAZIAS]
    if not palavras:
        return []
    nomes = ocupacoes["cbo_nome"].map(_normalizar)
    acertos = sum(nomes.str.contains(p, regex=False).astype(int) for p in palavras)
    achadas = ocupacoes.assign(acertos=acertos)
    achadas = achadas[achadas["acertos"] > 0].sort_values(["acertos", "n"], ascending=False)
    return achadas.head(limite)[["cbo", "cbo_nome", "cbo_familia", "cbo_familia_nome"]].to_dict("records")


def _recorte(tabela, familia, uf):
    linhas = tabela[(tabela["cbo_familia"] == familia) & (tabela["uf"] == uf)]
    return {linha["sexo"]: linha for _, linha in linhas.iterrows()}


def _numeros(linha):
    p50_integral = linha["p50_integral"]
    return {
        "n": int(linha["n"]),
        "p25": float(linha["p25"]),
        "p50": float(linha["p50"]),
        "p75": float(linha["p75"]),
        "p50_tempo_integral": None if pd.isna(p50_integral) else float(p50_integral),
    }


def _diferenca_pct(valor, referencia):
    return round((valor - referencia) / referencia * 100, 1)


def consultar(cbo_familia, uf, salario=None, tabela=None, ano=2025):
    """Números da família da CBO na UF, por sexo, com avisos para o agente repassar à usuária.

    Se a UF não tiver vínculos suficientes de mulheres e de homens, usa o Brasil todo e avisa.
    """
    tabela = carregar_tabela(ano) if tabela is None else tabela
    cbo_familia, uf = str(cbo_familia), str(uf).upper()
    avisos = [
        "Só inclui emprego formal do setor privado (CLT e afins); PJ, autônomas e servidoras ficam de fora.",
        "Valores são a remuneração média mensal de 2025, em reais nominais.",
    ]

    recorte_uf = _recorte(tabela, cbo_familia, uf)
    uf_usada = uf
    if not {"feminino", "masculino"} <= recorte_uf.keys():
        recorte_br = _recorte(tabela, cbo_familia, BRASIL)
        if recorte_br:
            avisos.append(f"Não há vínculos suficientes de mulheres e de homens em {uf} "
                          f"(mínimo de {N_MINIMO} cada); os números são do Brasil todo.")
            recorte_uf, uf_usada = recorte_br, BRASIL

    nome = next((linha["cbo_familia_nome"] for linha in recorte_uf.values()), None)
    resultado = {
        "cbo_familia": cbo_familia,
        "cbo_familia_nome": nome,
        "uf_pedida": uf,
        "uf_usada": uf_usada if recorte_uf else None,
        "ano": ano,
        "fonte": FONTE.format(ano=ano),
        "suficiente": bool(recorte_uf),
        "por_sexo": {sexo: _numeros(recorte_uf[sexo]) for sexo in SEXOS if sexo in recorte_uf},
        "diferenca_bruta_mediana_pct": None,
        "salario_informado": None,
        "avisos": avisos,
    }
    if not recorte_uf:
        avisos.append(f"Não há vínculos suficientes para a família {cbo_familia} nem no Brasil todo.")
        return resultado

    por_sexo = resultado["por_sexo"]
    if {"feminino", "masculino"} <= por_sexo.keys():
        # quanto a mediana das mulheres fica abaixo da dos homens, em % da mediana dos homens
        resultado["diferenca_bruta_mediana_pct"] = -_diferenca_pct(por_sexo["feminino"]["p50"],
                                                                   por_sexo["masculino"]["p50"])
        avisos.append("A diferença entre mulheres e homens é bruta: compara medianas sem controlar "
                      "escolaridade, tempo de casa, porte da empresa ou jornada. Não prova discriminação "
                      "individual, mas indica desigualdade no recorte.")

    if salario is not None:
        resultado["salario_informado"] = {
            "valor": float(salario),
            **{f"vs_mediana_{sexo}_pct": _diferenca_pct(float(salario), numeros["p50"])
               for sexo, numeros in por_sexo.items()},
        }
    return resultado


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="comando", required=True)
    p_gerar = sub.add_parser("gerar", help="agrega o parquet da RAIS em data/agregados/")
    p_gerar.add_argument("--ano", type=int, default=2025)
    p_gerar.add_argument("--parquet", type=Path)
    p_consultar = sub.add_parser("consultar", help="consulta uma ocupação numa UF")
    alvo = p_consultar.add_mutually_exclusive_group(required=True)
    alvo.add_argument("--familia", help="família da CBO, 4 dígitos (ex.: 2124)")
    alvo.add_argument("--ocupacao", help="nome da ocupação (ex.: analista de sistemas)")
    p_consultar.add_argument("--uf", required=True)
    p_consultar.add_argument("--salario", type=float)
    p_consultar.add_argument("--ano", type=int, default=2025)
    args = parser.parse_args()

    if args.comando == "gerar":
        caminho, linhas, ocupacoes = gerar(args.ano, args.parquet)
        print(f"{linhas} recortes em {caminho}; {ocupacoes} ocupações em {OCUPACOES}")
        return

    familia = args.familia
    if args.ocupacao:
        achadas = buscar_ocupacao(args.ocupacao)
        if not achadas:
            raise SystemExit(f"Nenhuma ocupação encontrada para {args.ocupacao!r}.")
        print("Ocupações encontradas:", json.dumps(achadas, ensure_ascii=False, indent=2))
        familia = achadas[0]["cbo_familia"]
    print(json.dumps(consultar(familia, args.uf, args.salario, ano=args.ano), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
