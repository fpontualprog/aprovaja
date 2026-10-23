"""Roda o pipeline para um unico concurso (util para debug)."""
import argparse
from dotenv import load_dotenv
from src.pipeline import processar_concurso

def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--evento", required=True, help="Codigo do concurso (ex: PF_25_ADM)")
    parser.add_argument("--saida", default="data")
    args = parser.parse_args()
    questoes = processar_concurso(args.evento, args.saida)
    print("\nTotal de questoes: " + str(len(questoes)))

if __name__ == "__main__":
    main()
