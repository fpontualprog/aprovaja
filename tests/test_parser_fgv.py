import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from parser_fgv import segmentar_questoes, separar_alternativas
from gabarito import parsear_gabarito
from validacao import validar_questao

def test_segmenta_duas_questoes():
    texto = """1
Este é um enunciado de questão suficientemente longo para teste.
(A) primeira alternativa
(B) segunda alternativa
(C) terceira alternativa
(D) quarta alternativa
(E) quinta alternativa
2
Este é outro enunciado de questão suficientemente longo para teste.
(A) primeira alternativa
(B) segunda alternativa
(C) terceira alternativa
(D) quarta alternativa
(E) quinta alternativa
"""
    blocos = segmentar_questoes(texto)
    assert [b["numero"] for b in blocos] == [1, 2]
    q = separar_alternativas(blocos[0])
    assert q["tipo"] == "multipla_escolha"
    assert [a["letra"] for a in q["alternativas"]] == list("ABCDE")

def test_gabarito():
    assert parsear_gabarito("1 A\n2 - C\nQUESTÃO 3: E") == {1:"A",2:"C",3:"E"}

def test_validacao_sem_gabarito_fica_quarentena():
    q = {"enunciado":"Um enunciado de tamanho suficiente para passar na validação.",
         "tipo":"multipla_escolha",
         "alternativas":[{"letra":x,"texto":"alternativa longa"} for x in "ABCDE"],
         "texto_bruto":"texto", "tem_imagem":False}
    status, motivos = validar_questao(q)
    assert status == "QUARENTENA"
    assert "gabarito_ausente" in motivos
