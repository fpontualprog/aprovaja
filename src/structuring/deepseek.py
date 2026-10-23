"""Estrutura itens extraídos usando a API compatível da DeepSeek."""
from __future__ import annotations
import json
import os
from openai import OpenAI

def estruturar_itens(itens: list[dict], evento: str, banca: str = "CEBRASPE") -> list[dict]:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("A variável DEEPSEEK_API_KEY não está configurada nos Secrets/ambiente.")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    saida = []
    # Lotes pequenos reduzem o risco de truncamento e facilitam diagnóstico.
    for inicio in range(0, len(itens), 8):
        lote = itens[inicio:inicio + 8]
        prompt = {
            "evento": evento,
            "banca": banca,
            "instrucoes": (
                "Estruture cada item sem alterar seu texto original. Não invente gabarito. "
                "Retorne somente JSON válido no formato {\"questoes\":[{\"numero\":1,\"enunciado\":\"...\","
                "\"disciplina\":null,\"gabarito\":null,\"banca\":\"CEBRASPE\",\"concurso\":\"...\"}]}. "
                "Se a disciplina não for inequívoca, use null. Preserve a numeração recebida."
            ),
            "itens": lote,
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
        content = response.choices[0].message.content or ""
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            parsed = json.loads(content)
            questoes = parsed["questoes"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RuntimeError(f"A DeepSeek retornou JSON inválido no lote iniciado no item {inicio + 1}.") from exc
        if not isinstance(questoes, list):
            raise RuntimeError("A resposta da DeepSeek não contém uma lista 'questoes'.")
        saida.extend(questoes)
    return saida
