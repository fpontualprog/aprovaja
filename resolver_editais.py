#!/usr/bin/env python3
"""Resolve edital links conservatively and attach the official bank homepage when recognized."""
from __future__ import annotations
import json, re, time
from pathlib import Path
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "resultado_coleta_pci_v3" / "concursos_pci_nordeste.json"
OUTPUT = ROOT / "resultado_coleta_pci_v3" / "concursos_pci_nordeste.json"
TIMEOUT = 18
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; APROVAJA-OfficialLinkResolver/1.0)"}
# Domains below are official institutional homepages, curated rather than inferred from search snippets.
BANKS = [
 ("Cebraspe", r"CEBRASPE|CESPE/CEBRASPE|CESPE", "https://www.cebraspe.org.br/concursos"),
 ("Fundação Getulio Vargas (FGV)", r"FUNDA[CÇ][AÃ]O GETULIO VARGAS|\bFGV\b", "https://conhecimento.fgv.br/concursos"),
 ("Fundação Carlos Chagas (FCC)", r"FUNDA[CÇ][AÃ]O CARLOS CHAGAS|\bFCC\b", "https://www.concursosfcc.com.br/"),
 ("Instituto AOCP", r"INSTITUTO AOCP|\BAOCP\b", "https://www.institutoaocp.org.br/"),
 ("IBFC", r"\bIBFC\b|INSTITUTO BRASILEIRO DE FORMA[CÇ][AÃ]O E CAPACITA[CÇ][AÃ]O", "https://www.ibfc.org.br/"),
 ("IDECAN", r"\bIDECAN\b", "https://www.idecan.org.br/"),
 ("IBAM", r"\bIBAM\b|INSTITUTO BRASILEIRO DE ADMINISTRA[CÇ][AÃ]O MUNICIPAL", "https://www.ibam-concursos.org.br/"),
 ("Comperve/UFRN", r"COMPERVE|COMISS[AÃ]O PERMANENTE DE VESTIBULAR", "https://comperve.ufrn.br/"),
 ("FUNCERN", r"\bFUNCERN\b", "https://funcern.br/"),
 ("ADM&TEC", r"ADM\s*&\s*TEC|ADMTEC", "https://www.admtec.org.br/"),
 ("IGEDUC", r"\bIGEDUC\b", "https://igeduc.org.br/"),
 ("Consulpam", r"CONSULPAM", "https://www.consulpam.com.br/"),
 ("Instituto Avalia", r"INSTITUTO AVALIA|\bAVALIA\b", "https://www.avalia.org.br/"),
 ("Quadrix", r"QUADRIX", "https://www.quadrix.org.br/"),
 ("Fundação Vunesp", r"VUNESP", "https://www.vunesp.com.br/"),
 ("Fundação Cesgranrio", r"CESGRANRIO", "https://www.cesgranrio.org.br/"),
 ("Instituto Selecon", r"SELECON", "https://selecon.org.br/"),
 ("IADES", r"\bIADES\b", "https://www.iades.com.br/"),
 ("IDCAP", r"\bIDCAP\b", "https://www.idcap.org.br/"),
 ("Fundatec", r"FUNDATEC", "https://www.fundatec.org.br/"),
 ("Legalle Concursos", r"LEGALLE", "https://www.legalleconcursos.com.br/"),
 ("Fundação FAFIPA", r"FAFIPA", "https://www.fundacaofafipa.org.br/"),
 ("UPENET/IAUPE", r"UPENET|IAUPE", "https://www.upenet.com.br/"),
]
def norm_url(value):
    if not isinstance(value, str) or not value.strip(): return None
    try:
        u = urlparse(value.strip())
        if u.scheme not in ("http", "https") or not u.hostname: return None
        if u.hostname.lower().endswith("pciconcursos.com.br"): return None
        return value.strip()
    except Exception: return None

def resolve(record, session):
    record.setdefault("edital_url", None)
    record.setdefault("banca", None)
    record.setdefault("banca_url", None)
    source = record.get("fonte_url")
    if not source: return record
    try:
        response = session.get(source, timeout=TIMEOUT, headers=HEADERS)
        response.raise_for_status()
        if len(response.text) < 500: raise ValueError("página de detalhes curta")
        soup = BeautifulSoup(response.text, "html.parser")
        text = " ".join(soup.stripped_strings)
        for name, pattern, homepage in BANKS:
            if re.search(pattern, text, re.I):
                record["banca"] = name
                record["banca_url"] = homepage
                break
        # Only accept a direct edital link when the link itself is labelled as an edital
        # and points to a non-PCI HTTPS/HTTP destination. Do not use search snippets or guesses.
        candidates = []
        bank_host = urlparse(record["banca_url"]).hostname if record.get("banca_url") else None
        for a in soup.find_all("a", href=True):
            label = " ".join(a.stripped_strings)
            href = urljoin(source, a["href"].strip())
            parsed = urlparse(href)
            host = (parsed.hostname or "").lower()
            if parsed.scheme not in ("http", "https") or not host or host.endswith("pciconcursos.com.br"):
                continue
            cue = re.search(r"edital|download.*pdf|arquivo.*pdf", (label + " " + href), re.I)
            official_domain = host.endswith(".gov.br") or host.endswith(".jus.br") or (bank_host and (host == bank_host or host.endswith("." + bank_host)))
            if cue and official_domain:
                candidates.append(href)
        if not record.get("edital_url") and candidates:
            record["edital_url"] = candidates[0]
    except Exception as exc:
        record["resolver_edital_status"] = "pendente"
        record["resolver_edital_erro"] = str(exc)[:180]
    if record.get("edital_url"):
        record["mensagem_edital"] = None
        record["resolver_edital_status"] = "link_oficial_localizado"
    elif record.get("banca_url"):
        record["mensagem_edital"] = "Edital não localizado automaticamente. Consulte a página oficial da banca organizadora: " + record["banca_url"]
        record["resolver_edital_status"] = record.get("resolver_edital_status", "banca_identificada_edital_nao_localizado")
    else:
        record["mensagem_edital"] = "Edital não localizado automaticamente e banca não identificada com segurança. Consulte o órgão responsável pelo concurso."
        record["resolver_edital_status"] = record.get("resolver_edital_status", "banca_nao_identificada")
    return record

def main():
    if not INPUT.exists():
        raise SystemExit(f"Arquivo de coleta não encontrado: {INPUT}")
    records = json.loads(INPUT.read_text(encoding="utf-8-sig"))
    if not isinstance(records, list):
        raise SystemExit("A coleta deve ser uma lista JSON.")
    session = requests.Session()
    total = len(records)
    for i, item in enumerate(records):
        if not isinstance(item, dict): continue
        resolve(item, session)
        if (i + 1) % 25 == 0: print(f"Editais verificados: {i+1}/{total}")
        time.sleep(0.12)
    tmp = OUTPUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUTPUT)
    found = sum(bool(x.get("edital_url")) for x in records if isinstance(x, dict))
    bank = sum(bool(x.get("banca_url")) for x in records if isinstance(x, dict))
    print(f"Resolução concluída: {found} links de edital identificados; {bank} bancas reconhecidas; {total-found} editais sem link confirmado.")
    print("Sem link confirmado, edital_url permanece null e mensagem orienta para o site oficial da banca quando identificada.")
if __name__ == "__main__": main()
