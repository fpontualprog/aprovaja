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
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; APROVAJA-OfficialLinkResolver/1.1)"}
BANKS = [
 ("Cebraspe", r"CEBRASPE|CESPE/CEBRASPE|CESPE", "https://www.cebraspe.org.br/concursos"),
 ("Fundação Getulio Vargas (FGV)", r"FUNDA[CÇ][AÃ]O GETULIO VARGAS|\\bFGV\\b", "https://conhecimento.fgv.br/concursos"),
 ("Fundação Carlos Chagas (FCC)", r"FUNDA[CÇ][AÃ]O CARLOS CHAGAS|\\bFCC\\b", "https://www.concursosfcc.com.br/"),
 ("Instituto AOCP", r"INSTITUTO AOCP|\\BAOCP\\b", "https://www.institutoaocp.org.br/"),
 ("IBFC", r"\\bIBFC\\b|INSTITUTO BRASILEIRO DE FORMA[CÇ][AÃ]O E CAPACITA[CÇ][AÃ]O", "https://www.ibfc.org.br/"),
 ("IDECAN", r"\\bIDECAN\\b", "https://www.idecan.org.br/"),
 ("IBAM", r"\\bIBAM\\b|INSTITUTO BRASILEIRO DE ADMINISTRA[CÇ][AÃ]O MUNICIPAL", "https://www.ibam-concursos.org.br/"),
 ("Comperve/UFRN", r"COMPERVE|COMISS[AÃ]O PERMANENTE DE VESTIBULAR", "https://comperve.ufrn.br/"),
 ("FUNCERN", r"\\bFUNCERN\\b", "https://funcern.br/"),
 ("ADM&TEC", r"ADM\\s*&\\s*TEC|ADMTEC", "https://www.admtec.org.br/"),
 ("IGEDUC", r"\\bIGEDUC\\b", "https://igeduc.org.br/"),
 ("Consulpam", r"CONSULPAM", "https://www.consulpam.com.br/"),
 ("Instituto Avalia", r"INSTITUTO AVALIA|\\bAVALIA\\b", "https://www.avalia.org.br/"),
 ("Quadrix", r"QUADRIX", "https://www.quadrix.org.br/"),
 ("Fundação Vunesp", r"VUNESP", "https://www.vunesp.com.br/"),
 ("Fundação Cesgranrio", r"CESGRANRIO", "https://www.cesgranrio.org.br/"),
 ("Instituto Selecon", r"SELECON", "https://selecon.org.br/"),
 ("IADES", r"\\bIADES\\b", "https://www.iades.com.br/"),
 ("IDCAP", r"\\bIDCAP\\b", "https://www.idcap.org.br/"),
 ("Fundatec", r"FUNDATEC", "https://www.fundatec.org.br/"),
 ("Legalle Concursos", r"LEGALLE", "https://www.legalleconcursos.com.br/"),
 ("Fundação FAFIPA", r"FAFIPA", "https://www.fundacaofafipa.org.br/"),
 ("UPENET/IAUPE", r"UPENET|IAUPE", "https://www.upenet.com.br/"),
]
PCI_SUFFIX = "pciconcursos.com.br"
OFFICIAL_SUFFIXES = (".gov.br", ".jus.br", ".edu.br", ".leg.br")

def host_of(value):
    try:
        return (urlparse(value).hostname or "").lower().rstrip(".")
    except Exception:
        return ""

