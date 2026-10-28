# Validação real do parser FGV — prova b1102

## Estado atual

**Aprovado estruturalmente para inspeção; ainda não homologado para publicação automática em massa.**

| Etapa | Estado | Evidência |
|---|---|---|
| PDF oficial baixado | Concluído — 28 páginas | [Execução real](https://github.com/fpontualprog/aprovaja/actions/runs/40617643875) |
| Extração de texto sem OCR | Concluído — texto bruto gerado | Artefato da execução |
| Testes unitários do validador | Concluído — 5/5 | [Testes do parser](https://github.com/fpontualprog/aprovaja/actions/runs/40617041615) |
| Validação estrutural do texto bruto | Concluído — 90 OK / 0 SUSPEITA / 0 FALHA | [Relatório por questão](https://github.com/fpontualprog/aprovaja/actions/runs/40617643875) |
| Geração e validação do JSON | Concluído — 90 OK / 0 SUSPEITA / 0 FALHA | [Artefatos para inspeção](https://github.com/fpontualprog/aprovaja/actions/runs/40617643875/artifacts/12785692910) |
| Inspeção estratificada JSON × PDF | **Pendente** | Checklist abaixo |
| Generalização para outra prova FGV | Pendente | Não executar antes da inspeção |
| Generalização para outra banca | Pendente | CEBRASPE e depois VUNESP/FCC |
| Supabase | **Desativado** | Gate explícito; nenhum envio nesta etapa |

## Amostra estratificada

Revisar no PDF original e registrar OK/DIVERGENTE com nota para cada item:

- [ ] Q1
- [ ] Q2
- [ ] Q3
- [ ] Q30
- [ ] Q45 (atenção à transição de página)
- [ ] Q46 (atenção à transição de página)
- [ ] Q60
- [ ] Q75
- [ ] Q89
- [ ] Q90
- [ ] Todas as questões com `tem_figura=true`
- [ ] Todas as questões com `tem_tabela=true`
- [ ] Questões com enunciado aparentemente cortado entre páginas

Use `scripts/comparar_json_pdf.py` para imprimir lado a lado o texto do JSON e a página indicada do texto bruto. Exemplo:

```bash
python scripts/comparar_json_pdf.py saida_b1102.json debug_b1102.txt --questoes 1,2,3,30,45,46,60,75,89,90 --todas-com-recursos
```

A comparação do texto bruto ajuda a localizar divergências do parser, mas a decisão final exige conferir visualmente o PDF. A saída do script é um auxílio, não um atestado automático de fidelidade.

## Critérios para homologar esta prova

1. Confirmar sequência 1–90, sem duplicações ou lacunas.
2. Comparar integralmente enunciado e alternativas A–E da amostra com o PDF.
3. Revisar todos os casos com figura/tabela e registrar se o recurso pertence à questão correta.
4. Investigar divergências e corrigir parser ou extração conforme a origem.
5. Guardar o registro de revisão e repetir a validação após cada correção.

## Limitações atuais

A detecção de imagem/tabela é feita por página e não garante que o recurso pertence a uma questão específica. A validação estrutural confere características formais; não comprova fidelidade semântica nem que a alternativa correta/gabarito foi identificado. O JSON de inspeção não deve ser importado em produção ainda.

## Gate de Supabase

A variável de repositório `SUPABASE_UPLOAD_ENABLED` é o interruptor auditável. O workflow de diagnóstico não possui uma etapa de upload configurada: mesmo que a variável seja ligada, a etapa de guarda falhará deliberadamente para evitar qualquer envio acidental. Só substituir esse bloqueio por um uploader real após homologação explícita e teste separado.

## Generalização posterior

Somente depois de concluir a amostra b1102:
1. Outra prova FGV (outro tipo do CPNU ou outra prova pública).
2. CEBRASPE, formato certo/errado.
3. VUNESP ou FCC, se estiverem no escopo do coletor.
