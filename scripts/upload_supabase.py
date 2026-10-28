"""Importa questões de CSV para public.questoes_globais, respeitando o schema real.

O upload usa evento_url + numero como chave de idempotência e envia somente
colunas existentes na tabela. Nunca coloque SUPABASE_SERVICE_ROLE_KEY no repo.
"""
from __future__ import annotations

import ast
import csv
import os
import sys
import traceback
from pathlib import Path
from typing import Any

from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
BATCH_SIZE = 500

ALIASES = {
    "evento_url": ("evento_url", "url_origem", "url_fonte", "source_url", "url_prova", "url"),
    "numero": ("numero", "questao", "questão", "numero_questao", "número"),
    "enunciado": ("enunciado", "texto", "questao_texto", "questão_texto"),
    "texto_apoio": ("texto_apoio", "texto de apoio", "contexto"),
    "tipo": ("tipo", "tipo_questao", "tipo de questão"),
    "formato_gabarito": ("formato_gabarito", "formato gabarito", "formato_resposta"),
    "gabarito": ("gabarito", "resposta", "resposta_correta"),
    "disciplina": ("disciplina", "materia", "matéria", "subject"),
    "imagens": ("imagens", "caminhos_imagens", "images"),
}


def _normalizar_colunas(row: dict[str, Any]) -> dict[str, Any]:
    return {str(k).strip().lower(): v for k, v in row.items() if k is not None}


def _valor(row: dict[str, Any], campo: str, padrao: Any = None) -> Any:
    for nome in ALIASES[campo]:
        valor = row.get(nome.lower())
        if valor is not None and str(valor).strip() != "":
            return valor
    return padrao


def _imagens(valor: Any) -> list[str]:
    if valor is None or str(valor).strip() == "":
        return []
    texto = str(valor).strip()
    if texto.startswith("[") and texto.endswith("]"):
        try:
            parsed = ast.literal_eval(texto)
            if isinstance(parsed, (list, tuple)):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (ValueError, SyntaxError):
            pass
    return [item.strip().strip('"').strip("'") for item in texto.split(",") if item.strip().strip('"').strip("'")]


def _registro(row: dict[str, Any], evento_padrao: str = "") -> dict[str, Any] | None:
    row = _normalizar_colunas(row)
    evento_valor = _valor(row, "evento_url", evento_padrao)
    evento = str(evento_valor or "").strip()
    numero_bruto = _valor(row, "numero")
    enunciado = _valor(row, "enunciado")
    # A chave do banco exige URL real da prova; não inventar URL com o nome do CSV.
    if not evento.startswith(("https://", "http://")) or numero_bruto is None or enunciado is None or not str(enunciado).strip():
        return None
    try:
        numero = int(str(numero_bruto).strip())
    except (TypeError, ValueError):
        return None
    if numero < 1:
        return None

    tipo_bruto = _valor(row, "tipo")
    # Não assumir CEBRASPE por omissão: isso classificaria questões FGV incorretamente.
    if tipo_bruto is None or not str(tipo_bruto).strip():
        return None
    tipo = str(tipo_bruto).strip().lower()
    formato_bruto = _valor(row, "formato_gabarito")
    formato = str(formato_bruto).strip().lower() if formato_bruto is not None else ""
    if not formato:
        if tipo in ("multipla_escolha", "múltipla escolha", "multipla escolha", "multiple_choice"):
            formato = "multipla_escolha"
        elif tipo in ("certo_errado", "certo/errado", "certo errado", "cebraspe"):
            formato = "cebraspe"

    gabarito_bruto = _valor(row, "gabarito")
    gabarito = str(gabarito_bruto).strip().upper() if gabarito_bruto is not None else None
    if gabarito == "":
        gabarito = None

    if gabarito is not None:
        if formato == "cebraspe" and gabarito not in ("C", "E", "X"):
            return None
        if formato == "multipla_escolha" and gabarito not in ("A", "B", "C", "D", "E"):
            return None
        if formato not in ("cebraspe", "multipla_escolha"):
            return None

    texto_apoio = _valor(row, "texto_apoio")
    disciplina = _valor(row, "disciplina")
    return {
        "evento_url": evento,
        "numero": numero,
        "enunciado": str(enunciado).strip(),
        "texto_apoio": str(texto_apoio).strip() if texto_apoio is not None and str(texto_apoio).strip() else None,
        "disciplina": str(disciplina).strip() if disciplina is not None and str(disciplina).strip() else None,
        "tipo": tipo,
        "gabarito": gabarito,
        "formato_gabarito": formato or None,
        "imagens": _imagens(_valor(row, "imagens")),
    }


