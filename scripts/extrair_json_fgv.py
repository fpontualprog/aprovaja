#!/usr/bin/env python3
"""Gera JSON de inspeção APROVAJÁ a partir do texto extraído e do PDF original."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import pymupdf
except ImportError:
    pymupdf = None

sys.path.insert(0, str(Path(__file__).parent))
from validar_questoes_fgv import parse_texto_bruto  # noqa: E402

META = {
    "banca": "FGV",
    "prova": "Concurso Público Nacional Unificado - 2ª Edição",
    "arquivo": "b1102.pdf",
    "tipo": "2 - Verde",
    "turno": "Tarde",
    "nivel": "Superior",
    "bloco": "Bloco Temático 1 - Seguridade Social: Saúde, Assistência Social e Previdência Social",
}


def mapear_recursos_pdf(pdf_path: Path | None) -> dict[int, dict[str, bool]]:
    if pdf_path is None or pymupdf is None:
        if pdf_path is not None and pymupdf is None:
            print("AVISO: PyMuPDF indisponível; flags de recursos serão null.", file=sys.stderr)
        return {}
    mapa: dict[int, dict[str, bool]] = {}
    with pymupdf.open(pdf_path) as pdf:
        for i, page in enumerate(pdf, start=1):
            tem_figura = bool(page.get_images(full=False))
            try:
                tem_tabela = len(page.find_tables().tables) > 0
            except Exception:
                tem_tabela = False
            mapa[i] = {"tem_figura": tem_figura, "tem_tabela": tem_tabela}
    return mapa


def montar_json(questoes, mapa_recursos: dict[int, dict[str, bool]]) -> dict:
    itens = []
    for q in questoes:
        recursos = mapa_recursos.get(q.pagina_pdf or -1, {})
        itens.append({
            "numero": q.numero,
            "enunciado": q.enunciado.strip(),
            "alternativas": {k: v.strip() for k, v in q.alternativas.items()},
            "pagina_pdf": q.pagina_pdf,
            "legenda_figura": q.legenda_figura,
            "legenda_tabela": q.legenda_tabela,
            "tem_figura": recursos.get("tem_figura"),
            "tem_tabela": recursos.get("tem_tabela"),
        })
    return {**META, "total_questoes": len(itens), "questoes": itens}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("texto", type=Path)
    ap.add_argument("--pdf", type=Path)
    ap.add_argument("--saida", type=Path, default=Path("saida_b1102.json"))
    args = ap.parse_args()
    questoes = parse_texto_bruto(args.texto.read_text(encoding="utf-8"))
    if not questoes:
        print("ERRO: nenhuma questão extraída.", file=sys.stderr)
        return 1
    dados = montar_json(questoes, mapear_recursos_pdf(args.pdf))
    args.saida.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {len(questoes)} questões gravadas em {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
