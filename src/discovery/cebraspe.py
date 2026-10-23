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
    """Busca primeiro o evento diretamente; usa a listagem como fallback."""
    evento = evento.strip()
    if not evento:
        raise ValueError("Informe o código do evento do Cebraspe.")

    detail_url = CEBRASPE_API_DETALHE.format(evento_url=evento)
    detail_status = None
    detail_error = None
    metadata: dict[str, Any] = {"evento_url": evento}
    pdfs: list[dict[str, str]] = []

    # Primeiro tenta o endpoint direto, que não depende de o evento aparecer
    # na listagem pública de concursos encerrados.
    try:
        detail = SESSION.get(detail_url, timeout=TIMEOUT)
        detail_status = detail.status_code
        if detail.ok:
            try:
                detail_payload = detail.json()
            except ValueError as exc:
                detail_error = "a API de detalhes não retornou JSON válido"
            else:
                if isinstance(detail_payload, dict):
                    metadata = detail_payload
                else:
                    metadata = {"evento_url": evento, "dados": detail_payload}
                pdfs.extend(_pdf_links(detail_payload))
        else:
            detail_error = f"HTTP {detail.status_code}"
    except requests.RequestException as exc:
        detail_error = f"falha de conexão ({exc})"

    if pdfs:
        unique = {p["url"]: p for p in pdfs}
        return {"evento": evento, "metadados": metadata, "provas": list(unique.values())}

    # Se a consulta direta não trouxe links, consulta a listagem como fallback.
    # A ausência na listagem, por si só, não invalida uma resposta válida do detalhe.
    list_error = None
    try:
        response = SESSION.get(CEBRASPE_API_LISTA, timeout=TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        candidates = []
        for item in _walk(payload):
            serialized = str(item).lower()
            code = _event_code(item)
            if evento.lower() in serialized or (code and evento.lower() == code.lower()):
                candidates.append(item)

        for item in candidates:
            pdfs.extend(_pdf_links(item))
            candidate_code = _event_code(item)
            if candidate_code:
                try:
                    candidate_detail = SESSION.get(
                        CEBRASPE_API_DETALHE.format(evento_url=candidate_code),
                        timeout=TIMEOUT,
                    )
                    if candidate_detail.ok:
                        candidate_payload = candidate_detail.json()
                        pdfs.extend(_pdf_links(candidate_payload))
                        if not metadata or metadata == {"evento_url": evento}:
                            metadata = candidate_payload if isinstance(candidate_payload, dict) else {
                                "evento_url": candidate_code, "dados": candidate_payload
                            }
                except (requests.RequestException, ValueError):
                    continue
    except (requests.RequestException, ValueError) as exc:
        list_error = str(exc)

    unique = {p["url"]: p for p in pdfs}
    if unique:
        return {"evento": evento, "metadados": metadata, "provas": list(unique.values())}

    if detail_status is not None and detail_status >= 400:
        reason = f"API de detalhes respondeu HTTP {detail_status}"
    elif detail_error:
        reason = f"não foi possível ler os detalhes: {detail_error}"
    elif list_error:
        reason = f"a listagem também falhou: {list_error}"
    else:
        reason = "a API de detalhes respondeu, mas não forneceu links para PDFs"
    raise LookupError(
        f"Não foi possível obter PDFs para o evento '{evento}' ({reason}). "
        f"Endpoint consultado: {detail_url}"
    )

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
