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
    for inicio in range(0, len(itens), 12):
        lote = itens[inicio:inicio + 12]
        prompt = {
            "evento": evento,
            "banca": banca,
            "instrucoes": (
                "Estruture cada item sem alterar seu texto original. Não invente gabarito. "
                "Retorne somente JSON válido no formato {\"questoes\":[{\"numero\":1,\"enunciado\":\"...\","
                "\"disciplina\":null,\"gabarito\":null,\"tem_imagem\":false,\"banca\":\"CEBRASPE\",\"concurso\":\"...\"}]}. "
                "Se a disciplina não for inequívoca, use null. Preserve a numeração recebida."
            ),
            "itens": [
                {k: v for k, v in item.items() if k != "imagens"}
                for item in lote
            ],
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
        if len(questoes) != len(lote):
            raise RuntimeError(
                f"A DeepSeek retornou {len(questoes)} questões para um lote de {len(lote)} "
                f"(início no item {inicio + 1}); lote rejeitado para evitar perda de questões."
            )

        # Reanexa metadados locais após a resposta da IA. Caminhos de imagens
        # não são enviados à DeepSeek; a correspondência primária é pela ordem do lote.
        for indice_local, questao in enumerate(questoes):
            origem = lote[indice_local] if indice_local < len(lote) else {}
            questao.setdefault("tem_imagem", bool(origem.get("tem_imagem", False)))
            questao["imagens"] = list(origem.get("imagens") or [])
            for campo in ("posicao_inicio", "posicao_fim", "arquivo_origem", "url_origem", "texto"):
                if campo in origem:
                    questao.setdefault(campo, origem[campo])
        saida.extend(questoes)
    return saida
