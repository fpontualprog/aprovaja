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
from imagens import associar_imagens, associar_imagens_paths
from validacao import validar_questao
from gabarito import cruzar_gabarito, parsear_gabarito

# Colunas confirmadas de public.questoes_globais. Campos com prefixo _ são locais.
COLUNAS_REAIS = {
    "evento_url", "numero", "enunciado", "texto_apoio", "disciplina",
    "tipo", "gabarito", "imagens", "formato_gabarito",
}

def montar_questao_canonica(numero: int, tipo: str, enunciado: str, texto_apoio: str | None, disciplina: str | None, gabarito: str | None, imagens: list[str], evento_url: str, pagina_inicio: int, pagina_fim: int, texto_bruto: str) -> dict[str, Any]:
    """Objeto canônico com campos do banco e metadados locais de revisão."""
    if tipo == "certo_errado":
        formato = "cebraspe"
    elif tipo == "multipla_escolha":
        formato = "multipla_escolha"
    else:
        formato = None
    return {
        "evento_url": evento_url, "numero": numero, "enunciado": enunciado,
        "texto_apoio": texto_apoio, "disciplina": disciplina, "tipo": tipo,
        "gabarito": gabarito, "imagens": list(imagens or []),
        "formato_gabarito": formato, "_pagina_inicio": pagina_inicio,
        "_pagina_fim": pagina_fim, "_texto_bruto": texto_bruto,
    }

def preparar_payload_supabase(questao: dict[str, Any]) -> dict[str, Any]:
    """Filtra metadados locais e valida as colunas obrigatórias do banco."""
    payload = {k: v for k, v in questao.items() if k in COLUNAS_REAIS}
    if questao.get("enunciado_supabase"):
        payload["enunciado"] = questao["enunciado_supabase"]
    if not isinstance(payload.get("imagens"), list) or any(not isinstance(path, str) for path in payload["imagens"]):
        raise ValueError("imagens deve ser uma lista de strings compatível com text[]")
    faltando = [k for k in ("evento_url", "numero", "enunciado", "tipo") if payload.get(k) in (None, "")]
    if faltando:
        raise ValueError(f"Payload inválido: faltam campos obrigatórios {faltando}")
    if not str(payload["evento_url"]).startswith(("https://", "http://")):
        raise ValueError("evento_url precisa ser a URL real HTTP/HTTPS da prova")
    return payload

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
        # Preserva alternativas no texto do banco; o objeto estruturado fica na revisão.
        if q.get("tipo") == "multipla_escolha" and q.get("alternativas"):
            alternativas_texto = "\\n".join(f'{a.get("letra", "")}) {a.get("texto", "")}'.strip() for a in q["alternativas"])
            q["enunciado_supabase"] = f'{q.get("enunciado", "").strip()}\\n{alternativas_texto}'.strip()
        else:
            q["enunciado_supabase"] = q.get("enunciado")
        q["imagens"] = associar_imagens_paths(q, paginas, inicio, fim)
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
