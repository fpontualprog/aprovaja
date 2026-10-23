from src.extraction.pdf_parser import segmentar_itens

def test_segmentar_itens_numerados():
    texto = "1. Este é um enunciado de questão suficientemente longo para teste.\n2. Este é outro enunciado de questão suficientemente longo para teste."
    itens = segmentar_itens(texto)
    assert [item["numero"] for item in itens] == [1, 2]
