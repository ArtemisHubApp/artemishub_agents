"""Agente de Análise: as variáveis do prompt (o texto do prompt mora só no Langfuse) e o rascunho padrão, sem LLM."""

from __future__ import annotations

from src.agentes.domain.formatacao import brl, pct
from src.agentes.domain.modelos import DadosSalariais, PedidoDeRascunho

LIMITE_TRECHO = 280

# Variáveis do prompt chat `artemis/analise-rascunho` no Langfuse ({{pergunta}}, {{ocupacao}}...).
VARIAVEIS_DO_PROMPT = ("pergunta", "ocupacao", "dados_salariais", "evidencias", "correcao")


def _linhas_salariais(dados: DadosSalariais | None) -> list[str]:
    if not dados or not dados.get("suficiente"):
        return ["Sem dados salariais suficientes para esse recorte."]
    local = "Brasil" if dados["uf_usada"] == "BR" else dados["uf_usada"]
    grupo = f"{dados['cbo_familia_nome']} (família {dados['cbo_familia']})"
    linhas = [f"Grupo da CBO: {grupo}, {local}, RAIS {dados['ano']}."]
    rotulos = {"feminino": "Mulheres", "masculino": "Homens", "todos": "Todas as pessoas"}
    for sexo, n in dados["por_sexo"].items():
        linha = (f"{rotulos[sexo]}: mediana {brl(n['p50'])}, faixa do meio de {brl(n['p25'])} a {brl(n['p75'])}, "
                 f"{n['n']} vínculos")
        if n.get("p50_tempo_integral") is not None:
            linha += f", mediana em tempo integral (40 h ou mais) {brl(n['p50_tempo_integral'])}"
        linhas.append(linha + ".")
    diferenca = dados.get("diferenca_bruta_mediana_pct")
    if diferenca is not None:
        sentido = "abaixo" if diferenca > 0 else "acima"
        linhas.append(f"Diferença bruta entre as medianas de mulheres e homens: {pct(diferenca)} ({sentido} delas).")
    homens = dados["por_sexo"].get("masculino")
    if homens:
        linhas.append(f"Referência provisória para negociar (mediana dos homens nesta ocupação e UF): "
                      f"{brl(homens['p50'])}.")
    informado = dados.get("salario_informado")
    if informado:
        linhas.append(f"Salário informado: {brl(informado['valor'])}.")
        for chave, rotulo in (("feminino", "das mulheres"), ("masculino", "dos homens"), ("todos", "geral")):
            valor = informado.get(f"vs_mediana_{chave}_pct")
            if valor is not None:
                linhas.append(f"Ele está {pct(valor)} {'acima' if valor >= 0 else 'abaixo'} da mediana {rotulo}.")
    linhas += [f"Aviso: {aviso}" for aviso in dados.get("avisos", [])]
    return linhas


def variaveis_do_prompt(pedido: PedidoDeRascunho) -> dict[str, str]:
    """Valores das variáveis do prompt da Análise. Cada fonte de dados vai entre delimitadores no prompt."""
    evidencias = "\n".join(
        f"[{e.id}] {e.titulo}" + (f", {e.artigo}" if e.artigo else "") + (f", página {e.pagina}" if e.pagina else "")
        + f"\n{e.texto[:1200]}"
        for e in pedido.evidencias
    ) or "Nenhuma evidência recuperada."
    ocupacao = pedido.parametros.ocupacao
    motivo = pedido.motivo_reprovacao
    return {
        "pergunta": pedido.pergunta,
        "ocupacao": (f"Ocupação encontrada na CBO: {ocupacao}. Fale dela pelo nome; os números são do grupo da CBO "
                     "dela.\n\n") if ocupacao else "",
        "dados_salariais": "\n".join(_linhas_salariais(pedido.dados_salariais)),
        "evidencias": evidencias,
        "correcao": f"\n\nA versão anterior foi reprovada pela Validação. Corrija isto: {motivo}" if motivo else "",
    }


def _trecho(texto: str) -> str:
    limpo = " ".join(texto.split())
    return limpo if len(limpo) <= LIMITE_TRECHO else limpo[:LIMITE_TRECHO].rsplit(" ", 1)[0] + "…"


def rascunho_padrao(pedido: PedidoDeRascunho) -> str:
    """Rascunho sem LLM: os mesmos fatos, em frases fixas. Usado quando o LLM não está configurado."""
    paragrafos: list[str] = []
    dados = pedido.dados_salariais
    if pedido.intencao.salario and dados and dados.get("suficiente"):
        por_sexo = dados["por_sexo"]
        local = "no Brasil" if dados["uf_usada"] == "BR" else f"em {dados['uf_usada']}"
        if {"feminino", "masculino"} <= por_sexo.keys():
            f, m = por_sexo["feminino"], por_sexo["masculino"]
            paragrafos.append(
                f"Para {dados['cbo_familia_nome'].lower()} {local}, a mediana salarial das mulheres é {brl(f['p50'])} "
                f"e a dos homens é {brl(m['p50'])}, segundo a RAIS {dados['ano']} [RAIS]."
            )
        else:
            todos = por_sexo.get("todos") or next(iter(por_sexo.values()))
            paragrafos.append(f"Para {dados['cbo_familia_nome'].lower()} {local}, a mediana salarial é "
                              f"{brl(todos['p50'])}, segundo a RAIS {dados['ano']} [RAIS].")
        diferenca = dados.get("diferenca_bruta_mediana_pct")
        if diferenca is not None:
            sentido = "abaixo" if diferenca > 0 else "acima"
            paragrafos.append(
                f"A mediana das mulheres fica {pct(diferenca)} {sentido} da dos homens. É uma diferença bruta: "
                "não controla escolaridade, tempo de casa nem jornada, mas mostra desigualdade no grupo [RAIS]."
            )
        informado = dados.get("salario_informado")
        if informado:
            comparacoes = [
                f"{pct(v)} {'acima' if v >= 0 else 'abaixo'} da mediana {rotulo}"
                for chave, rotulo in (("feminino", "das mulheres"), ("masculino", "dos homens"))
                if (v := informado.get(f"vs_mediana_{chave}_pct")) is not None
            ]
            paragrafos.append(f"O salário que você informou, {brl(informado['valor'])}, está "
                              + " e ".join(comparacoes) + " [RAIS].")
    if pedido.intencao.direitos:
        for evidencia in pedido.evidencias[:2]:
            referencia = evidencia.titulo + (f", {evidencia.artigo}" if evidencia.artigo else "")
            paragrafos.append(f"Sobre seus direitos, {referencia} diz: “{_trecho(evidencia.texto)}” [{evidencia.id}].")
    return "\n\n".join(paragrafos)
