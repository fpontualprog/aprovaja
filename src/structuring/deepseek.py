"""Estrutura itens extraídos com recuperação conservadora de falhas da IA."""
from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

TAMANHO_LOTE = 12


def _questao_pendente(origem: dict[str, Any], evento: str, banca: str, motivo: str) -> dict[str, Any]:
    """Preserva integralmente o item original quando a IA não consegue estruturá-lo."""
    texto = origem.get("texto") or origem.get("enunciado") or ""
    resultado = {
        "numero": origem.get("numero"),
        "enunciado": texto,
        "texto": texto,
        "disciplina": None,
        "gabarito": None,
        "banca": banca,
        "concurso": evento,
        "tem_imagem": bool(origem.get("tem_imagem", False)),
        "imagens": list(origem.get("imagens") or []),
        "status_estruturacao": "pendente_revisao",
        "motivo_pendencia": motivo,
    }
    for campo in ("posicao_inicio", "posicao_fim", "arquivo_origem", "url_origem"):
        if campo in origem:
            resultado[campo] = origem[campo]
    return resultado


def _anexar_origem(questao: dict[str, Any], origem: dict[str, Any]) -> dict[str, Any]:
    """Reanexa metadados e mantém o texto original como referência de auditoria."""
    resultado = dict(questao)
    resultado.setdefault("tem_imagem", bool(origem.get("tem_imagem", False)))
    resultado["imagens"] = list(origem.get("imagens") or [])
    for campo in ("posicao_inicio", "posicao_fim", "arquivo_origem", "url_origem", "texto"):
        if campo in origem:
            resultado.setdefault(campo, origem[campo])
    return resultado


def _chamar_ia(client: Any, lote: list[dict], evento: str, banca: str) -> list[dict]:
    prompt = {
        "evento": evento,
        "banca": banca,
        "instrucoes": (
            "Estruture cada item sem alterar seu texto original. Não invente gabarito. "
            "Retorne somente JSON válido no formato "
            "{\"questoes\":[{\"numero\":1,\"enunciado\":\"...\",\"disciplina\":null,"
            "\"gabarito\":null,\"tem_imagem\":false,\"banca\":\"CEBRASPE\",\"concurso\":\"...\"}]}. "
            "Se a disciplina não for inequívoca, use null. Preserve a numeração recebida "
            "e retorne exatamente uma questão para cada item de entrada, na mesma ordem."
        ),
        "itens": [{k: v for k, v in item.items() if k != "imagens"} for item in lote],
    }
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "Você estrutura dados de questões de concursos com fidelidade ao texto-fonte."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        temperature=0,
        max_tokens=4096,
    )
    content = (response.choices[0].message.content or "").strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    parsed = json.loads(content)
    questoes = parsed.get("questoes") if isinstance(parsed, dict) else None
    if not isinstance(questoes, list) or not all(isinstance(q, dict) for q in questoes):
        raise ValueError("A resposta da DeepSeek não contém uma lista válida de questões.")
    return questoes


def _validar_numeracao(questoes: list[dict], lote: list[dict]) -> None:
    """Evita associar a resposta de uma questão à origem de outra."""
    for indice, (questao, origem) in enumerate(zip(questoes, lote), start=1):
        numero_origem = origem.get("numero")
        numero_saida = questao.get("numero")
        if numero_origem is not None and numero_saida is not None:
            try:
                coincide = int(numero_origem) == int(numero_saida)
            except (TypeError, ValueError):
                coincide = str(numero_origem).strip() == str(numero_saida).strip()
            if not coincide:
                raise ValueError(
                    f"Numeração divergente na posição {indice}: origem={numero_origem!r}, "
                    f"IA={numero_saida!r}."
                )


def estruturar_itens(itens: list[dict], evento: str, banca: str = "CEBRASPE") -> list[dict]:
    """Estrutura por lotes; tenta recuperar individualmente e preserva falhas para revisão."""
    if not itens:
        return []
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("A variável DEEPSEEK_API_KEY não está configurada nos Secrets/ambiente.")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    saida: list[dict] = []

    for inicio in range(0, len(itens), TAMANHO_LOTE):
        lote = itens[inicio:inicio + TAMANHO_LOTE]
        try:
            questoes = _chamar_ia(client, lote, evento, banca)
            if len(questoes) != len(lote):
                raise ValueError(
                    f"A IA retornou {len(questoes)} questões para {len(lote)} itens de entrada."
                )
            _validar_numeracao(questoes, lote)
            saida.extend(_anexar_origem(q, origem) for q, origem in zip(questoes, lote))
            continue
        except Exception as exc:
            motivo_lote = f"Lote não validado: {type(exc).__name__}: {exc}"

        # O lote incompleto é recuperado item a item; não se chama a própria
        # função recursivamente, evitando repetição infinita em falhas persistentes.
        for origem in lote:
            try:
                individuais = _chamar_ia(client, [origem], evento, banca)
                if len(individuais) == 1:
                    _validar_numeracao(individuais, [origem])
                    saida.append(_anexar_origem(individuais[0], origem))
                    continue
                motivo = f"{motivo_lote} A tentativa individual não retornou exatamente uma questão."
            except Exception as exc:
                motivo = f"{motivo_lote} Falha individual: {type(exc).__name__}: {exc}"
            saida.append(_questao_pendente(origem, evento, banca, motivo))

    if len(saida) != len(itens):
        raise RuntimeError(
            f"Falha de integridade: entrada com {len(itens)} itens e saída com {len(saida)}."
        )
    return saida
