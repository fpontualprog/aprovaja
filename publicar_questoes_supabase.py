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
    total = 0
    rejected_no_key = 0
    rejected_unverified = 0
    for item in data.get("candidatos", []):
        total += 1
        # Regra rígida: somente respostas extraídas de gabarito oficial com confiança alta.
        answer = str(item.get("gabarito") or "").strip().upper()
        source = str(item.get("gabarito_fonte_oficial") or "").strip()
        status = str(item.get("gabarito_status") or "")
        confidence = str(item.get("gabarito_confianca") or "").lower()
        if not answer:
            rejected_no_key += 1
            continue
        if confidence != "alta" or not (source or status in {"EXTRAIDO_DOCUMENTO_ORIGINAL", "EXTRAIDO_GABARITO_SEPARADO_COMPATIVEL"}):
            rejected_unverified += 1
            continue
        if answer not in {"A", "B", "C", "D", "E", "C", "E", "ANULADA"}:
            rejected_unverified += 1
            continue
        sha = str(item.get("documento_sha256") or "").lower()
        if len(sha) == 64 and all(c in "0123456789abcdef" for c in sha):
            groups[sha].append(item)
    accepted = sum(len(items) for items in groups.values())
    print(json.dumps({"candidatos_total": total, "aceitos_com_gabarito_oficial": accepted,
                      "bloqueados_sem_gabarito": rejected_no_key,
                      "bloqueados_sem_confirmacao_oficial": rejected_unverified}, ensure_ascii=False))
    if not groups:
        print("BLOQUEADO: nenhum candidato tem gabarito oficial confirmado. Nada foi enviado ao Supabase.", file=sys.stderr)
        return 1

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
                    persistence = result.get("persistencia") or {}
                    valid_response = (
                        bool(result.get("trace_id"))
                        and bool(result.get("lote_id"))
                        and isinstance(summary, dict)
                        and persistence.get("verificada") is True
                        and persistence.get("atualizacao_lote_confirmada") is True
                        and isinstance(persistence.get("itens_no_lote"), int)
                        and int(summary.get("erros", -1)) == 0
                    )
                    print(json.dumps({
                        "arquivo_sha256": sha,
                        "trace_id": result.get("trace_id"),
                        "lote_id": result.get("lote_id"),
                        "status": result.get("status"),
                        "resumo": summary,
                        "persistencia": persistence,
                        "validacao_persistencia": valid_response,
                    }, ensure_ascii=False))
                    if valid_response:
                        successes += 1
                        sent += len(payload["items"])
                    else:
                        print(f"Resposta HTTP {response.status_code}, mas persistência não foi confirmada para {sha[:12]}. Corpo: {response.text[:1000]}", file=sys.stderr)
                        failures += 1
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
