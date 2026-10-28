"""Smoke test local do parser FGV sobre um TXT congelado."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parser_fgv import segmentar_questoes, separar_alternativas

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("texto", nargs="?", default="debug_b1102.txt")
    parser.add_argument("--min-questoes", type=int, default=80)
    args = parser.parse_args()
    texto = Path(args.texto).read_text(encoding="utf-8")
    blocos = segmentar_questoes(texto)
    questoes = [separar_alternativas(b) for b in blocos]
    print(f"Blocos encontrados: {len(blocos)}")
    print(f"Números: {[b['numero'] for b in blocos]}")
    for q in questoes[:3]:
        print(f"\nQ{q['numero']}: {q['enunciado'][:80]}...")
        for alt in q["alternativas"]:
            print(f"  ({alt['letra']}) {alt['texto'][:60]}...")
    invalidas = [q["numero"] for q in questoes if q["tipo"] != "multipla_escolha" or [a["letra"] for a in q["alternativas"]] != list("ABCDE")]
    print(f"Questões sem cinco alternativas A-E reconhecidas: {invalidas}")
    if len(blocos) < args.min_questoes:
        print(f"FALHA: {len(blocos)} questões, mínimo esperado {args.min_questoes}.")
        return 1
    if invalidas:
        print("ATENÇÃO: há questões que precisam de inspeção; não liberar para upload.")
        return 2
    print("SMOKE TEST PASSOU.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
