"""Testes da busca web de gabaritos com restrição ao domínio oficial."""
from types import SimpleNamespace

from src.discovery import cebraspe


def test_busca_web_aceita_pdf_oficial_e_rejeita_dominio_terceiro(monkeypatch):
    html = """
    <html><body>
      <a class="result__a" href="https://cdn.cebraspe.org.br/concursos/pf_25/arquivos/gabarito_definitivo.pdf">Gabarito definitivo PF</a>
      <a class="result__a" href="https://exemplo.com/gabarito.pdf">Gabarito espelho</a>
      <a class="result__a" href="https://cdn.cebraspe.org.br/concursos/pf_25/arquivos/prova.pdf">Prova objetiva</a>
    </body></html>
    """

    class Response:
        text = html
        def raise_for_status(self):
            return None

    monkeypatch.setattr(cebraspe.SESSION, "get", lambda *args, **kwargs: Response())
    resultados = cebraspe.buscar_gabaritos_web_oficial("pf_25", "Polícia Federal 2025")

    assert len(resultados) == 1
    assert resultados[0]["url"] == "https://cdn.cebraspe.org.br/concursos/pf_25/arquivos/gabarito_definitivo.pdf"
    assert resultados[0]["descoberto_por"] == "busca_web_restrita_cebraspe"
    assert resultados[0]["fonte_oficial"] == "true"


def test_busca_web_retorna_lista_vazia_sem_evento():
    assert cebraspe.buscar_gabaritos_web_oficial("  ") == []