def norm_url(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        u = urlparse(value.strip())
        if u.scheme not in ("http", "https") or not u.hostname:
            return None
        if u.hostname.lower().endswith(PCI_SUFFIX):
            return None
        return value.strip()
    except Exception:
        return None

def official_host(host, bank_host=None):
    if not host or host.endswith(PCI_SUFFIX):
        return False
    if any(host.endswith(suffix) for suffix in OFFICIAL_SUFFIXES):
        return True
    return bool(bank_host and (host == bank_host or host.endswith("." + bank_host)))

def resolve(record, session):
    record.setdefault("edital_url", None)
    record.setdefault("banca", None)
    record.setdefault("banca_url", None)
    source = record.get("fonte_url")
    soup = None
    text = ""
    if source:
        try:
            response = session.get(source, timeout=TIMEOUT, headers=HEADERS)
            response.raise_for_status()
            if len(response.text) < 500:
                raise ValueError("página de detalhes curta")
            soup = BeautifulSoup(response.text, "html.parser")
            text = " ".join(soup.stripped_strings)
        except Exception as exc:
            record["resolver_edital_status"] = "pendente"
            record["resolver_edital_erro"] = str(exc)[:180]

    # Prefer an explicit bank domain linked from the PCI article over a generic
    # mention in the article text; only then use a named bank in the page text.
    if soup:
        known_hosts = [(name, pattern, homepage, host_of(homepage)) for name, pattern, homepage in BANKS]
        for a in soup.find_all("a", href=True):
            href = urljoin(source, a["href"].strip())
            host = host_of(href)
            for name, pattern, homepage, bank_host in known_hosts:
                if host == bank_host or host.endswith("." + bank_host):
                    record["banca"], record["banca_url"] = name, homepage
                    break
            if record.get("banca_url"):
                break
        if not record.get("banca_url"):
            for name, pattern, homepage in BANKS:
                if re.search(pattern, text, re.I):
                    record["banca"], record["banca_url"] = name, homepage
                    break

    bank_host = host_of(record.get("banca_url") or "")
    # Validate pre-existing values too; never label an arbitrary or PCI URL official.
    existing = norm_url(record.get("edital_url"))
    if existing and official_host(host_of(existing), bank_host):
        record["edital_url"] = existing
    else:
        record["edital_url"] = None
        candidates = []
        if soup:
            for a in soup.find_all("a", href=True):
                label = " ".join(a.stripped_strings)
                href = urljoin(source, a["href"].strip())
                parsed = urlparse(href)
                host = (parsed.hostname or "").lower()
                if parsed.scheme not in ("http", "https") or not official_host(host, bank_host):
                    continue
                # Accept explicit edital/PDF cues in the link or its URL. Also
                # inspect nearby text for generic links such as "Acesse aqui".
                nearby = " ".join(a.parent.stripped_strings) if a.parent else ""
                cue = re.search(r"edital|download.{0,30}pdf|arquivo.{0,30}pdf|\\.pdf(?:$|[?#])|retifica[cç][aã]o do edital", label + " " + href, re.I)
                contextual_cue = re.search(r"edital|processo seletivo|concurso p[uú]blico", nearby, re.I)
                generic_label = re.fullmatch(r"(acesse aqui|clique aqui|aqui|site oficial|saiba mais|documentos|download)", label.strip(), re.I)
                if cue or (generic_label and contextual_cue and (host.endswith(OFFICIAL_SUFFIXES) or (bank_host and (host == bank_host or host.endswith("." + bank_host))))):
                    candidates.append(href)
        if candidates:
            # Prefer PDF paths and explicit edital labels, preserving page order otherwise.
            candidates.sort(key=lambda u: (0 if re.search(r"edital|\\.pdf(?:$|[?#])", u, re.I) else 1, len(u)))
            record["edital_url"] = candidates[0]

    if record.get("edital_url"):
        record["mensagem_edital"] = None
        record["resolver_edital_status"] = "link_oficial_localizado"
        record.pop("resolver_edital_erro", None)
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
        if not isinstance(item, dict):
            continue
        resolve(item, session)
        if (i + 1) % 25 == 0:
            print(f"Editais verificados: {i+1}/{total}")
        time.sleep(0.12)
    tmp = OUTPUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUTPUT)
    found = sum(bool(x.get("edital_url")) for x in records if isinstance(x, dict))
    bank = sum(bool(x.get("banca_url")) for x in records if isinstance(x, dict))
    print(f"Resolução concluída: {found} links oficiais aceitos; {bank} bancas reconhecidas; {total-found} editais sem link confirmado.")
    print("Editais sem link confirmado permanecem sem URL e recebem orientação para a banca ou órgão responsável.")

if __name__ == "__main__":
    main()
