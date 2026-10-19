#!/usr/bin/env python3
"""Conservative second-stage review for APROVAJÁ contest discovery.

Never writes to Supabase. RSS/news items remain candidates until a human confirms
an official notice, organizer and registration status.
"""
from __future__ import annotations
import csv, json, re, time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

BASE = Path("varredura_experimental_resultados")
INPUT = BASE / "candidatos_concursos.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; APROVAJA-Review/0.2; +https://github.com/fpontualprog/aprovaja)"}
TIMEOUT = 12
OFFICIAL_HINTS = re.compile(r"\.(gov\.br|jus\.br|leg\.br|edu\.br)$", re.I)
NOTICE_HINTS = re.compile(r"edital|concurso|processo.?seletivo|selecao|selecção|diario.?oficial", re.I)
OPEN_HINTS = re.compile(r"inscri.{0,20}(aberta|até|ate|prorrog)|per[ií]odo de inscri|inscri.{0,15}encerra", re.I)
CLOSED_HINTS = re.compile(r"inscri.{0,20}(encerrad|terminad|finaliz)|prazo.{0,15}encerrad", re.I)
OLD_RESULTS = re.compile(r"resultado final|gabarito definitivo|homologa.{0,15}resultado|convoca.{0,15}aprovados", re.I)
STOP = set("concurso concursos publico públicos publica pública processo seletivo edital prefeitura governo vagas vaga inscrições inscricoes abertas aberto 2026 2027".split())

def norm(s):
    s = (s or "").lower()
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"[^a-z0-9áéíóúâêôãõç]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def tokens(s):
    return {t for t in norm(s).split() if len(t) > 2 and t not in STOP}

def domain(url):
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""

def official_domain(url):
    d = domain(url)
    return bool(OFFICIAL_HINTS.search(d))

def main():
    if not INPUT.exists():
        raise SystemExit(f"Arquivo não encontrado: {INPUT}; execute primeiro varredura_experimental.py")
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    rows = payload.get("candidatos", [])
    # Merge duplicates when titles are identical after normalization or have high token overlap.
    groups = []
    for row in rows:
        ts = tokens(row.get("titulo", ""))
        match = None
        for group in groups:
            base = group["tokens"]
            overlap = len(ts & base) / max(1, len(ts | base))
            if norm(row.get("titulo")) == group["norm"] or overlap >= 0.82:
                match = group
                break
        if match is None:
            groups.append({"norm": norm(row.get("titulo")), "tokens": ts, "rows": [row]})
        else:
            match["rows"].append(row)
            match["tokens"] |= ts

    session = requests.Session()
    review = []
    for idx, group in enumerate(groups, 1):
        # Prefer a discovery link with an accessible page; do not assume news links are official.
        variants = sorted(group["rows"], key=lambda x: (bool(x.get("url_descoberta")), len(x.get("descricao") or "")), reverse=True)
        best = variants[0]
        found_links = []
        page_status = "nao_testado"
        page_title = ""
        text_sample = ""
        for candidate in variants[:3]:
            url = candidate.get("url_descoberta") or ""
            if not url.startswith("http"):
                continue
            try:
                resp = session.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
                page_status = f"http_{resp.status_code}"
                if resp.status_code >= 400 or "text/html" not in resp.headers.get("content-type", ""):
                    continue
                soup = BeautifulSoup(resp.text[:2_000_000], "html.parser")
                page_title = (soup.title.get_text(" ", strip=True) if soup.title else "")[:250]
                text_sample = soup.get_text(" ", strip=True)[:15000]
                for a in soup.find_all("a", href=True):
                    label = a.get_text(" ", strip=True)
                    href = urljoin(resp.url, a["href"])
                    if NOTICE_HINTS.search(label + " " + href) and official_domain(href):
                        found_links.append({"texto_link": label[:160], "url": href, "dominio_oficial": domain(href)})
                break
            except Exception as exc:
                page_status = "falha_acesso"
        # Unique official links only.
        dedup = {}
        for link in found_links:
            dedup[link["url"]] = link
        found_links = list(dedup.values())[:20]
        combined = " ".join([best.get("titulo", ""), best.get("descricao") or "", page_title, text_sample])
        signals_open = bool(OPEN_HINTS.search(combined))
        signals_closed = bool(CLOSED_HINTS.search(combined))
        if OLD_RESULTS.search(best.get("titulo", "")):
            status = "provavel_resultado_antigo"
        elif found_links:
            status = "fonte_oficial_encontrada_revisao_humana"
        else:
            status = "aguardando_validacao_oficial"
        review.append({
            "titulo": best.get("titulo"),
            "url_descoberta": best.get("url_descoberta"),
            "fonte_publicadora": best.get("fonte_publicadora"),
            "data_publicacao": best.get("data_publicacao"),
            "quantidade_fontes_duplicadas": len(group["rows"]),
            "urls_descoberta_relacionadas": " | ".join(dict.fromkeys(x.get("url_descoberta", "") for x in group["rows"] if x.get("url_descoberta"))),
            "status_validacao": status,
            "status_http_fonte": page_status,
            "titulo_pagina_acessada": page_title,
            "links_oficiais_candidatos": json.dumps(found_links, ensure_ascii=False),
            "sinal_inscricao_aberta_no_texto": signals_open,
            "sinal_inscricao_encerrada_no_texto": signals_closed,
            "edital_url_confirmado": None,
            "banca_url_confirmada": None,
            "inscricoes_abertas_confirmadas": False,
            "acao_recomendada": "Conferir edital e página de inscrição no órgão oficial antes de publicar",
        })
        if idx % 50 == 0:
            print(f"Revisados {idx}/{len(groups)} grupos...")
        time.sleep(0.15)

    review.sort(key=lambda x: (x["status_validacao"] != "fonte_oficial_encontrada_revisao_humana", x["titulo"] or ""))
    report = {
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
        "modo": "somente_leitura_sem_supabase",
        "candidatos_originais": len(rows),
        "grupos_apos_deduplicacao": len(groups),
        "grupos_com_mais_de_uma_fonte": sum(1 for g in groups if len(g["rows"]) > 1),
        "fontes_oficiais_candidatas_encontradas": sum(1 for x in review if x["status_validacao"] == "fonte_oficial_encontrada_revisao_humana"),
        "inscricoes_abertas_confirmadas": 0,
        "aviso": "Links oficiais são candidatos encontrados em páginas de notícias, não confirmação de edital ou inscrições. Nenhum registro foi enviado ao Supabase.",
        "candidatos": review,
    }
    (BASE / "relatorio_validacao.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (BASE / "fila_revisao.csv").open("w", newline="", encoding="utf-8-sig") as f:
        fields = list(review[0].keys()) if review else ["titulo", "status_validacao"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(review)
    print(json.dumps({k: report[k] for k in report if k != "candidatos"}, ensure_ascii=False, indent=2))
    print("Arquivos gerados: relatorio_validacao.json e fila_revisao.csv. Supabase não foi alterado.")

if __name__ == "__main__":
    main()
