#!/usr/bin/env python3
"""Prepara inspeção estratificada de questões JSON versus texto bruto por página."""
from __future__ import annotations
import argparse
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

PAGE_MARKER = re.compile(r"^\s*=====\s*PÁGINA\s+(\d+)\s*=====\s*$", re.IGNORECASE | re.MULTILINE)

def blocos_por_pagina(texto: str) -> dict[int, str]:
    matches = list(PAGE_MARKER.finditer(texto))
    return {
        int(m.group(1)): texto[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(texto)].strip()
        for i, m in enumerate(matches)
    }

def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKC", texto).casefold()
    return re.sub(r"\s+", " ", texto).strip()

def melhor_trecho(alvo: str, texto: str) -> tuple[str, str]:
    """Busca aproximação para ajudar o revisor a localizar texto divergente."""
    alvo_palavras = normalizar(alvo).split()
    bruto_palavras = normalizar(texto).split()
    if not alvo_palavras or not bruto_palavras:
        return "", "texto vazio"
    tamanho = max(5, min(len(alvo_palavras), 40))
    alvo_inicio = " ".join(alvo_palavras[:tamanho])
    melhor, score_melhor = "", 0.0
    for i in range(max(1, len(bruto_palavras) - tamanho + 1)):
        candidato = " ".join(bruto_palavras[i:i + tamanho])
        score = SequenceMatcher(None, alvo_inicio, candidato).ratio()
        if score > score_melhor:
            melhor, score_melhor = candidato, score
    return melhor, f"similaridade aproximada {score_melhor:.0%}"

def texto_json(q: dict[str, Any]) -> str:
    linhas = ["ENUNCIADO:", str(q.get("enunciado") or "[VAZIO]"), "", "ALTERNATIVAS:"]
    alternativas = q.get("alternativas") if isinstance(q.get("alternativas"), dict) else {}
    linhas.extend(f"{letra}) {alternativas.get(letra) or '[AUSENTE/VAZIA]'}" for letra in "ABCDE")
    return "\n".join(linhas)

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("json", type=Path)
    ap.add_argument("texto_bruto", type=Path)
    ap.add_argument("--questoes", default="1,2,3,30,45,46,60,75,89,90")
    ap.add_argument("--todas-com-recursos", action="store_true", help="Inclui flags True; null é ignorado.")
    ap.add_argument("--diff", action="store_true", help="Procura enunciado/alternativas na página normalizada e mostra aproximação se não encontrar.")
    ap.add_argument("--registrar", type=Path, help="Cria modelo JSON para preencher status e observações após revisão visual.")
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
    por_numero = {}
    for q in dados["questoes"]:
        if isinstance(q, dict):
            try:
                por_numero[int(q["numero"])] = q
            except (KeyError, TypeError, ValueError):
                pass
    if args.todas_com_recursos:
        nums.update(n for n, q in por_numero.items()
                    if q.get("tem_figura") is True or q.get("tem_tabela") is True)
    if not paginas:
        print("ERRO: nenhum marcador '===== PÁGINA N =====' encontrado.", file=sys.stderr)
        return 2
    registros = []
    for n in sorted(nums):
        print("\n" + "=" * 100)
        q = por_numero.get(n)
        if q is None:
            print(f"QUESTÃO {n}: não encontrada no JSON")
            registros.append({"numero": n, "status": "PENDENTE", "observacoes": "Questão ausente do JSON"})
            continue
        pag_raw = q.get("pagina_pdf")
        try:
            pag = int(pag_raw) if pag_raw is not None else None
        except (TypeError, ValueError):
            pag = None
        print(f"QUESTÃO {n} | página={pag_raw!r} | figura={q.get('tem_figura')!r} | tabela={q.get('tem_tabela')!r}")
        print("\n" + "-" * 44 + " JSON " + "-" * 44)
        print(texto_json(q))
        print("\n" + "-" * 39 + " TEXTO BRUTO " + "-" * 39)
        pagina_texto = paginas.get(pag) if pag is not None else None
        if pagina_texto is None:
            print("Página ausente/null/inválida ou não localizada no texto bruto.")
        else:
            print(f"[Página {pag}; pode conter outras questões]")
            print(pagina_texto)
            if pag + 1 in paginas:
                print("\n[ALERTA] Confira também a página seguinte se o conteúdo parecer incompleto.")
        if args.diff and pagina_texto is not None:
            print("\n--- DIAGNÓSTICO APROXIMADO (não é prova de fidelidade) ---")
            campos = [("ENUNCIADO", q.get("enunciado") or "")]
            alt = q.get("alternativas") if isinstance(q.get("alternativas"), dict) else {}
            campos.extend((f"ALTERNATIVA {letra}", alt.get(letra) or "") for letra in "ABCDE")
            bruto_norm = normalizar(pagina_texto)
            for nome, valor in campos:
                alvo = normalizar(valor)
                if alvo and alvo in bruto_norm:
                    print(f"{nome}: correspondência normalizada encontrada")
                else:
                    trecho, razao = melhor_trecho(valor, pagina_texto)
                    print(f"{nome}: >>> NÃO ENCONTRADO EXATAMENTE; {razao}")
                    print(f"  JSON: {str(valor)[:250]}")
                    print(f"  TRECHO APROXIMADO: {trecho[:250]}")
        print("\nRESULTADO MANUAL: [ ] OK  [ ] DIVERGENTE  [ ] CORTE")
        print("NOTA: ______________________________________________")
        registros.append({
            "numero": n, "pagina_pdf": pag, "status": "PENDENTE", "observacoes": "",
            "tem_figura": q.get("tem_figura"), "tem_tabela": q.get("tem_tabela"),
            "revisao_visual_pdf": False
        })
    if args.registrar:
        args.registrar.write_text(json.dumps({
            "arquivo_json": str(args.json), "arquivo_texto_bruto": str(args.texto_bruto),
            "commit_script_base": "10ef4017251780a9acd0621ce0e916bad7bca3e5",
            "aviso": "Modelo pendente; preencher status/observacoes após conferência visual no PDF.",
            "questoes": registros
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Modelo de registro criado: {args.registrar}")
    print(f"\nResumo: {len(nums)} questões selecionadas; {len(paginas)} páginas reconhecidas.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
