"""Teste isolado: baixa o gabarito definitivo da PF e mostra o texto extraído.

Execute localmente com:
    python tests/test_gabarito.py

O download só ocorre quando o arquivo é executado diretamente; pytest não
dispara uma chamada de rede automaticamente.
"""
from pathlib import Path
import sys

import pymupdf
import requests

URL_GABARITO = (
    "https://cdn.cebraspe.org.br/concursos/PF_25_ADM/arquivos/"
    "Gab_Definitivo_094_PF_CB1_01.pdf"
)
DESTINO = Path("data/testes/Gab_Definitivo_094_PF_CB1_01.pdf")


def main() -> None:
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    print(f"Baixando gabarito: {URL_GABARITO}")
    response = requests.get(
        URL_GABARITO,
        timeout=60,
        headers={"User-Agent": "APROVAJA-gabarito-test/1.0"},
    )
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        raise RuntimeError(
            f"A URL não retornou um PDF válido (Content-Type: "
            f"{response.headers.get('Content-Type')})."
        )
    DESTINO.write_bytes(response.content)
    print(f"PDF salvo em: {DESTINO} ({len(response.content)} bytes)")

    with pymupdf.open(DESTINO) as documento:
        texto = "\n".join(
            pagina.get_text("text", sort=True) for pagina in documento
        )

    inicio, fim = 1500, 3500
    print(f"\n--- TEXTO EXTRAÍDO: CARACTERES {inicio} A {fim} ---\n")
    print(texto[inicio:fim] or "(O texto extraído não chega à posição 1500.)")
    print("\n--- FIM DO TRECHO ---")
    if not texto.strip():
        print(
            "AVISO: nenhum texto foi extraído; o PDF pode exigir OCR.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
