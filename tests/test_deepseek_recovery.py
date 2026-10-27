"""Testes de recuperação e preservação de itens na estruturação com IA."""
from types import SimpleNamespace

from src.structuring import deepseek


def resposta(questoes):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=__import__("json").dumps({"questoes": questoes})))],
    )


def test_recupera_lote_incompleto_sem_perder_itens(monkeypatch):
    chamadas = []

    class ClienteFake:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.criar))

        def criar(self, **kwargs):
            import json
            prompt = json.loads(kwargs["messages"][1]["content"])
            itens = prompt["itens"]
            chamadas.append([item["numero"] for item in itens])
            if len(itens) == 2:
                return resposta([{"numero": 1, "enunciado": "Questão 1 estruturada"}])
            if itens[0]["numero"] == 2:
                raise RuntimeError("falha simulada")
            return resposta([{"numero": itens[0]["numero"], "enunciado": itens[0]["texto"]}])

    monkeypatch.setenv("DEEPSEEK_API_KEY", "teste")
    monkeypatch.setattr(deepseek, "OpenAI", ClienteFake)
    itens = [
        {"numero": 1, "texto": "Texto original da questão número um, longo o suficiente."},
        {"numero": 2, "texto": "Texto original da questão número dois, longo o suficiente."},
    ]

    resultado = deepseek.estruturar_itens(itens, "Concurso teste")

    assert len(resultado) == 2
    assert resultado[0]["numero"] == 1
    assert resultado[1]["numero"] == 2
    assert resultado[1]["status_estruturacao"] == "pendente_revisao"
    assert resultado[1]["texto"] == itens[1]["texto"]
    assert resultado[1]["enunciado"] == itens[1]["texto"]
    assert chamadas == [[1, 2], [1], [2]]


def test_lista_vazia_nao_chama_api(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert deepseek.estruturar_itens([], "Concurso teste") == []
