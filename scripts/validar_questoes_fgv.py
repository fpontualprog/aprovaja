#!/usr/bin/env python3
"""Valida questões extraídas de texto bruto ou JSON de prova FGV."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

RE_CABECALHO = re.compile(
    r"(Concurso Público Nacional Unificado|FGV Conhecimento|Bloco Temático\s*\d+|Página\s*\d+)",
    re.IGNORECASE,
)
RE_ALTERNATIVA = re.compile(r"^\s*\(([A-E])\)\s*(.*)$")
RE_NUM_QUESTAO = re.compile(r"^\s*(\d{1,2})\s*$")
RE_INICIO_OUTRA_QUESTAO = re.compile(r"^\s*(\d{1,2})\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]")
RE_RODAPE = re.compile(
    r"^\s*(?:Realização\s*:?.*|FGV(?: Conhecimento)?|"
    r"Concurso Público Nacional Unificado|Página\s*\d+|Bloco Temático\s*\d+)\s*$",
    re.IGNORECASE,
)
RE_FONTE = re.compile(r"^\s*Fonte\s*:", re.IGNORECASE)
RE_INICIO_LEGENDA = re.compile(r"^\s*(?:Evolução histórica|Gráfico\b|Figura\b|Tabela\b)", re.IGNORECASE)
RE_CABECALHO_SECAO = re.compile(r"^\s*(?:CONHECIMENTOS ESPECÍFICOS|CONHECIMENTOS GERAIS|Eixo Temático\s*\d+\b)", re.IGNORECASE)
RE_CABECALHO_SECAO_EMBUTIDO = re.compile(r"\s+(?:CONHECIMENTOS ESPECÍFICOS|CONHECIMENTOS GERAIS|Eixo Temático\s*\d+\b).*$", re.IGNORECASE)
TAM_MIN_ENUNCIADO = 40
TAM_MIN_ALTERNATIVA = 3


@dataclass
class Questao:
    numero: int
    enunciado: str = ""
    alternativas: dict[str, str] = field(default_factory=dict)
    pagina_pdf: int | None = None
    legenda_figura: str = ""
    legenda_tabela: str = ""
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "FALHA" if self.erros else ("SUSPEITA" if self.avisos else "OK")


def parse_texto_bruto(texto: str) -> list[Questao]:
    """Interpreta números isolados como início de questão e (A)..(E) como alternativas."""
    questoes: list[Questao] = []
    atual: Questao | None = None
    letra_atual: str | None = None
    pagina_atual: int | None = None
    buffer: list[str] = []
    parte: str = "enunciado"

    def salvar_buffer() -> None:
        nonlocal buffer
        trecho = " ".join(x.strip() for x in buffer if x.strip()).strip()
        if atual is not None and trecho:
            if parte == "enunciado":
                atual.enunciado = (atual.enunciado + " " + trecho).strip()
            elif letra_atual is not None:
                atual.alternativas[letra_atual] = (
                    atual.alternativas.get(letra_atual, "") + " " + trecho
                ).strip()
        buffer = []

    def fechar_questao() -> None:
        nonlocal atual, letra_atual, parte, buffer
        salvar_buffer()
        if atual is not None:
            questoes.append(atual)
        atual = None
        letra_atual = None
        parte = "enunciado"
        buffer = []

    for linha in texto.splitlines():
        m_pag = re.search(r"=====\s*PÁGINA\s*(\d+)\s*=====", linha, re.IGNORECASE)
        if m_pag:
            pagina_atual = int(m_pag.group(1))
            continue
        if RE_CABECALHO.search(linha) or RE_RODAPE.match(linha):
            continue
        # Descarta cabeçalhos de seção, inclusive quando o extrator os cola
        # ao final da linha anterior (por exemplo, alternativa E + título da seção).
        if RE_CABECALHO_SECAO.match(linha):
            continue
        linha_sem_cabecalho = RE_CABECALHO_SECAO_EMBUTIDO.sub("", linha).rstrip()
        if not linha_sem_cabecalho.strip():
            continue
        linha = linha_sem_cabecalho
        # A legenda pode ocupar várias linhas. Quando surge Fonte:, recua até
        # o início reconhecível do título e remove o bloco inteiro do enunciado.
        if atual is not None and parte == "enunciado" and RE_FONTE.match(linha) and buffer:
            inicio = next((i for i, item in enumerate(buffer) if RE_INICIO_LEGENDA.match(item.strip())), None)
            if inicio is not None:
                linhas_legenda = [x.strip() for x in buffer[inicio:] if x.strip()]
                buffer = buffer[:inicio]
                legenda = " ".join(linhas_legenda + [linha.strip()]).strip()
                atual.legenda_figura = (atual.legenda_figura + " " + legenda).strip()
                continue
            titulo_legenda = buffer[-1].strip()
            if titulo_legenda and len(titulo_legenda) >= 12:
                buffer.pop()
                legenda = f"{titulo_legenda} {linha.strip()}".strip()
                atual.legenda_figura = (atual.legenda_figura + " " + legenda).strip()
                continue
        m_alt = RE_ALTERNATIVA.match(linha)
        if m_alt and atual is not None:
            salvar_buffer()
            letra_atual = m_alt.group(1)
            parte = "alternativa"
            buffer = [m_alt.group(2)]
            continue
        m_num = RE_NUM_QUESTAO.match(linha)
        if m_num:
            n = int(m_num.group(1))
            # O próximo número sequencial é um novo enunciado mesmo se a questão
            # anterior terminou na alternativa (E). Isso também deixa exposta
            # uma alternativa ausente, em vez de absorver a próxima questão.
            inicia_nova = (
                1 <= n <= 99
                and (
                    atual is None
                    or (atual is not None and n == atual.numero + 1)
                )
            )
            if inicia_nova:
                fechar_questao()
                atual = Questao(numero=n, pagina_pdf=pagina_atual)
                parte = "enunciado"
                letra_atual = None
                continue
        if atual is not None:
            buffer.append(linha.strip())
    fechar_questao()
    return questoes


def validar(questoes: list[Questao], min_questoes: int = 80) -> tuple[bool, list[str]]:
    problemas: list[str] = []
    numeros = [q.numero for q in questoes]
    if numeros:
        esperado = list(range(1, max(numeros) + 1))
        if numeros != esperado:
            problemas.append(f"Sequência quebrada: {len(numeros)} questões; esperado 1..{max(numeros)}")
    if len(questoes) < min_questoes:
        problemas.append(f"Total {len(questoes)} < mínimo {min_questoes}")
    duplicadas = sorted({n for n in numeros if numeros.count(n) > 1})
    if duplicadas:
        problemas.append(f"Questões duplicadas: {duplicadas}")

    for q in questoes:
        if len(q.enunciado.strip()) < TAM_MIN_ENUNCIADO:
            q.erros.append(f"enunciado curto ({len(q.enunciado.strip())} chars)")
        if RE_CABECALHO.search(q.enunciado) or RE_CABECALHO_SECAO_EMBUTIDO.search(q.enunciado):
            q.erros.append("cabeçalho vazou para o enunciado")
        if RE_INICIO_OUTRA_QUESTAO.search(q.enunciado):
            q.erros.append("enunciado contém início de outra questão")
        for letra in "ABCDE":
            if letra not in q.alternativas:
                q.erros.append(f"alternativa ({letra}) ausente")
                continue
            txt = q.alternativas[letra].strip()
            if len(txt) < TAM_MIN_ALTERNATIVA:
                q.erros.append(f"alternativa ({letra}) vazia ou truncada")
            if RE_CABECALHO.search(txt) or RE_CABECALHO_SECAO_EMBUTIDO.search(txt):
                q.erros.append(f"cabeçalho vazou para alternativa ({letra})")
        vals = [v.strip() for v in q.alternativas.values()]
        if len(vals) != len(set(vals)):
            q.erros.append("duas alternativas idênticas (indício de corte)")
        if q.enunciado.rstrip().endswith((" de", " a", " o", " e", " com", " para")):
            q.avisos.append("enunciado termina em palavra de ligação")
    return not any(q.status == "FALHA" for q in questoes) and not problemas, problemas


def carregar_json(caminho: Path) -> list[Questao]:
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return [
        Questao(
            numero=int(q["numero"]),
            enunciado=q.get("enunciado", ""),
            alternativas=q.get("alternativas", {}),
            pagina_pdf=q.get("pagina_pdf"),
            legenda_figura=q.get("legenda_figura", ""),
            legenda_tabela=q.get("legenda_tabela", ""),
        )
        for q in dados.get("questoes", [])
    ]


def imprimir_relatorio(questoes: list[Questao], problemas: list[str]) -> None:
    print(f"{'#':>3}  {'Status':<8}  {'Pág':>4}  {'Enun':>5}  {'Alt':>3}  Observações")
    print("-" * 90)
    for q in questoes:
        obs = "; ".join(q.erros + q.avisos) or "-"
        print(f"{q.numero:>3}  {q.status:<8}  {str(q.pagina_pdf or '-'):>4}  {len(q.enunciado):>5}  {len(q.alternativas):>3}  {obs[:80]}")
    print("-" * 90)
    print(f"Resumo: {len(questoes)} questões | OK={sum(q.status == 'OK' for q in questoes)} "
          f"SUSPEITA={sum(q.status == 'SUSPEITA' for q in questoes)} "
          f"FALHA={sum(q.status == 'FALHA' for q in questoes)}")
    for p in problemas:
        print(f"PROBLEMA GLOBAL: {p}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("arquivo", type=Path)
    ap.add_argument("--min-questoes", type=int, default=80)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    questoes = carregar_json(args.arquivo) if args.json else parse_texto_bruto(args.arquivo.read_text(encoding="utf-8"))
    ok, problemas = validar(questoes, args.min_questoes)
    imprimir_relatorio(questoes, problemas)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
