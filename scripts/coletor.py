"""Orquestra parser FGV, imagens, gabarito e validação; não envia ao Supabase."""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from parser_fgv import segmentar_questoes, separar_alternativas
from imagens import associar_imagens
from validacao import validar_questao
from gabarito import cruzar_gabarito, parsear_gabarito

def _normalizar(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def localizar_paginas(texto_questao: str, paginas: list[dict[str, Any]], pagina_cursor: int = 1) -> tuple[int, int]:
    """Localiza páginas com base no início da questão; intervalo é estimado."""
    alvo = _normalizar(texto_questao)
    prefixo = alvo[:100]
    if prefixo:
        for i, pagina in enumerate(paginas):
            texto = _normalizar(str(pagina.get("texto", "")))
            if prefixo in texto:
                inicio = int(pagina.get("pagina", i + 1))
                # Se o bloco inteiro não cabe na página inicial, procura o fim
                # aproximado pela última ocorrência de trecho final nas páginas seguintes.
                sufixo = alvo[-80:]
                fim = inicio
                if sufixo:
                    for j in range(i, len(paginas)):
                        if sufixo in _normalizar(str(paginas[j].get("texto", ""))):
                            fim = int(paginas[j].get("pagina", j + 1))
                return inicio, fim
    return pagina_cursor, pagina_cursor

def coletar_prova(json_path: str, gabarito: dict[int, str] | None = None) -> list[dict[str, Any]]:
    caminho = Path(json_path)
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    paginas = dados.get("paginas", [])
    meta = dados.get("documento", {})
    if not paginas:
        raise ValueError(f"JSON sem páginas: {caminho}")
    texto_completo = "\n".join(str(p.get("texto", "")) for p in paginas)
    blocos = segmentar_questoes(texto_completo)
    questoes = [separar_alternativas(b) for b in blocos]
    cursor_pagina = int(paginas[0].get("pagina", 1))
    for q in questoes:
        inicio, fim = localizar_paginas(q.get("texto_bruto", ""), paginas, cursor_pagina)
        associar_imagens(q, paginas, inicio, fim)
        q["requer_conferencia_pagina"] = True
        cursor_pagina = max(cursor_pagina, fim)
    if gabarito is not None:
        cruzar_gabarito(questoes, gabarito)
    for q in questoes:
        status, motivos = validar_questao(q)
        q["status"] = status
        q["motivos_revisao"] = sorted(set(q.get("motivos_revisao", []) + motivos))
        q["documento_sha256"] = meta.get("sha256")
        q["fonte"] = meta.get("source") or meta.get("fonte")
        q["url_fonte"] = meta.get("url") or meta.get("url_origem")
        q["evento_url"] = meta.get("evento_url") or meta.get("url_origem") or meta.get("url")
        if q.get("tipo") == "certo_errado":
            q["formato_gabarito"] = "cebraspe"
        elif q.get("tipo") == "multipla_escolha":
            q["formato_gabarito"] = "multipla_escolha"
        else:
            q["formato_gabarito"] = None
    return questoes

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", type=Path)
    parser.add_argument("--gabarito-texto", type=Path, help="TXT extraído do gabarito oficial")
    parser.add_argument("--saida", type=Path, default=ROOT / "provas_data" / "revisao" / "questoes_fgv.json")
    args = parser.parse_args()
    gabarito = parsear_gabarito(args.gabarito_texto.read_text(encoding="utf-8")) if args.gabarito_texto else None
    questoes = coletar_prova(str(args.json_path), gabarito)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(questoes, ensure_ascii=False, indent=2), encoding="utf-8")
    prontas = sum(q.get("status") == "PRONTA_PARA_SUPABASE" for q in questoes)
    print(f"Questões extraídas: {len(questoes)}; prontas: {prontas}; quarentena: {len(questoes)-prontas}")
    print(f"Arquivo gerado: {args.saida}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
