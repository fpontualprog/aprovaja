"""Importa CSVs de questões para o Supabase com upsert idempotente.

Configurar SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no ambiente.
Por segurança, a service-role key nunca deve ser gravada no repositório.
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path
from typing import Any

from supabase import create_client


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
BATCH_SIZE = 500

ALIASES = {
    "evento_url": ("evento_url", "evento", "concurso", "codigo_evento"),
    "numero": ("numero", "questao", "questão", "numero_questao", "número"),
    "enunciado": ("enunciado", "texto", "questao_texto", "questão_texto"),
    "texto_apoio": ("texto_apoio", "texto de apoio", "contexto"),
    "tipo": ("tipo", "tipo_questao", "tipo de questão"),
    "gabarito": ("gabarito", "resposta", "resposta_correta"),
    "disciplina": ("disciplina", "materia", "matéria", "subject"),
    "tem_imagem": ("tem_imagem", "possui_imagem", "has_image"),
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


def _bool(valor: Any) -> bool:
    return str(valor or "").strip().lower() in {"1", "true", "t", "sim", "yes", "y"}


def _registro(row: dict[str, Any], evento_padrao: str) -> dict[str, Any] | None:
    row = _normalizar_colunas(row)
    evento = str(_valor(row, "evento_url", evento_padrao)).strip()
    numero_bruto = _valor(row, "numero")
    enunciado = _valor(row, "enunciado")
    if not evento or numero_bruto is None or enunciado is None:
        return None

    try:
        numero = int(str(numero_bruto).strip())
    except (TypeError, ValueError):
        return None

    gabarito = _valor(row, "gabarito")
    gabarito = str(gabarito).strip().upper() if gabarito is not None else None
    if gabarito == "":
        gabarito = None
    if gabarito not in (None, "C", "E", "X"):
        # Não converte silenciosamente formatos desconhecidos.
        gabarito = None

    tipo = str(_valor(row, "tipo", "certo_errado")).strip() or "certo_errado"
    texto_apoio = _valor(row, "texto_apoio")
    disciplina = _valor(row, "disciplina")
    imagens = _valor(row, "imagens")
    return {
        "evento_url": evento,
        "numero": numero,
        "enunciado": str(enunciado).strip(),
        "texto_apoio": str(texto_apoio).strip() if texto_apoio is not None else None,
        "tipo": tipo,
        "gabarito": gabarito,
        "disciplina": str(disciplina).strip() if disciplina is not None else None,
        "tem_imagem": _bool(_valor(row, "tem_imagem", False)),
        "imagens": str(imagens).strip() if imagens is not None else None,
    }


def _csvs() -> list[Path]:
    selecionado = os.getenv("QUESTOES_CSV")
    if selecionado:
        path = Path(selecionado)
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file():
            raise FileNotFoundError(f"CSV definido em QUESTOES_CSV não encontrado: {path}")
        return [path]
    return sorted(p for p in DATA_DIR.glob("*.csv") if p.is_file())


def main() -> int:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERRO: configure SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY.", file=sys.stderr)
        return 2

    arquivos = _csvs()
    if not arquivos:
        print(f"Nenhum CSV encontrado em {DATA_DIR}.")
        return 0

    client = create_client(url, key)
    total_enviadas = total_invalidas = total_ignoradas = 0
    for arquivo in arquivos:
        evento_padrao = arquivo.stem
        registros = []
        with arquivo.open("r", encoding="utf-8-sig", newline="") as f:
            amostra = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(amostra, delimiters=",;\\t")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(f, dialect=dialect)
            for linha, row in enumerate(reader, start=2):
                registro = _registro(row, evento_padrao)
                if registro is None:
                    total_invalidas += 1
                    print(f"[AVISO] {arquivo.name}:{linha}: linha sem numero/enunciado válido; ignorada.")
                    continue
                registros.append(registro)

        for i in range(0, len(registros), BATCH_SIZE):
            lote = registros[i:i + BATCH_SIZE]
            response = client.table("questoes").upsert(
                lote, on_conflict="evento_url,numero"
            ).execute()
            total_enviadas += len(lote)
        total_ignoradas += 0
        print(f"{arquivo.name}: {len(registros)} registro(s) enviados em upsert.")

    print(
        f"Concluído: {total_enviadas} registro(s) enviados; "
        f"{total_invalidas} linha(s) inválidas ignoradas."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
