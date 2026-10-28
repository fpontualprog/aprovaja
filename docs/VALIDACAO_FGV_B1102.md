# Validação real do parser FGV — prova b1102

## Objetivo

Separar o sucesso dos testes unitários da validação estrutural de uma prova real. O workflow baixa a prova oficial FGV b1102, extrai texto, executa o validador, gera um JSON de inspeção e valida esse JSON.

## Estado das etapas

| Etapa | Estado | Evidência |
|---|---|---|
| Baseline: download e extração do PDF real | Concluído anteriormente | [Diagnóstico inicial](https://github.com/fpontualprog/aprovaja/actions/runs/40615961101) |
| Testes unitários do validador | Passaram no workflow mais recente observado | [Testes do parser](https://github.com/fpontualprog/aprovaja/actions/runs/40617041615) |
| Validação estrutural das 90 questões reais | Pendente de execução/inspeção do relatório mais recente | O workflow imprime status por questão |
| Geração e validação de saida_b1102.json | Pendente de inspeção do artefato | O workflow publica JSON, texto e PDF |
| Integração com Supabase | **Pausada** | Não enviar dados durante esta etapa |

## Critérios para liberar a extração

1. Confirmar 90 questões em sequência, sem duplicações ou lacunas.
2. Inspecionar todas as questões marcadas como FALHA ou SUSPEITA.
3. Corrigir bugs do parser separadamente de peculiaridades legítimas da prova.
4. Marcar no JSON as questões que exigem revisão manual por figura ou tabela.
5. Validar o JSON final e manter qualquer envio ao Supabase desativado até aprovação explícita.

## Limitações atuais

A detecção de imagem/tabela é feita por página do PDF e não garante, sozinha, que o recurso pertence a uma questão específica. Questões com recursos visuais devem ser revisadas manualmente. A validação estrutural não substitui a comparação visual com o PDF original.

## Gate contínuo

O workflow .github/workflows/debug-parser-fgv-real.yml executa manualmente e em push/pull request quando os scripts de validação, seus testes ou o próprio workflow são alterados. Falhas de validação interrompem a execução; os artefatos são publicados mesmo em caso de falha, para facilitar o diagnóstico.
