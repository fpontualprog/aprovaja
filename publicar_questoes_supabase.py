#!/usr/bin/env python3
"""Envia candidatos de provas para a fila de importação do APROVAJÁ, agrupados por PDF."""
from __future__ import annotations
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
import requests

INPUT = Path("provas_data/revisao/questoes_candidatas.json")

def main() -> int:
    base_url = os.environ.get("APROVAJA_SUPABASE_URL", "").rstrip("/")
    secret = os.environ.get("APROVAJA_IMPORT_SECRET", "")
    if not base_url or not secret:
        missing = []
        if not base_url:
            missing.append("APROVAJA_SUPABASE_URL")
        if not secret:
            missing.append("APROVAJA_IMPORT_SECRET")
        print("ERRO: integração Supabase não configurada: " + ", ".join(missing) + ". O lote não foi enviado.", file=sys.stderr)
        return 2
    if not INPUT.exists():
        print(f"Arquivo de candidatos não encontrado: {INPUT}", file=sys.stderr)
        return 2

    data = json.loads(INPUT.read_text(encoding="utf-8"))
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in data.get("candidatos", []):
        sha = str(item.get("documento_sha256") or "").lower()
        if len(sha) == 64 and all(c in "0123456789abcdef" for c in sha):
            groups[sha].append(item)
    if not groups:
        print("Nenhum candidato vinculado a um PDF com SHA-256 válido; nada foi enviado.")
        return 0

    endpoint = f"{base_url}/functions/v1/importar-questoes-pdf"
    headers = {
        "Content-Type": "application/json",
        "x-aprovaja-import-secret": secret,
    }
    session = requests.Session()
    successes = failures = sent = 0
    for sha, items in groups.items():
        first = items[0]
        batch = {
            "arquivo_sha256": sha,
            "nome_arquivo": first.get("arquivo_pdf") or f"prova-{sha[:12]}.pdf",
            "fonte": first.get("fonte"),
            "url_fonte": first.get("url_fonte"),
        }
        # A Edge Function limita cada chamada a 500 candidatos. Reenvios são idempotentes.
        for start in range(0, len(items), 500):
            payload = {"batch": batch, "items": items[start:start + 500]}
            try:
                response = session.post(endpoint, json=payload, headers=headers, timeout=90)
                if response.ok:
                    result = response.json()
                    summary = result.get("resumo", {})
                    print(json.dumps({
                        "arquivo_sha256": sha,
                        "lote_id": result.get("lote_id"),
                        "status": result.get("status"),
                        "resumo": summary,
                    }, ensure_ascii=False))
                    successes += 1
                    sent += len(payload["items"])
                else:
                    print(f"Falha ao enviar {sha[:12]}: HTTP {response.status_code} - {response.text[:500]}", file=sys.stderr)
                    failures += 1
            except requests.RequestException as exc:
                print(f"Falha de conexão ao enviar {sha[:12]}: {exc}", file=sys.stderr)
                failures += 1
            time.sleep(0.2)

    print(json.dumps({"chamadas_ok": successes, "falhas": failures, "candidatos_enviados": sent}, ensure_ascii=False))
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
