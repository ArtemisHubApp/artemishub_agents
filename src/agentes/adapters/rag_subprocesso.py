"""Pesquisa no `artemishub_rag` rodando o Retriever dele no próprio ambiente (subprocesso `uv run`).

Os dois repositórios usam o pacote `src`, então não dá para importar um no outro. Quando o RAG virar
pacote importável (artemishub_rag#23), troque só este adaptador; a porta `BuscadorDeDireitos` continua igual.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.agentes.application.portas import FonteIndisponivel
from src.agentes.domain.modelos import Evidencia

RAIZ_AGENTS = Path(__file__).resolve().parents[3]
MARCADOR = "ARTEMIS_EVIDENCIAS "
TIMEOUT_SEGUNDOS = 180

# Roda dentro do artemishub_rag. Lê {tema, top_k, parcial} do stdin e imprime uma linha marcada com o JSON.
# Usa a API pública `artemis_rag.buscar` (artemishub_rag#27) e, no layout antigo (pacote `src`), o Retriever.
_SCRIPT = f"""
import json, sys
pedido = json.load(sys.stdin)
campos = ("id", "titulo", "url", "pagina", "artigo", "texto")
try:
    from artemis_rag import buscar
except ImportError:
    from src.query import Retriever
    hits = Retriever(allow_partial=pedido["parcial"]).retrieve(pedido["tema"], pedido["top_k"])
    saida = []
    for i, hit in enumerate(hits, 1):
        meta = hit["metadata"]
        origem = meta.get("metadata") or {{}}
        if isinstance(origem, str):
            origem = json.loads(origem)
        saida.append({{"id": f"FONTE {{i}}", "titulo": meta.get("title") or "", "url": meta.get("source_url") or "",
                      "pagina": str(meta["page"]) if meta.get("page") is not None else None,
                      "artigo": origem.get("article"), "texto": hit["text"]}})
else:
    evidencias = buscar(pedido["tema"], pedido["top_k"], parcial=pedido["parcial"])
    saida = [{{c: getattr(e, c) for c in campos}} for e in evidencias]
print({MARCADOR!r} + json.dumps(saida, ensure_ascii=False))
"""

Executor = Callable[..., subprocess.CompletedProcess[str]]


class BuscadorRagSubprocesso:
    def __init__(self, rag_dir: Path, parcial: bool = False, executar: Executor = subprocess.run,
                 timeout: int = TIMEOUT_SEGUNDOS) -> None:
        self.rag_dir, self.parcial, self._executar, self._timeout = Path(rag_dir), parcial, executar, timeout

    @classmethod
    def de_ambiente(cls) -> BuscadorRagSubprocesso:
        """`ARTEMIS_RAG_DIR` (padrão: `../artemishub_rag`, ao lado deste repo) e `ARTEMIS_RAG_PARCIAL=1`."""
        rag_dir = Path(os.getenv("ARTEMIS_RAG_DIR", RAIZ_AGENTS.parent / "artemishub_rag"))
        return cls(rag_dir, parcial=os.getenv("ARTEMIS_RAG_PARCIAL") == "1")

    def buscar(self, tema: str, top_k: int) -> list[Evidencia]:
        pedido = json.dumps({"tema": tema, "top_k": top_k, "parcial": self.parcial})
        comando = ["uv", "run", "--project", str(self.rag_dir), "--quiet", "python", "-c", _SCRIPT]
        try:
            resultado = self._executar(comando, cwd=self.rag_dir, input=pedido, capture_output=True, text=True,
                                       encoding="utf-8", timeout=self._timeout, check=False)
        except FileNotFoundError as erro:
            raise FonteIndisponivel("uv não encontrado no PATH para rodar o artemishub_rag") from erro
        except subprocess.TimeoutExpired as erro:
            raise FonteIndisponivel(f"o RAG demorou mais de {self._timeout} s") from erro
        if resultado.returncode != 0:
            ultima = (resultado.stderr or "").strip().splitlines()[-1:] or ["sem detalhes"]
            raise FonteIndisponivel(f"o RAG falhou: {ultima[0]}")
        return [Evidencia(**item) for item in self._ler(resultado.stdout)]

    @staticmethod
    def _ler(stdout: str) -> list[dict[str, Any]]:
        linha = next((ln for ln in reversed(stdout.splitlines()) if ln.startswith(MARCADOR)), None)
        if linha is None:
            raise FonteIndisponivel("o RAG terminou com saída sem resultado")
        try:
            return json.loads(linha[len(MARCADOR):])
        except json.JSONDecodeError as erro:
            raise FonteIndisponivel(f"o RAG devolveu JSON inválido: {erro}") from erro
