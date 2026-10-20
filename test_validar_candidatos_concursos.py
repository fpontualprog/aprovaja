import unittest
from validar_candidatos_concursos import (
    domain, official_domain, is_social_or_share, is_generic_destination,
    norm, tokens, OPEN_HINTS, CLOSED_HINTS, OLD_RESULTS,
)

class ValidatorRulesTests(unittest.TestCase):
    def test_extracts_domain(self):
        self.assertEqual(domain("https://www.exemplo.gov.br/editais/123"), "exemplo.gov.br")

    def test_official_domains(self):
        self.assertTrue(official_domain("https://www.prefeitura.gov.br/concursos"))
        self.assertTrue(official_domain("https://tribunal.jus.br/edital"))
        self.assertFalse(official_domain("https://concursos-exemplo.com.br/edital"))

    def test_rejects_social_networks(self):
        for url in (
            "https://www.instagram.com/p/abc/",
            "https://www.facebook.com/share/abc",
            "https://youtu.be/abc",
            "https://x.com/perfil",
        ):
            with self.subTest(url=url):
                self.assertTrue(is_social_or_share(url))

    def test_rejects_generic_homepages_and_login(self):
        self.assertTrue(is_generic_destination("https://prefeitura.gov.br", "Prefeitura"))
        self.assertTrue(is_generic_destination("https://portal.com/login", "Entrar"))
        self.assertFalse(is_generic_destination("https://portal.com/concursos/edital-123", "Edital 123"))

    def test_normalization_and_tokens(self):
        self.assertEqual(norm("Concurso Público — 2026!"), "concurso público 2026")
        self.assertIn("universidade", tokens("Concurso da Universidade Federal"))

    def test_open_and_closed_signals_are_distinct(self):
        self.assertTrue(OPEN_HINTS.search("Inscrições abertas até 30 de outubro"))
        self.assertTrue(CLOSED_HINTS.search("Inscrições encerradas"))
        self.assertFalse(CLOSED_HINTS.search("Inscrições abertas até 30 de outubro"))

    def test_old_result_signals(self):
        self.assertTrue(OLD_RESULTS.search("Resultado final do concurso publicado"))
        self.assertFalse(OLD_RESULTS.search("Edital de abertura publicado"))

if __name__ == "__main__":
    unittest.main(verbosity=2)
