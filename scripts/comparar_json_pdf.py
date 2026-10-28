#!/usr/bin/env python3
"""Compara questões do JSON FGV com os trechos correspondentes do texto bruto.

Uso:
  python scripts/comparar_json_pdf.py saida_b1102.json debug_b1102.txt --questoes 1,2,3,30,45,46,60,75,89,90
O script não substitui a conferência visual no PDF; paginação e texto bruto são pistas para inspeção manual.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

def blocos_por_pagina(texto: str) -> dict[int, str]:
    partes = re.split(r"=====\s*PÁGINA\s+(\d+)\s*=====", texto, flags=re.I)
    return {int(partes[i]): partes[i + 1] for i in range(1, len(partes) - 1, 2)}

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("json", type=Path)
    ap.add_argument("texto_bruto", type=Path)
    ap.add_argument("--questoes", default="1,2,3,30,45,46,60,75,89,90",
                    help="Números separados por vírgula; padrão: amostra estratificada")
    ap.add_argument("--todas-com-recursos", action="store_true",
                    help="Inclui todas as questões com tem_figura/tem_tabela true")
    args = ap.parse_args()
    dados = json.loads(args.json.read_text(encoding="utf-8"))
    paginas = blocos_por_pagina(args.texto_bruto.read_text(encoding="utf-8"))
    qs = dados.get("questoes", [])
    nums = {int(x.strip()) for x in args.questoes.split(",") if x.strip()}
    if args.todas_com_recursos:
        nums.update(int(q["numero"]) for q in qs if q.get("tem_figura") is True or q.get("tem_tabela") is True)
    por_numero = {int(q["numero"]): q for q in qs}
    for n in sorted(nums):
        q = por_numero.get(n)
        print("\n" + "=" * 100)
        if not q:
            print(f"QUESTÃO {n}: não encontrada no JSON")
            continue
        pag = q.get("pagina_pdf")
        print(f"QUESTÃO {n} | página PDF indicada: {pag} | figura={q.get('tem_figura')} | tabela={q.get('tem_tabela')}")
        print("\n--- JSON: ENUNCIADO ---\n" + (q.get("enunciado") or ""))
        print("\n--- JSON: ALTERNATIVAS ---")
        for letra in "ABCDE":
            print(f"{letra}) {q.get('alternativas', {}).get(letra, '[AUSENTE]')}")
        print("\n--- TEXTO BRUTO: PÁGINA INDICADA ---")
        if pag in paginas:
            print(paginas[pag])
        else:
            print("Página não localizada no texto bruto.")
        print("\nNOTA DE REVISÃO: preencher manualmente OK ou DIVERGENTE após comparar com o PDF visual.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