def _arquivo_csv() -> Path | None:
    selecionado = os.getenv("QUESTOES_CSV")
    print(f"[CSV] Diretório esperado: {DATA_DIR}")
    encontrados_agora = sorted(DATA_DIR.glob("*.csv")) if DATA_DIR.exists() else []
    print(f"[CSV] CSVs encontrados em data/: {[p.name for p in encontrados_agora]}")
    if selecionado:
        path = Path(selecionado)
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file():
            raise FileNotFoundError(f"CSV de QUESTOES_CSV não encontrado: {path}")
        return path

    candidatos = [DATA_DIR / "PF_25_ADM.csv", DATA_DIR / "PF_25_ADM_questoes.csv"]
    for candidato in candidatos:
        if candidato.is_file():
            return candidato
    encontrados = sorted(DATA_DIR.glob("*.csv"))
    return encontrados[0] if encontrados else None


def main() -> int:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERRO: configure SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY.", file=sys.stderr)
        return 2

    arquivo = _arquivo_csv()
    if arquivo is None:
        print(f"ERRO: nenhum CSV encontrado em {DATA_DIR}.", file=sys.stderr)
        return 2

    print(f"[CSV] Arquivo selecionado: {arquivo}")
    print(f"[CSV] Tamanho: {arquivo.stat().st_size} bytes")
    registros: list[dict[str, Any]] = []
    invalidas = 0
    formatos = {"cebraspe": 0, "multipla_escolha": 0, "sem_gabarito": 0}
    with arquivo.open("r", encoding="utf-8-sig", newline="") as f:
        amostra = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(amostra, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        leitor = csv.DictReader(f, dialect=dialect)
        print(f"[CSV] Colunas detectadas: {leitor.fieldnames}")
        linhas_lidas = 0
        for linha, row in enumerate(leitor, start=2):
            linhas_lidas += 1
            registro = _registro(row)
            if registro is None:
                invalidas += 1
                print(f"[AVISO] {arquivo.name}:{linha}: linha inválida ou incompatível com o schema, ignorada.")
                continue
            if registro["gabarito"] is None:
                formatos["sem_gabarito"] += 1
            elif registro["formato_gabarito"] in formatos:
                formatos[registro["formato_gabarito"]] += 1
            registros.append(registro)

    print(f"[CSV] Linhas de dados lidas: {linhas_lidas}")
    print(f"[CSV] Registros válidos preparados: {len(registros)}")
    print(f"[CSV] Linhas inválidas ignoradas: {invalidas}")
    print(f"[CSV] Distribuição dos registros: {formatos}")
    if not registros:
        print(f"ERRO: nenhum registro válido encontrado em {arquivo}.", file=sys.stderr)
        return 2

    client = create_client(url, key)
    enviados = 0
    for inicio in range(0, len(registros), BATCH_SIZE):
        lote = registros[inicio:inicio + BATCH_SIZE]
        print(f"[SUPABASE] Tentando enviar lote {inicio // BATCH_SIZE + 1} com {len(lote)} registro(s); total planejado={len(registros)}.")
        try:
            client.table("questoes_globais").upsert(lote, on_conflict="evento_url,numero").execute()
            enviados += len(lote)
            print(f"[SUPABASE] Lote concluído. Total processado: {enviados}.")
        except Exception as exc:
            print(f"[SUPABASE][ERRO] Tipo: {type(exc).__name__}; mensagem: {exc}", file=sys.stderr)
            traceback.print_exc()
            return 3

    print(f"Concluído: {enviados} questão(ões) processadas de {arquivo.name}; {invalidas} linha(s) inválidas ignoradas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
