"""Exporta o texto das páginas de um JSON de prova para inspeção manual."""
import json
import sys
from pathlib import Path

def extrair_texto_para_debug(json_path: str, out_path: str) -> None:
    dados = json.loads(Path(json_path).read_text(encoding="utf-8"))
    paginas = dados.get("paginas", [])
    texto = "\n".join(str(p.get("texto", "")) for p in paginas)
    Path(out_path).write_text(texto, encoding="utf-8")
    print(f"Texto extraído: {len(texto)} chars; páginas: {len(paginas)} -> {out_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Uso: python scripts/debug_extrair_texto.py entrada.json saida.txt")
    extrair_texto_para_debug(sys.argv[1], sys.argv[2])
