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
TIMEOUT = 5
OFFICIAL_HINTS = re.compile(r"\.(gov\.br|jus\.br|leg\.br|edu\.br)$", re.I)
NOTICE_HINTS = re.compile(r"edital|concurso|processo.?seletivo|selecao|diario.?oficial", re.I)
OPEN_HINTS = re.compile(r"inscri.{0,25}(aberta|até|ate|prorrog)|per[ií]odo de inscri|inscri.{0,20}encerra", re.I)
CLOSED_HINTS = re.compile(r"inscri.{0,25}(encerrad|terminad|finaliz)|prazo.{0,20}encerrad", re.I)
OLD_RESULTS = re.compile(r"resultado final|gabarito definitivo|homologa.{0,20}resultado|convoca.{0,20}aprovados|convoca.{0,30}(?:exames|documentos|posse)", re.I)
SOCIAL_HOSTS = ("facebook.com", "instagram.com", "youtube.com", "youtu.be", "tiktok.com", "whatsapp.com", "x.com", "twitter.com")
GENERIC_TITLES = re.compile(r"^(assine|login|entrar|facebook|instagram|youtube|página inicial|pagina inicial|home|início|inicio|gov\.br)$", re.I)
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

def is_social_or_share(url):
    d = domain(url)
    path = (urlparse(url).path or "").lower()
    return any(d == h or d.endswith("." + h) for h in SOCIAL_HOSTS) or any(x in path for x in ("/login", "/accounts/", "/share", "/send?", "/intent/"))

def is_generic_destination(url, title=""):
    p = urlparse(url)
    path = (p.path or "").strip("/")
    t = norm(title)
    return is_social_or_share(url) or (not path and not p.query) or bool(GENERIC_TITLES.search(t))

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
        # Primeiro tenta resolver o link específico da notícia. A URL <source> do RSS
        # normalmente é apenas a página inicial do publicador e nunca prova que o artigo foi localizado.
        tried = set()
        for candidate in variants[:3]:
            urls = [candidate.get("url_descoberta") or "", candidate.get("url_fonte_publicadora") or ""]
            for src in urls:
                if not src.startswith("http") or src in tried:
                    continue
                tried.add(src)
                result, stat, soup, text = fetch_page(session, src)
                page_status = stat
                if not result:
                    continue
                final_url, soup, title, text = result
                page_title = title or page_title
                combined_text += " " + text
                is_google = any(domain(final_url) == x or domain(final_url).endswith("." + x) for x in GOOGLE_HOSTS)
                # A page is accepted as the article only when it is not a social/share redirect
                # and has a meaningful path (or page title strongly resembles the discovered title).
                if not is_google and not is_generic_destination(final_url, title):
                    discovered_tokens = tokens(candidate.get("titulo", ""))
                    page_tokens = tokens(title)
                    title_overlap = len(discovered_tokens & page_tokens) / max(1, len(discovered_tokens))
                    has_article_path = len((urlparse(final_url).path or "").strip("/")) > 3
                    if has_article_path or title_overlap >= 0.35:
                        publisher_url = final_url
                # Search links on the wrapper/page, prioritizing links whose labels resemble the headline.
                links = external_article_links(soup, final_url)
                headline_tokens = tokens(candidate.get("titulo", ""))
                scored = []
                for link in links:
                    if is_social_or_share(link):
                        continue
                    link_path = (urlparse(link).path or "").strip("/")
                    if not link_path:
                        continue
                    label = ""
                    # URL path can identify the story even if the anchor text is absent.
                    link_tokens = tokens(unquote(link_path.replace("/", " ").replace("-", " ").replace("_", " ")))
                    score = len(headline_tokens & link_tokens) / max(1, len(headline_tokens))
                    if NOTICE_HINTS.search(link):
                        score += 0.08
                    scored.append((score, link))
                scored.sort(reverse=True)
                for score, link in scored[:5]:
                    if score < 0.12:
                        continue
                    res2, stat2, soup2, text2 = fetch_page(session, link)
                    if not res2:
                        continue
                    final2, soup2, title2, text2 = res2
                    if is_generic_destination(final2, title2):
                        continue
                    page_tokens = tokens(title2)
                    overlap = len(headline_tokens & page_tokens) / max(1, len(headline_tokens))
                    # Do not call a homepage or unrelated page the resolved article.
                    if overlap < 0.18 and len((urlparse(final2).path or "").strip("/")) < 4:
                        continue
                    publisher_url = final2
                    page_title = title2 or page_title
                    combined_text += " " + text2
                    for a in soup2.find_all("a", href=True):
                        label = a.get_text(" ", strip=True)
                        href = urljoin(final2, a["href"])
                        if official_domain(href) and NOTICE_HINTS.search(label + " " + href):
                            official[href] = {"texto_link": label[:160], "url": href, "dominio_oficial": domain(href)}
                    for tag in soup2.find_all(["link", "meta"]):
                        val = tag.get("href") or tag.get("content") or ""
                        href = urljoin(final2, val)
                        if official_domain(href) and NOTICE_HINTS.search(href):
                            official[href] = {"texto_link": "metadado/canonical", "url": href, "dominio_oficial": domain(href)}
                    break
                if publisher_url or official:
                    break
            if publisher_url or official:
                break
        combined_text = " ".join([best.get("titulo", ""), best.get("descricao") or "", page_title, combined_text])
        is_old = bool(OLD_RESULTS.search(best.get("titulo", "")))
        # The word "abertas" in a headline is only a lead, never proof of current registration.
        is_open_signal = bool(OPEN_HINTS.search(combined_text)) and not bool(CLOSED_HINTS.search(combined_text)) and not is_old
        status = "provavel_resultado_antigo" if is_old else ("fonte_oficial_candidata_revisao_humana" if official else ("pagina_publicadora_localizada_revisao_humana" if publisher_url else "nao_conseguiu_resolver_noticia"))
        review.append({
            "titulo": best.get("titulo"),
            "url_descoberta": best.get("url_descoberta"),
            "url_fonte_publicadora_rss": best.get("url_fonte_publicadora"),
            "url_publicadora_resolvida": publisher_url,
            "fonte_publicadora": best.get("fonte_publicadora"),
            "data_publicacao": best.get("data_publicacao"),
            "quantidade_fontes_duplicadas": len(group["rows"]),
            "urls_descoberta_relacionadas": " | ".join(dict.fromkeys(x.get("url_descoberta", "") for x in group["rows"] if x.get("url_descoberta"))),
            "status_validacao": status,
            "status_http_fonte": page_status,
            "titulo_pagina_acessada": page_title,
            "links_oficiais_candidatos": json.dumps(list(official.values())[:20], ensure_ascii=False),
            "sinal_inscricao_aberta_no_texto": is_open_signal,
            "sinal_inscricao_encerrada_no_texto": bool(CLOSED_HINTS.search(combined_text)),
            "edital_url_confirmado": None,
            "banca_url_confirmada": None,
            "inscricoes_abertas_confirmadas": False,
            "acao_recomendada": "Revisar a notícia específica; confirmar edital, banca e prazo em fonte oficial. Sinal textual não confirma inscrição aberta.",
        })
        if idx % 50 == 0:
            print(f"Revisados {idx}/{len(groups)} grupos...")
        time.sleep(0.02)

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
