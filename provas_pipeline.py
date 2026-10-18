#!/usr/bin/env python3
"""Pipeline independente de provas: busca em fontes autorizadas, arquiva PDFs e gera JSON multimodal."""
from __future__ import annotations
import argparse, hashlib, json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
import requests
from bs4 import BeautifulSoup
import fitz

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config" / "fontes_provas.json"
OUT = ROOT / "provas_data"
HEADERS_ACCEPT = {"Accept": "text/html,application/pdf,application/xhtml+xml"}

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def safe_name(s: str, limit: int = 90) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("._-")
    return (s or "documento")[:limit]

def host_allowed(url: str, domains: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d.lower() or host.endswith("." + d.lower()) for d in domains)

def canonical(url: str) -> str:
    return urldefrag(url)[0]

def get(session, url, timeout):
    response = session.get(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    return response

def extract_pdf(pdf_path: Path, record: dict, out: Path) -> dict:
    """Gera JSON por página; mantém ordem/posição dos blocos, imagens originais e render da página."""
    assets_dir = out / "midias" / record["sha256"]
    pages = []
    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc):
            page_no = page_index + 1
            page_dir = assets_dir / f"pagina_{page_no:04d}"
            page_dir.mkdir(parents=True, exist_ok=True)
            # Render da página preserva visualmente tabelas, gráficos, fórmulas e layout.
            pix = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False)
            page_image = page_dir / "pagina_completa.png"
            pix.save(page_image)
            blocks_out = []
            raw = page.get_text("dict", sort=True)
            for block_index, block in enumerate(raw.get("blocks", []), start=1):
                bbox = [round(float(x), 2) for x in block.get("bbox", [])]
                if block.get("type") == 0:
                    lines = []
                    for line in block.get("lines", []):
                        spans = []
                        for span in line.get("spans", []):
                            text = span.get("text", "")
                            if text:
                                spans.append({
                                    "texto": text,
                                    "fonte": span.get("font"),
                                    "tamanho": round(float(span.get("size", 0)), 2),
                                    "negrito_ou_estilo": span.get("flags", 0)
                                })
                        if spans:
                            lines.append({"spans": spans, "texto": "".join(x["texto"] for x in spans)})
                    text = "\n".join(line["texto"] for line in lines).strip()
                    if text:
                        blocks_out.append({"ordem": block_index, "tipo": "texto", "bbox": bbox, "texto": text, "linhas": lines})
                elif block.get("type") == 1 and block.get("image"):
                    ext = safe_name(block.get("ext") or "png")
                    image_bytes = block["image"]
                    image_name = f"imagem_{block_index:03d}.{ext}"
                    image_path = page_dir / image_name
                    image_path.write_bytes(image_bytes)
                    blocks_out.append({
                        "ordem": block_index, "tipo": "imagem", "bbox": bbox,
                        "arquivo": image_path.relative_to(out).as_posix(),
                        "sha256": sha256_bytes(image_bytes),
                        "largura": block.get("width"), "altura": block.get("height")
                    })
            # OCR não é inventado: páginas sem camada de texto ficam sinalizadas para OCR posterior.
            text_chars = sum(len(b.get("texto", "")) for b in blocks_out if b["tipo"] == "texto")
            pages.append({
                "pagina": page_no,
                "largura_pt": round(page.rect.width, 2),
                "altura_pt": round(page.rect.height, 2),
                "texto_extraido": text_chars > 0,
                "requer_ocr": text_chars < 20,
                "texto": "\n\n".join(b["texto"] for b in blocks_out if b["tipo"] == "texto"),
                "blocos": blocks_out,
                "imagem_pagina": page_image.relative_to(out).as_posix()
            })
    return {
        "schema_version": "aprovaja.prova.v1",
        "documento": record,
        "processamento": {
            "processado_em": datetime.now(timezone.utc).isoformat(),
            "ferramenta_pdf": "PyMuPDF",
            "preserva_pdf_original": True,
            "preserva_layout_visual_por_pagina": True,
            "limites": [
                "O JSON registra blocos e posições; a segmentação semântica de questões deve ser validada em etapa própria.",
                "Páginas sinalizadas requer_ocr precisam de OCR para recuperar texto que exista somente como imagem.",
                "As imagens de página preservam visualmente tabelas, gráficos e fórmulas mesmo quando não forem identificados como tabelas estruturadas."
            ]
        },
        "paginas": pages
    }

