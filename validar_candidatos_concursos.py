#!/usr/bin/env python3
"""Conservative second-stage review for APROVAJÁ; read-only, no Supabase writes."""
from __future__ import annotations
import csv, json, re, time, html
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
import requests
from bs4 import BeautifulSoup

BASE = Path("varredura_experimental_resultados")
INPUT = BASE / "candidatos_concursos.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; APROVAJA-Review/0.3)"}
TIMEOUT = 8
OFFICIAL_HINTS = re.compile(r"\.(gov\.br|jus\.br|leg\.br|edu\.br)$", re.I)
NOTICE_HINTS = re.compile(r"edital|concurso|processo.?seletivo|selecao|diario.?oficial", re.I)
OPEN_HINTS = re.compile(r"inscri.{0,25}(aberta|até|ate|prorrog)|per[ií]odo de inscri|inscri.{0,20}encerra", re.I)
CLOSED_HINTS = re.compile(r"inscri.{0,25}(encerrad|terminad|finaliz)|prazo.{0,20}encerrad", re.I)
OLD_RESULTS = re.compile(r"resultado final|gabarito definitivo|homologa.{0,20}resultado|convoca.{0,20}aprovados", re.I)
STOP = set("concurso concursos publico públicos publica pública processo seletivo edital prefeitura governo vagas vaga inscrições inscricoes abertas aberto 2026 2027".split())
GOOGLE_HOSTS = ("news.google.com", "google.com", "www.google.com")

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
    return bool(OFFICIAL_HINTS.search(domain(url)))

def external_article_links(soup, base_url):
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, html.unescape(a["href"]))
        d = domain(href)
        if href.startswith("http") and d and not any(d == x or d.endswith("." + x) for x in GOOGLE_HOSTS):
            links.append(href)
    # Google News pages sometimes embed the publisher URL in metadata/JSON rather than an anchor.
    for tag in soup.find_all(["meta", "link"]):
        val = tag.get("content") or tag.get("href") or ""
        val = html.unescape(val)
        if val.startswith("http") and domain(val) and not any(domain(val) == x or domain(val).endswith("." + x) for x in GOOGLE_HOSTS):
            links.append(val)
    return list(dict.fromkeys(links))[:8]

def fetch_page(session, url):
    try:
        resp = session.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code >= 400 or "html" not in resp.headers.get("content-type", "").lower():
            return None, f"http_{resp.status_code}", None, ""
        soup = BeautifulSoup(resp.text[:2_000_000], "html.parser")
        title = soup.title.get_text(" ", strip=True)[:250] if soup.title else ""
        text = soup.get_text(" ", strip=True)[:18000]
        return (resp.url, soup, title, text), f"http_{resp.status_code}", soup, text
    except Exception:
        return None, "falha_acesso", None, ""

