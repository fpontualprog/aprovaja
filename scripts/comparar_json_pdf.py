#!/usr/bin/env python3
"""Prepara inspeção estratificada de questões JSON versus texto bruto por página.

Exemplo:
  python scripts/comparar_json_pdf.py saida_b1102.json debug_b1102.txt --questoes 1,2,3,30,45,46,60,75,89,90 --todas-com-recursos

A saída coloca JSON e texto bruto em colunas lógicas lado a lado por seção.
Não prova fidelidade ao PDF: a conferência visual continua obrigatória.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


PAGE_MARKER = re.compile(r"^\s*=====\s*PÁGINA\s+(\d+)\s*=====\s*$", re.IGNORECASE | re.MULTILINE)


def blocos_por_pagina(texto: str) -> dict[int, str]:
    """Separa páginas usando os marcadores exatos escritos pelo workflow."""
    matches = list(PAGE_MARKER.finditer(texto))
    paginas: dict[int, str] = {}
    for i, match in enumerate(matches):
        inicio = match.end()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
        paginas[int(match.group(1))] = texto[inicio:fim].strip()
    return paginas


def texto_json(q: dict[str, Any]) -> str:
    linhas = ["ENUNCIADO:", str(q.get("enunciado") or "[VAZIO]")]
    linhas.append("")
    linhas.append("ALTERNATIVAS:")
    alternativas = q.get("alternativas")
    if not isinstance(alternativas, dict):
        alternativas = {}
    for letra in "ABCDE":
        valor = alternativas.get(letra)
        linhas.append(f"{letra}) {valor if valor else '[AUSENTE/VAZIA]'}")
    return "\n".join(linhas)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("json", type=Path, help="JSON gerado pelo extrator")
    ap.add_argument("texto_bruto", type=Path, help="debug_b1102.txt")
    ap.add_argument(
        "--questoes",
        default="1,2,3,30,45,46,60,75,89,90",
        help="Números separados por vírgula (padrão: amostra estratificada)",
    )
    ap.add_argument(
        "--todas-com-recursos",
        action="store_true",
        help="Inclui questões com tem_figura=true ou tem_tabela=true; null é ignorado",
    )
    args = ap.parse_args()

    try:
        dados = json.loads(args.json.read_text(encoding="utf-8-sig"))
        bruto = args.texto_bruto.read_text(encoding="utf-8-sig")
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        print(f"ERRO ao ler entrada: {exc}", file=sys.stderr)
        return 2

    if not isinstance(dados, dict) or not isinstance(dados.get("questoes"), list):
        print("ERRO: JSON deve conter uma lista em 'questoes'.", file=sys.stderr)
        return 2

    paginas = blocos_por_pagina(bruto)
    try:
        nums = {int(x.strip()) for x in args.questoes.split(",") if x.strip()}
    except ValueError:
        print("ERRO: --questoes deve conter números separados por vírgula.", file=sys.stderr)
        return 2

    qs = dados["questoes"]
    por_numero: dict[int, dict[str, Any]] = {}
    for q in qs:
        if not isinstance(q, dict):
            continue
        try:
            numero = int(q["numero"])
        except (KeyError, TypeError, ValueError):
            continue
        por_numero[numero] = q

    if args.todas_com_recursos:
        nums.update(
            numero
            for numero, q in por_numero.items()
            if q.get("tem_figura") is True or q.get("tem_tabela") is True
        )

    if not paginas:
        print("ERRO: nenhum marcador '===== PÁGINA N =====' foi encontrado.", file=sys.stderr)
        return 2

    for n in sorted(nums):
        print("\n" + "=" * 100)
        q = por_numero.get(n)
        if q is None:
            print(f"QUESTÃO {n}: não encontrada no JSON")
            continue

        pag_raw = q.get("pagina_pdf")
        try:
            pag = int(pag_raw) if pag_raw is not None else None
        except (TypeError, ValueError):
            pag = None

        print(
            f"QUESTÃO {n} | página JSON={pag_raw!r} | "
            f"figura={q.get('tem_figura')!r} | tabela={q.get('tem_tabela')!r}"
        )
        print("\n" + "-" * 44 + " JSON " + "-" * 44)
        print(texto_json(q))
        print("\n" + "-" * 39 + " TEXTO BRUTO " + "-" * 39)
        if pag is None:
            print("Página JSON ausente/null/inválida; não é possível selecionar a página.")
        elif pag not in paginas:
            print(f"Página {pag} não localizada no texto bruto.")
        else:
            print(f"[Conteúdo integral da página {pag}; pode conter outras questões]")
            print(paginas[pag])
            if pag + 1 in paginas:
                print(
                    "\n[ALERTA DE INSPEÇÃO] Confira também a página seguinte se o "
                    "enunciado ou as alternativas parecerem incompletos."
                )
        print("\nRESULTADO MANUAL: [ ] OK  [ ] DIVERGENTE")
        print("NOTA: ______________________________________________")

    print(f"\nResumo: {len(nums)} números selecionados; páginas no texto bruto: {len(paginas)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
