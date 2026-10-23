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

def _normalizar_chave(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _pdf_links(value: Any, evento: str | None = None) -> list[dict[str, str]]:
    """Extrai links de PDF sem transformar nomes de campos em URLs."""
    found: dict[str, dict[str, str]] = {}
    file_keys = {
        "nomearquivo", "arquivo", "filename", "file", "urlarquivo",
        "caminhoarquivo", "linkarquivo", "url", "link", "downloadurl",
        "urldownload", "caminho", "path",
    }
    description_keys = {
        "descricao", "descricaoarquivo", "nome", "titulo", "tipo",
        "tipoarquivo", "documento", "descricaoanexo",
    }

    for item in _walk(value):
        normalized = {_normalizar_chave(str(k)): v for k, v in item.items()}
        description = " ".join(
            str(normalized[k]) for k in description_keys
            if k in normalized and isinstance(normalized[k], (str, int))
        ).strip()
        objective = "prova objetiva" in description.lower()

        # Primeiro, usa os campos explicitamente relacionados a arquivos/URLs.
        candidates = []
        for key in file_keys:
            val = normalized.get(key)
            if isinstance(val, str) and val.strip():
                candidates.append(val.strip())

        # Alguns retornos da API armazenam o nome do arquivo em nomeArquivo,
        # separado da descrição/tipo do documento.
        for raw in item.values():
            if isinstance(raw, str) and ".pdf" in raw.lower() and raw.strip() not in candidates:
                candidates.append(raw.strip())

        for candidate in candidates:
            if ".pdf" not in candidate.lower():
                continue
            candidate_filename = candidate.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1].replace("\\", "")
            if candidate_filename.strip().lower() in {"_", "_.pdf"}:
                continue
            if candidate.startswith(("https://", "http://")):
                url = candidate
            elif candidate.startswith("/") or "/" in candidate or "\\" in candidate:
                url = urljoin("https://cdn.cebraspe.org.br/", candidate.replace("\\", "/"))
            elif evento and re.fullmatch(r"[^/?#]+\.pdf(?:\?[^#]*)?", candidate, flags=re.I):
                # Só monta o caminho CDN quando o valor é realmente um nome de arquivo.
                filename = candidate.split("?", 1)[0]
                url = CEBRASPE_CDN.format(evento_url=evento, nome_arquivo=filename)
            else:
                continue

            if not url.startswith("https://") or ".pdf" not in url.lower():
                continue
            filename = url.rsplit("/", 1)[-1].split("?", 1)[0]
            # Se há descrição disponível, prioriza documentos de prova objetiva.
            found[url] = {
                "url": url,
                "url_download": url,
                "nome": filename,
                "nomeArquivo": filename,
                "descricao": description,
                "prova_objetiva": "true" if objective else "false",
            }

    # Quando a API descreve explicitamente os documentos, devolve provas objetivas
    # se houver alguma; se não houver esse metadado, preserva os PDFs encontrados.
    records = list(found.values())
    explicit_objective = [p for p in records if p["prova_objetiva"] == "true"]
    return explicit_objective or records

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
                pdfs.extend(_pdf_links(detail_payload, evento))
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
            pdfs.extend(_pdf_links(item, evento))
            candidate_code = _event_code(item)
            if candidate_code:
                try:
                    candidate_detail = SESSION.get(
                        CEBRASPE_API_DETALHE.format(evento_url=candidate_code),
                        timeout=TIMEOUT,
                    )
                    if candidate_detail.ok:
                        candidate_payload = candidate_detail.json()
                        pdfs.extend(_pdf_links(candidate_payload, evento))
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