def main():
    if not INPUT.exists():
        raise SystemExit(f"Arquivo não encontrado: {INPUT}; execute primeiro varredura_experimental.py")
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    rows = payload.get("candidatos", [])
    # Conservative deduplication: exact normalized title or high Jaccard token similarity.
    groups = []
    for row in rows:
        ts = tokens(row.get("titulo", ""))
        n = norm(row.get("titulo", ""))
        match = None
        for group in groups:
            overlap = len(ts & group["tokens"]) / max(1, len(ts | group["tokens"]))
            if n == group["norm"] or (len(ts) >= 4 and overlap >= 0.82):
                match = group
                break
        if match is None:
            groups.append({"norm": n, "tokens": ts, "rows": [row]})
        else:
            match["rows"].append(row)
            match["tokens"] |= ts

    session = requests.Session()
    review = []
    for idx, group in enumerate(groups, 1):
        variants = sorted(group["rows"], key=lambda x: len(x.get("descricao") or ""), reverse=True)
        best = variants[0]
        official, publisher_url, page_status, page_title, combined_text = {}, None, "nao_testado", "", ""
        # Try a few distinct discovery URLs, first to unwrap Google News and then inspect the publisher page.
        for candidate in variants[:2]:
            src = candidate.get("url_descoberta") or ""
            if not src.startswith("http"):
                continue
            result, stat, soup, text = fetch_page(session, src)
            page_status = stat
            if not result:
                continue
            final_url, soup, title, text = result
            page_title = title or page_title
            combined_text += " " + text
            if domain(final_url) and not any(domain(final_url) == x or domain(final_url).endswith("." + x) for x in GOOGLE_HOSTS):
                publisher_url = final_url
            links = external_article_links(soup, final_url)
            # If Google News provides an external publisher link, visit it directly.
            for link in links[:3]:
                if publisher_url and domain(link) == domain(publisher_url):
                    continue
                res2, stat2, soup2, text2 = fetch_page(session, link)
                if not res2:
                    continue
                final2, soup2, title2, text2 = res2
                if not any(domain(final2) == x or domain(final2).endswith("." + x) for x in GOOGLE_HOSTS):
                    publisher_url = final2
                    page_title = title2 or page_title
                    combined_text += " " + text2
                    for a in soup2.find_all("a", href=True):
                        label = a.get_text(" ", strip=True)
                        href = urljoin(final2, a["href"])
                        if official_domain(href) and NOTICE_HINTS.search(label + " " + href):
                            official[href] = {"texto_link": label[:160], "url": href, "dominio_oficial": domain(href)}
                    # Also consider canonical links to official documents.
                    for tag in soup2.find_all(["link", "meta"]):
                        val = tag.get("href") or tag.get("content") or ""
                        href = urljoin(final2, val)
                        if official_domain(href) and NOTICE_HINTS.search(href):
                            official[href] = {"texto_link": "metadado/canonical", "url": href, "dominio_oficial": domain(href)}
                    break
            if official or publisher_url:
                break
        combined_text = " ".join([best.get("titulo", ""), best.get("descricao") or "", page_title, combined_text])
        is_old = bool(OLD_RESULTS.search(best.get("titulo", "")))
        status = "provavel_resultado_antigo" if is_old else ("fonte_oficial_candidata_revisao_humana" if official else ("pagina_publicadora_localizada_revisao_humana" if publisher_url else "nao_conseguiu_resolver_noticia"))
        review.append({
            "titulo": best.get("titulo"),
            "url_descoberta": best.get("url_descoberta"),
            "url_publicadora_resolvida": publisher_url,
            "fonte_publicadora": best.get("fonte_publicadora"),
            "data_publicacao": best.get("data_publicacao"),
            "quantidade_fontes_duplicadas": len(group["rows"]),
            "urls_descoberta_relacionadas": " | ".join(dict.fromkeys(x.get("url_descoberta", "") for x in group["rows"] if x.get("url_descoberta"))),
            "status_validacao": status,
            "status_http_fonte": page_status,
            "titulo_pagina_acessada": page_title,
            "links_oficiais_candidatos": json.dumps(list(official.values())[:20], ensure_ascii=False),
            "sinal_inscricao_aberta_no_texto": bool(OPEN_HINTS.search(combined_text)),
            "sinal_inscricao_encerrada_no_texto": bool(CLOSED_HINTS.search(combined_text)),
            "edital_url_confirmado": None,
            "banca_url_confirmada": None,
            "inscricoes_abertas_confirmadas": False,
            "acao_recomendada": "Conferir manualmente o edital e a página de inscrição no órgão oficial antes de publicar",
        })
        if idx % 50 == 0:
            print(f"Revisados {idx}/{len(groups)} grupos...")
        time.sleep(0.08)

    review.sort(key=lambda x: (x["status_validacao"] not in ("fonte_oficial_candidata_revisao_humana", "pagina_publicadora_localizada_revisao_humana"), x["titulo"] or ""))
    report = {
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
        "modo": "somente_leitura_sem_supabase",
        "candidatos_originais": len(rows),
        "grupos_apos_deduplicacao": len(groups),
        "grupos_com_mais_de_uma_fonte": sum(1 for g in groups if len(g["rows"]) > 1),
        "paginas_publicadoras_resolvidas": sum(1 for x in review if x["url_publicadora_resolvida"]),
        "fontes_oficiais_candidatas_encontradas": sum(1 for x in review if x["status_validacao"] == "fonte_oficial_candidata_revisao_humana"),
        "inscricoes_abertas_confirmadas": 0,
        "aviso": "Links e sinais são candidatos para revisão humana, não confirmação de edital ou inscrições. Nenhum registro foi enviado ao Supabase.",
        "candidatos": review,
    }
    (BASE / "relatorio_validacao.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (BASE / "fila_revisao.csv").open("w", newline="", encoding="utf-8-sig") as f:
        fields = list(review[0].keys()) if review else ["titulo", "status_validacao"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(review)
    print(json.dumps({k: v for k, v in report.items() if k != "candidatos"}, ensure_ascii=False, indent=2))
    print("Nenhuma escrita no Supabase.")
if __name__ == "__main__":
    main()
