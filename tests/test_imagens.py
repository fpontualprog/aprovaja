from scripts.imagens import associar_imagens_paths, associar_imagens


def test_associar_imagens_paths_retorna_apenas_strings_no_intervalo():
    paginas = [
        {"pagina": 13, "blocos": [
            {"tipo": "imagem", "arquivo": "midias/imagem_013.png"},
        ]},
        {"pagina": 14, "blocos": [
            {"tipo": "imagem", "arquivo": "midias/imagem_014.png"},
            {"tipo": "texto", "texto": "texto ignorado"},
            {"tipo": "imagem", "arquivo": "midias/imagem_014.png"},
            {"tipo": "imagem", "arquivo": "midias/imagem_014b.png"},
        ]},
        {"pagina": 15, "blocos": [
            {"tipo": "imagem", "arquivo": "midias/imagem_015.png"},
        ]},
    ]

    paths = associar_imagens_paths({}, paginas, 14, 14)

    assert paths == ["midias/imagem_014.png", "midias/imagem_014b.png"]
    assert all(isinstance(path, str) for path in paths)


def test_associar_imagens_paths_retorna_lista_vazia_sem_imagens():
    paginas = [
        {"pagina": 14, "blocos": [
            {"tipo": "texto", "texto": "Não há imagem nesta página."},
            {"tipo": "imagem", "arquivo": ""},
        ]}
    ]

    assert associar_imagens_paths({}, paginas, 14, 14) == []


def test_associar_imagens_define_imagens_como_lista_de_paths():
    questao = {"enunciado": "Questão que menciona a figura abaixo."}
    paginas = [
        {"pagina": 14, "blocos": [
            {"tipo": "imagem", "arquivo": "midias/figura_014.png",
             "sha256": "abc123", "bbox": [10, 20, 100, 200]},
        ]}
    ]

    resultado = associar_imagens(questao, paginas, 14, 14)

    assert resultado["imagens"] == ["midias/figura_014.png"]
    assert all(isinstance(path, str) for path in resultado["imagens"])
    assert resultado["tem_imagem"] is True
    assert resultado["imagens_associadas"][0]["pagina"] == 14
    assert resultado["requer_conferencia_visual"] is True
