#!/usr/bin/env python3
"""Experimental APROVAJÁ contest discovery sweep.
Read-only: searches public news/search RSS feeds and writes candidates locally.
It does NOT write to Supabase or modify the production collector/database.
"""
from __future__ import annotations
import csv, json, re, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
import requests
import xml.etree.ElementTree as ET

OUT = Path("varredura_experimental_resultados")
OUT.mkdir(parents=True, exist_ok=True)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; APROVAJA-Discovery/0.1; +https://github.com/fpontualprog/aprovaja)"}
TIMEOUT = 20
QUERIES = [
    '"concurso público" edital',
    '"concurso público" inscrições abertas',
    '"edital de concurso" prefeitura',
    '"concurso público" universidade federal',
    '"concurso público" governo estadual',
    '"processo seletivo" edital prefeitura',
    '"concurso público" câmara municipal',
    '"concurso público" tribunal',
    '"concurso público" saúde edital',
    '"concurso público" educação edital',
    '"concurso público" 2026 edital',
    '"concurso público" 2027 edital',
]
TERMS = re.compile(r"concurso|processo seletivo|edital|inscriç|seleção pública", re.I)
EXCLUDE = re.compile(r"resultado final|gabarito definitivo|homologação de resultado|convocação de aprovados", re.I)

def clean(s: str) -> str:
    return re.sub(r"\\s+", " ", (s or "")).strip()

def get_text(node, name):
    el = node.find(name)
    return clean("".join(el.itertext())) if el is not None else ""

def parse_feed(xml_text, query):
    root = ET.fromstring(xml_text)
    found = []
    # Google News RSS usually uses RSS item/title/link/pubDate/source.
    for item in root.findall(".//item"):
        title = get_text(item, "title")
        link = get_text(item, "link")
        pub = get_text(item, "pubDate")
        source = get_text(item, "source")
        desc = get_text(item, "description")
        if not title or not link or not TERMS.search(title + " " + desc):
            continue
        if EXCLUDE.search(title):
            continue
        found.append({
            "titulo": title,
            "url_descoberta": link,
            "data_publicacao": pub or None,
            "fonte_publicadora": source or None,
            "url_fonte_publicadora": (item.find("source").attrib.get("url") if item.find("source") is not None else None),
            "consulta_origem": query,
            "descricao": re.sub(r"<[^>]+>", " ", desc)[:500] if desc else None,
            "status_validacao": "nao_verificado",
            "edital_url": None,
            "banca_url": None,
        })
    return found

def main():
    session = requests.Session()
    results, errors = [], []
    for i, query in enumerate(QUERIES, 1):
        url = "https://news.google.com/rss/search?q=" + quote(query + " when:30d") + "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        try:
            r = session.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            results.extend(parse_feed(r.text, query))
            print(f"[{i}/{len(QUERIES)}] {query}: OK")
        except Exception as exc:
            errors.append({"consulta": query, "erro": str(exc)[:300]})
            print(f"[{i}/{len(QUERIES)}] {query}: FALHOU - {exc}")
        time.sleep(0.6)
    # Deduplicate by normalized title and URL. These are discovery candidates, not verified contests.
    seen, unique = set(), []
    for row in results:
        host = (urlparse(row["url_descoberta"]).hostname or "").lower()
        key = re.sub(r"[^a-z0-9]+", "", row["titulo"].lower())
        if not key or key in seen:
            continue
        seen.add(key)
        row["dominio_url_descoberta"] = host
        unique.append(row)
    payload = {
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
        "modo": "experimental_somente_leitura",
        "consultas_executadas": len(QUERIES),
        "total_resultados_brutos": len(results),
        "total_candidatos_unicos": len(unique),
        "aviso": "Candidatos descobertos por RSS de notícias; ainda não são concursos confirmados. Não houve escrita no Supabase.",
        "erros": errors,
        "candidatos": unique,
    }
    (OUT / "candidatos_concursos.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "candidatos_concursos.csv").open("w", newline="", encoding="utf-8-sig") as f:
        fields = ["titulo", "url_descoberta", "data_publicacao", "fonte_publicadora", "url_fonte_publicadora", "dominio_url_descoberta", "consulta_origem", "status_validacao", "edital_url", "banca_url"]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(unique)
    print(f"Concluído: {len(unique)} candidatos únicos; {len(errors)} consultas com erro.")
    print("Resultados gravados em varredura_experimental_resultados/; nada foi enviado ao Supabase.")

if __name__ == "__main__":
    main()
