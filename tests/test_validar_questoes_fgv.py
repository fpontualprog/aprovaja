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


    def test_proxima_questao_separa_mesmo_com_alternativa_anterior_ausente(self):
        texto = """1
Enunciado da primeira questão suficientemente comprido para passar pela validação estrutural.
(A) Alternativa A suficientemente longa.
(B) Alternativa B suficientemente longa.
(C) Alternativa C suficientemente longa.
(D) Alternativa D suficientemente longa.
2
Enunciado da segunda questão suficientemente comprido para passar pela validação estrutural.
(A) Alternativa A da segunda questão suficientemente longa.
(B) Alternativa B da segunda questão suficientemente longa.
(C) Alternativa C da segunda questão suficientemente longa.
(D) Alternativa D da segunda questão suficientemente longa.
(E) Alternativa E da segunda questão suficientemente longa.
"""
        questoes = parse_texto_bruto(texto)
        self.assertEqual([q.numero for q in questoes], [1, 2])
        self.assertNotIn("E", questoes[0].alternativas)
        ok, _ = validar(questoes, min_questoes=2)
        self.assertFalse(ok)
        self.assertIn("alternativa (E) ausente", questoes[0].erros)

    def test_rodape_realizacao_nao_vaza_para_alternativa(self):
        texto = """===== PÁGINA 1 =====
1
Este enunciado é suficientemente longo para testar a remoção do rodapé.
(A) Alternativa A com conteúdo suficiente.
(B) Alternativa B com conteúdo suficiente.
(C) Alternativa C com conteúdo suficiente.
(D) Alternativa D com conteúdo suficiente.
(E) Alternativa E com conteúdo suficiente.
Realização
"""
        questoes = parse_texto_bruto(texto)
        self.assertEqual(len(questoes), 1)
        self.assertNotIn("Realização", questoes[0].alternativas["E"])

    def test_legenda_com_fonte_e_separada_do_enunciado(self):
        texto = """===== PÁGINA 1 =====
1
O estudo apresenta os resultados históricos de saúde pública.
Evolução histórica das taxas de mortalidade e DALY segundo sexo e grupo de causa.
Fonte: GBD, 2021.
A partir dos dados apresentados, é correto concluir que:
(A) Alternativa A com conteúdo suficiente.
(B) Alternativa B com conteúdo suficiente.
(C) Alternativa C com conteúdo suficiente.
(D) Alternativa D com conteúdo suficiente.
(E) Alternativa E com conteúdo suficiente.
"""
        questoes = parse_texto_bruto(texto)
        self.assertEqual(len(questoes), 1)
        self.assertIn("A partir dos dados apresentados", questoes[0].enunciado)
        self.assertNotIn("Evolução histórica", questoes[0].enunciado)
        self.assertNotIn("Fonte: GBD", questoes[0].enunciado)
        self.assertIn("Evolução histórica", questoes[0].legenda_figura)
        self.assertIn("Fonte: GBD, 2021", questoes[0].legenda_figura)

    def test_cabecalho_de_secao_colado_na_alternativa_e_removido(self):
        texto = """===== PÁGINA 1 =====
1
Este enunciado é suficientemente longo para testar o cabeçalho de seção.
(A) Alternativa A com conteúdo suficiente.
(B) Alternativa B com conteúdo suficiente.
(C) Alternativa C com conteúdo suficiente.
(D) Alternativa D com conteúdo suficiente.
(E) A avaliação de desempenho do agente público fica suspensa no período do teletrabalho, mesmo que sejam utilizadas as opções de status da ferramenta de comunicação da equipe. CONHECIMENTOS ESPECÍFICOS Eixo Temático 1 - Seguridade Social
"""
        questoes = parse_texto_bruto(texto)
        self.assertEqual(len(questoes), 1)
        self.assertNotIn("CONHECIMENTOS ESPECÍFICOS", questoes[0].alternativas["E"])
        self.assertNotIn("Eixo Temático", questoes[0].alternativas["E"])

    def test_legenda_multilinha_inteira_e_separada_do_enunciado(self):
        texto = """===== PÁGINA 1 =====
1
O estudo apresenta os resultados históricos de saúde pública.
Evolução histórica das taxas de mortalidade e DALY segundo sexo
e grupo de causa. Brasil, 1990-2019.
Fonte: GBD, 2021.
A partir dos dados apresentados, é correto concluir que:
(A) Alternativa A com conteúdo suficiente.
(B) Alternativa B com conteúdo suficiente.
(C) Alternativa C com conteúdo suficiente.
(D) Alternativa D com conteúdo suficiente.
(E) Alternativa E com conteúdo suficiente.
"""
        questoes = parse_texto_bruto(texto)
        self.assertNotIn("Evolução histórica", questoes[0].enunciado)
        self.assertNotIn("e grupo de causa", questoes[0].enunciado)
        self.assertIn("A partir dos dados apresentados", questoes[0].enunciado)
        self.assertIn("Evolução histórica", questoes[0].legenda_figura)
        self.assertIn("e grupo de causa", questoes[0].legenda_figura)
        self.assertIn("Fonte: GBD, 2021", questoes[0].legenda_figura)

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