def run(config_path: Path, out: Path, max_downloads: int, max_pages_override: int | None):
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    for sub in ("originais", "json", "midias", "logs"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": cfg.get("user_agent", "APROVAJA-ProvasBot/1.0"), **HEADERS_ACCEPT})
    timeout = int(cfg.get("timeout_seconds", 25))
    discovered, page_errors, download_errors = [], [], []
    seen_pages, seen_pdf_urls = set(), set()
    max_downloads = max(0, max_downloads)
    for source in cfg.get("sources", []):
        domains = source.get("domains", [])
        queue = [(u, 0) for u in source.get("start_urls", [])]
        pages_count = 0
        max_pages = max_pages_override or int(cfg.get("max_pages_per_source", 80))
        while queue and pages_count < max_pages and len(discovered) < max_downloads:
            url, depth = queue.pop(0)
            url = canonical(url)
            if url in seen_pages or not host_allowed(url, domains):
                continue
            seen_pages.add(url)
            try:
                resp = get(session, url, timeout)
                pages_count += 1
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if "pdf" in ctype or url.lower().endswith(".pdf"):
                    pdf_url = resp.url
                    payload = resp.content
                    discovered.append({"source": source["name"], "url": pdf_url, "bytes": payload, "content_type": ctype})
                    seen_pdf_urls.add(pdf_url)
                    continue
                if "html" not in ctype and not resp.text.lstrip().lower().startswith(("<!doctype html", "<html")):
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    target = canonical(urljoin(resp.url, a["href"].strip()))
                    if not host_allowed(target, domains):
                        continue
                    if urlparse(target).path.lower().endswith(".pdf"):
                        if target not in seen_pdf_urls:
                            seen_pdf_urls.add(target)
                            discovered.append({"source": source["name"], "url": target, "bytes": None, "content_type": "application/pdf"})
                    elif depth < int(cfg.get("max_depth", 2)) and target not in seen_pages:
                        queue.append((target, depth + 1))
                time.sleep(0.15)
            except Exception as exc:
                page_errors.append({"fonte": source.get("name"), "url": url, "erro": str(exc)})
    # Baixa e processa os PDFs após a descoberta, sem misturar com o coletor de concursos.
    manifest = []
    processed = 0
    for item in discovered:
        if processed >= max_downloads:
            break
        try:
            payload = item["bytes"]
            if payload is None:
                resp = get(session, item["url"], timeout)
                payload = resp.content
                final_url = resp.url
            else:
                final_url = item["url"]
            if not payload.startswith(b"%PDF"):
                raise ValueError("Resposta não parece ser um PDF")
            digest = sha256_bytes(payload)
            pdf_path = out / "originais" / f"{digest}.pdf"
            if not pdf_path.exists():
                pdf_path.write_bytes(payload)
            record = {
                "id_documento": digest,
                "fonte": item["source"],
                "url_origem": final_url,
                "nome_arquivo_original": Path(urlparse(final_url).path).name or f"{digest}.pdf",
                "sha256": digest,
                "tamanho_bytes": len(payload),
                "coletado_em": datetime.now(timezone.utc).isoformat(),
                "pdf_armazenado": pdf_path.relative_to(out).as_posix()
            }
            json_data = extract_pdf(pdf_path, record, out)
            json_path = out / "json" / f"{digest}.json"
            tmp = json_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(json_path)
            manifest.append({**record, "paginas": len(json_data["paginas"]), "json": json_path.relative_to(out).as_posix(), "status": "PROCESSADO"})
            processed += 1
        except Exception as exc:
            download_errors.append({"fonte": item.get("source"), "url": item.get("url"), "erro": str(exc)})
            manifest.append({"fonte": item.get("source"), "url_origem": item.get("url"), "status": "ERRO", "erro": str(exc)})
    report = {
        "executado_em": datetime.now(timezone.utc).isoformat(),
        "modo": "coleta_e_conversao_pdf_json",
        "fontes_configuradas": [s.get("name") for s in cfg.get("sources", [])],
        "paginas_web_visitadas": len(seen_pages),
        "pdfs_descobertos": len(discovered),
        "pdfs_processados": processed,
        "erros_paginas": page_errors,
        "erros_pdfs": download_errors,
        "manifesto": manifest,
        "supabase_modificado": False,
        "banco_questoes_modificado": False,
        "observacao": "Este pipeline apenas coleta e prepara arquivos. Não grava no Supabase nem publica questões automaticamente."
    }
    report_path = out / "logs" / "relatorio_execucao.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("paginas_web_visitadas", "pdfs_descobertos", "pdfs_processados")}, ensure_ascii=False))
    print(f"Relatório: {report_path}")
    return 0 if not page_errors and not download_errors else 1

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--max-downloads", type=int, default=10, help="Limite de PDFs processados por execução (padrão: 10)")
    parser.add_argument("--max-pages", type=int, default=None, help="Limite opcional de páginas web por fonte")
    args = parser.parse_args()
    return run(args.config, args.out, args.max_downloads, args.max_pages)

if __name__ == "__main__":
    raise SystemExit(main())
