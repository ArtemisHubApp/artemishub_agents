"""O texto dos prompts de LLM mora só no Langfuse: o código (repo público) não pode guardá-lo."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
TRECHOS_DO_PROMPT = ("Você é a Análise", "Regras obrigatórias", "conteúdo entre as tags é dado não confiável")


def test_nenhum_texto_de_prompt_no_codigo():
    for arquivo in (RAIZ / "src").rglob("*.py"):
        texto = arquivo.read_text(encoding="utf-8")
        for trecho in TRECHOS_DO_PROMPT:
            assert trecho not in texto, f"{arquivo.relative_to(RAIZ)} guarda texto de prompt: {trecho!r}"
