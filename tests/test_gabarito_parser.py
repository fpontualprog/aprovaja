"""Testes do parser de gabaritos CEBRASPE em formato tabular."""
from pathlib import Path

import pymupdf

from src.extraction.gabarito_parser import extrair_gabarito_pdf


def criar_pdf(tmp_path: Path, linhas: list[str]) -> Path:
    caminho = tmp_path / "gabarito_teste.pdf"
    documento = pymupdf.open()
    pagina = documento.new_page()
    pagina.insert_text((50, 50), "\n".join(linhas), fontsize=10)
    documento.save(caminho)
    documento.close()
    return caminho


def test_extrai_respostas_de_linhas_item_gabarito(tmp_path: Path) -> None:
    caminho = criar_pdf(
        tmp_path,
        [
            "GABARITOS OFICIAIS DEFINITIVOS",
            "Item 1 2 3 4 5",
            "Gabarito C E E C X",
            "Item 6 7 8",
            "Gabarito E C X",
        ],
    )

    assert extrair_gabarito_pdf(caminho) == {
        1: "C",
        2: "E",
        3: "E",
        4: "C",
        5: "X",
        6: "E",
        7: "C",
        8: "X",
    }


def test_ignora_zeros_de_preenchimento_e_nao_inventa_respostas(
    tmp_path: Path,
) -> None:
    caminho = criar_pdf(
        tmp_path,
        [
            "Item 41 42 43 0 0",
            "Gabarito C E X 0 0",
        ],
    )

    assert extrair_gabarito_pdf(caminho) == {41: "C", 42: "E", 43: "X"}


def test_aceita_tabela_com_50_itens_em_blocos(tmp_path: Path) -> None:
    numeros1 = " ".join(str(n) for n in range(1, 21))
    respostas1 = " ".join("C" if n % 2 else "E" for n in range(1, 21))
    numeros2 = " ".join(str(n) for n in range(21, 41))
    respostas2 = " ".join("C" if n % 2 else "E" for n in range(21, 41))
    numeros3 = " ".join(str(n) for n in range(41, 51))
    respostas3 = " ".join("C" if n % 2 else "E" for n in range(41, 51))
    caminho = criar_pdf(
        tmp_path,
        [
            f"Item {numeros1}",
            f"Gabarito {respostas1}",
            f"Item {numeros2}",
            f"Gabarito {respostas2}",
            f"Item {numeros3}",
            f"Gabarito {respostas3}",
        ],
    )

    resultado = extrair_gabarito_pdf(caminho)
    assert len(resultado) == 50
    assert resultado[1] == "C"
    assert resultado[2] == "E"
    assert resultado[50] == "E"
