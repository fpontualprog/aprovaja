"""Exportação dos itens estruturados."""
from __future__ import annotations
import csv
import json
from pathlib import Path
import pandas as pd

def exportar_questoes(questoes: list[dict], saida: str | Path, evento: str) -> dict[str, str]:
    pasta = Path(saida)
    pasta.mkdir(parents=True, exist_ok=True)
    base = "".join(c if c.isalnum() or c in "-_" else "_" for c in evento).strip("_") or "concurso"
    csv_path = pasta / f"{base}_questoes.csv"
    xlsx_path = pasta / f"{base}_questoes.xlsx"
    json_path = pasta / f"{base}_questoes.json"
    if not questoes:
        raise ValueError("Não há questões para exportar.")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for q in questoes for k in q.keys())))
        writer.writeheader()
        writer.writerows(questoes)
    pd.DataFrame(questoes).to_excel(xlsx_path, index=False)
    json_path.write_text(json.dumps(questoes, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"csv": str(csv_path), "xlsx": str(xlsx_path), "json": str(json_path)}
