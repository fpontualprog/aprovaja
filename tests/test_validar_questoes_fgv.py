import unittest

from scripts.validar_questoes_fgv import Questao, parse_texto_bruto, validar


def trecho_questoes():
    return """===== PÁGINA 1 =====
1
Considerando as regras de administração pública descritas no texto, assinale a alternativa correta.
(A) A primeira alternativa apresenta uma proposição suficientemente desenvolvida.
(B) A segunda alternativa apresenta uma proposição suficientemente desenvolvida.
(C) A terceira alternativa apresenta uma proposição suficientemente desenvolvida.
(D) A quarta alternativa apresenta uma proposição suficientemente desenvolvida.
(E) A quinta alternativa apresenta uma proposição suficientemente desenvolvida.
2
Sobre a organização administrativa, assinale a opção correta conforme o enunciado apresentado.
(A) A primeira resposta possível descreve corretamente a situação indicada.
(B) A segunda resposta possível descreve corretamente a situação indicada.
(C) A terceira resposta possível descreve corretamente a situação indicada.
(D) A quarta resposta possível descreve corretamente a situação indicada.
(E) A quinta resposta possível descreve corretamente a situação indicada.
"""


class TestValidarQuestoesFGV(unittest.TestCase):
    def test_extrai_duas_questoes_com_cinco_alternativas(self):
        questoes = parse_texto_bruto(trecho_questoes())
        self.assertEqual([q.numero for q in questoes], [1, 2])
        self.assertIn("Considerando as regras", questoes[0].enunciado)
        self.assertEqual(set(questoes[0].alternativas), set("ABCDE"))
        self.assertIn("quinta alternativa", questoes[0].alternativas["E"])

    def test_questoes_validas_passam_validacao(self):
        questoes = parse_texto_bruto(trecho_questoes())
        ok, problemas = validar(questoes, min_questoes=2)
        self.assertTrue(ok, problemas)
        self.assertEqual(problemas, [])
        self.assertTrue(all(q.status == "OK" for q in questoes))

    def test_alternativa_ausente_e_falha(self):
        q = Questao(
            numero=1,
            enunciado="Este enunciado é suficientemente longo para passar pela regra de tamanho mínimo.",
            alternativas={
                "A": "Alternativa A com conteúdo suficiente.",
                "B": "Alternativa B com conteúdo suficiente.",
                "C": "Alternativa C com conteúdo suficiente.",
                "D": "Alternativa D com conteúdo suficiente.",
            },
        )
        ok, _ = validar([q], min_questoes=1)
        self.assertFalse(ok)
        self.assertIn("alternativa (E) ausente", q.erros)

    def test_sequencia_quebrada_e_detectada(self):
        questoes = [
            Questao(numero=1, enunciado="Enunciado longo o bastante para passar na validação estrutural.", alternativas={k: f"Conteúdo alternativo {k}" for k in "ABCDE"}),
            Questao(numero=3, enunciado="Outro enunciado longo o bastante para passar na validação estrutural.", alternativas={k: f"Outro conteúdo alternativo {k}" for k in "ABCDE"}),
        ]
        ok, problemas = validar(questoes, min_questoes=2)
        self.assertFalse(ok)
        self.assertTrue(any("Sequência quebrada" in p for p in problemas))


if __name__ == "__main__":
    unittest.main()
