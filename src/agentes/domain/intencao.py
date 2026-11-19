"""Leitura determinística da pergunta: intenção (salário, direitos) e parâmetros (UF, salário, ocupação)."""

from __future__ import annotations

import re
import unicodedata

from src.agentes.domain.modelos import Intencao

UFS = {
    "AC": "acre", "AL": "alagoas", "AP": "amapa", "AM": "amazonas", "BA": "bahia", "CE": "ceara",
    "DF": "distrito federal", "ES": "espirito santo", "GO": "goias", "MA": "maranhao", "MT": "mato grosso",
    "MS": "mato grosso do sul", "MG": "minas gerais", "PA": "para", "PB": "paraiba", "PR": "parana",
    "PE": "pernambuco", "PI": "piaui", "RJ": "rio de janeiro", "RN": "rio grande do norte",
    "RS": "rio grande do sul", "RO": "rondonia", "RR": "roraima", "SC": "santa catarina", "SP": "sao paulo",
    "SE": "sergipe", "TO": "tocantins",
}

# "igualdade salarial" é tema de direitos, não pedido de valor: por isso não basta a palavra "salarial".
_SALARIO = re.compile(
    r"\b(ganh|remunera|receb|quanto\s+(se\s+)?(ganha|recebe|paga)|mediana|faixa\s+salarial|justo"
    r"|meu\s+sal[aá]rio|sal[aá]rio\s+(de|d[oa]s?|m[eé]dio))"
    r"|r\$"
)
_DIREITOS = re.compile(
    r"\b(direito|lei\b|leis\b|igualdade|discrimina|diferen[cç]a\s+(para|em\s+rela[cç][aã]o\s+aos|com)\s+(os\s+)?homens"
    r"|equipara|clt|14\.?611|denunci|licen[cç]a|maternidade|paternidade|gestante|gr[aá]vida|ass[eé]dio|f[eé]rias"
    r"|jornada|hora\s+extra|demiss|demitid|rescis|fgts)"
)
# Valor em reais: com R$, ou número perto de ganho/salário (evita "Lei 14.611" e anos). Aceita "7 mil".
_NUMERO = r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?(\s*mil\b)?"
_VALOR_RS = re.compile(rf"r\$\s*{_NUMERO}")
_VALOR_SOLTO = re.compile(rf"\b(?:ganho|recebo|ganhando|recebendo|sal[aá]rio\s+(?:de|[eé]))\s+{_NUMERO}")
PISO_SALARIO = 100.0  # abaixo disso é quase sempre "7 mil" escrito sem o "mil"
# Siglas em minúsculas só depois de preposição, e só as que não são palavras comuns ("se", "pa", "to"...).
_SIGLAS_MINUSCULAS = {"df", "sp", "rj", "mg", "rs", "sc", "pr", "ba", "pb", "rn", "ms", "mt", "ro", "rr", "ap", "ac"}

# Palavras da pergunta que não fazem parte do nome da ocupação.
_PALAVRAS_DA_PERGUNTA = {
    "quanto", "ganha", "ganho", "ganham", "recebe", "recebo", "qual", "quais", "a", "o", "as", "os", "um", "uma",
    "de", "da", "do", "das", "dos", "no", "na", "nos", "nas", "em", "e", "para", "pra", "com", "sou", "como",
    "trabalho", "diferenca", "homens", "mulheres", "mulher", "homem", "meus", "minhas", "meu", "minha",
    "direitos", "direito", "sao", "esta", "justo", "salario", "salarios", "mes", "por", "r", "eu", "que",
    "sobre", "lei", "media", "mediana", "mil", "reais", "ganhando", "recebendo",
}


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def interpretar(pergunta: str) -> Intencao:
    texto = pergunta.lower()
    return Intencao(salario=bool(_SALARIO.search(texto)), direitos=bool(_DIREITOS.search(texto)))


def extrair_uf(pergunta: str) -> str | None:
    """Sigla (`DF`; em minúsculas só depois de preposição e se não for palavra comum) ou nome do estado."""
    for sigla in re.findall(r"\b([A-Z]{2})\b", pergunta):
        if sigla in UFS:
            return sigla
    texto = f" {_sem_acento(pergunta)} "
    for sigla in re.findall(r"\b(?:em|no|na|de|do|da)\s+([a-z]{2})\b", texto):
        if sigla in _SIGLAS_MINUSCULAS:
            return sigla.upper()
    # nomes mais longos primeiro: "mato grosso do sul" antes de "mato grosso"
    for sigla, nome in sorted(UFS.items(), key=lambda item: -len(item[1])):
        if re.search(rf"\b(em|no|na|do|da|de)\s+{nome}\b", texto):
            return sigla
    return None


def extrair_salario(pergunta: str) -> float | None:
    texto = pergunta.lower()
    achado = _VALOR_RS.search(texto) or _VALOR_SOLTO.search(texto)
    if not achado:
        return None
    inteiro, centavos, mil = achado.group(1).replace(".", ""), achado.group(2) or "0", achado.group(3)
    valor = float(f"{inteiro}.{centavos}") * (1000 if mil else 1)
    return valor if valor >= PISO_SALARIO else None


def termo_de_ocupacao(pergunta: str) -> str:
    """O que sobra da pergunta sem palavras de pergunta, UF e valores: vai para `buscar_ocupacao`."""
    texto = _sem_acento(pergunta)
    for nome in sorted(UFS.values(), key=len, reverse=True):
        texto = re.sub(rf"\b{nome}\b", " ", texto)
    palavras = re.findall(r"[a-z]+", texto)
    siglas = {s.lower() for s in UFS}
    return " ".join(_forma_da_cbo(p) for p in palavras if p not in _PALAVRAS_DA_PERGUNTA and p not in siglas)


def _forma_da_cbo(palavra: str) -> str:
    """A CBO nomeia as ocupações no masculino: "desenvolvedora" → "desenvolvedor", "engenheira" → "engenheiro"."""
    if palavra.endswith("ora"):
        return palavra[:-1]
    if palavra.endswith("eira"):
        return palavra[:-1] + "o"
    if palavra.endswith("a") and not palavra.endswith("ista") and len(palavra) > 4:
        return palavra[:-1] + "o"
    return palavra
