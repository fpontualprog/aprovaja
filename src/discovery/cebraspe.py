"""Descoberta de provas publicadas pelo Cebraspe."""
from __future__ import annotations
import re
from typing import Any
from urllib.parse import urljoin
import requests
from src.config import CEBRASPE_API_LISTA, CEBRASPE_API_DETALHE, CEBRASPE_CDN

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "APROVAJA-concursos-collector/1.0 (+https://github.com/fpontualprog/aprovaja)"})
TIMEOUT = 30

def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)

def _event_code(item: dict) -> str | None:
    for key in ("url", "evento_url", "codigo", "codigoEvento", "slug", "id"):
        value = item.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()
    return None

def _pdf_links(value: Any) -> list[dict[str, str]]:
    found = {}
    for item in _walk(value):
        for key, val in item.items():
            if isinstance(val, str) and ".pdf" in val.lower():
                url = urljoin("https://cdn.cebraspe.org.br/", val)
                if url.startswith("https://") and ".pdf" in url.lower():
                    found[url] = {"url": url, "nome": url.rsplit("/", 1)[-1].split("?", 1)[0]}
    return list(found.values())

def descobrir_prova(evento: str) -> dict[str, Any]:
    """Localiza PDFs do evento; levanta erro claro se a API não retornar os arquivos."""
    response = SESSION.get(CEBRASPE_API_LISTA, timeout=TIMEOUT)
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("A API do Cebraspe não retornou JSON válido na listagem de concursos.") from exc

    candidates = []
    for item in _walk(payload):
        code = _event_code(item)
        serialized = str(item).lower()
        if code and (evento.lower() in code.lower() or evento.lower() in serialized):
            candidates.append(item)
    if not candidates:
        raise LookupError(f"Evento '{evento}' não foi localizado na listagem pública do Cebraspe.")

    pdfs = []
    metadata = candidates[0]
    for item in candidates:
        pdfs.extend(_pdf_links(item))
    event_url = _event_code(metadata)
    if event_url:
        detail_url = CEBRASPE_API_DETALHE.format(evento_url=event_url)
        try:
            detail = SESSION.get(detail_url, timeout=TIMEOUT)
            if detail.ok:
                pdfs.extend(_pdf_links(detail.json()))
        except (requests.RequestException, ValueError):
            pass
    if not pdfs and event_url:
        # Fallback conservador: consulta detalhe e não inventa nomes de arquivos.
        for candidate in [event_url, evento]:
            try:
                detail = SESSION.get(CEBRASPE_API_DETALHE.format(evento_url=candidate), timeout=TIMEOUT)
                if detail.ok:
                    pdfs.extend(_pdf_links(detail.json()))
            except (requests.RequestException, ValueError):
                continue
    unique = {p["url"]: p for p in pdfs}
    if not unique:
        raise LookupError(f"O evento '{evento}' foi localizado, mas nenhum link PDF foi encontrado nos dados públicos.")
    return {"evento": evento, "metadados": metadata, "provas": list(unique.values())}

def baixar_pdf(url: str, destino: str) -> str:
    """Baixa um PDF HTTPS; rejeita respostas que não aparentem ser PDF."""
    if not url.startswith("https://"):
        raise ValueError("Por segurança, só são aceitas URLs HTTPS.")
    response = SESSION.get(url, timeout=60)
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        raise ValueError(f"A URL não retornou um PDF válido: {url}")
    with open(destino, "wb") as stream:
        stream.write(response.content)
    return destino
