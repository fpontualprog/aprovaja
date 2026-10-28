from scripts.coletor import COLUNAS_REAIS, montar_questao_canonica, preparar_payload_supabase


def test_payload_canonico_fgv_so_contem_colunas_reais():
    q = montar_questao_canonica(
        numero=56, tipo="multipla_escolha",
        enunciado="Enunciado de teste da Q56", texto_apoio=None,
        disciplina="Assistência Social", gabarito="C", imagens=[],
        evento_url="https://conhecimento.fgv.br/sites/default/files/concursos/b1102.pdf",
        pagina_inicio=18, pagina_fim=18, texto_bruto="texto bruto",
    )
    payload = preparar_payload_supabase(q)
    assert set(payload) == COLUNAS_REAIS
    assert payload["tipo"] == "multipla_escolha"
    assert payload["formato_gabarito"] == "multipla_escolha"
    assert payload["gabarito"] == "C"
    assert payload["imagens"] == []
    assert "id" not in payload and "criado_em" not in payload
    assert "_texto_bruto" not in payload


def test_payload_rejeita_url_que_nao_e_url():
    q = montar_questao_canonica(
        numero=1, tipo="certo_errado", enunciado="Enunciado",
        texto_apoio=None, disciplina=None, gabarito='C', imagens=[],
        evento_url="PF_25_ADM", pagina_inicio=1, pagina_fim=1, texto_bruto="x",
    )
    try:
        preparar_payload_supabase(q)
    except ValueError as exc:
        assert "URL real" in str(exc)
    else:
        raise AssertionError("Esperava rejeição de evento_url sem URL real")