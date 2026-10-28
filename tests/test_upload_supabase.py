from scripts.upload_supabase import _registro


def test_fgv_alternativa_a_com_formato_multipla_escolha():
    row = {
        "url_origem": "https://banca.example/prova.pdf",
        "numero": "1",
        "enunciado": "Enunciado de teste com tamanho suficiente",
        "tipo": "multipla_escolha",
        "gabarito": "A",
    }
    registro = _registro(row)
    assert registro is not None
    assert registro["evento_url"] == "https://banca.example/prova.pdf"
    assert registro["gabarito"] == "A"
    assert registro["formato_gabarito"] == "multipla_escolha"
    assert set(registro).issubset({
        "evento_url", "numero", "enunciado", "texto_apoio", "disciplina",
        "tipo", "gabarito", "formato_gabarito", "imagens",
    })


def test_cebraspe_certo_errado():
    row = {
        "evento_url": "https://banca.example/cebraspe.pdf",
        "numero": "2",
        "enunciado": "Enunciado CEBRASPE de teste",
        "tipo": "certo_errado",
        "gabarito": "C",
    }
    registro = _registro(row)
    assert registro is not None
    assert registro["gabarito"] == "C"
    assert registro["formato_gabarito"] == "cebraspe"


def test_gabarito_incompativel_com_formato_e_rejeitado():
    row = {
        "evento_url": "https://banca.example/cebraspe.pdf",
        "numero": "3",
        "enunciado": "Enunciado de teste com formato incompatível",
        "tipo": "certo_errado",
        "gabarito": "A",
    }
    assert _registro(row) is None


def test_url_real_e_obrigatoria():
    row = {
        "evento": "PF_25_ADM",
        "numero": "4",
        "enunciado": "Enunciado sem URL real da prova",
        "tipo": "certo_errado",
        "gabarito": "C",
    }
    assert _registro(row) is None


def test_questao_sem_gabarito_pode_entrar_em_revisao():
    row = {
        "url_origem": "https://banca.example/prova.pdf",
        "numero": "5",
        "enunciado": "Enunciado aguardando o gabarito oficial",
        "tipo": "certo_errado",
        "gabarito": "",
    }
    registro = _registro(row)
    assert registro is not None
    assert registro["gabarito"] is None
    assert registro["formato_gabarito"] == "cebraspe"


def test_tipo_ausente_e_rejeitado_para_nao_assumir_cebraspe():
    row = {
        "evento_url": "https://banca.example/prova.pdf",
        "numero": "6",
        "enunciado": "Enunciado sem tipo explícito",
        "gabarito": "A",
    }
    assert _registro(row) is None
