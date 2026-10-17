# APROVAJÁ — coletor PCI Concursos

Pipeline isolada para coleta e processamento de concursos do PCI Concursos antes de qualquer integração com o Supabase.

## Regras funcionais
- Prazo vencido: fica no histórico, não na lista de oportunidades elegíveis.
- Data ausente/inválida: exclui da base elegível.
- Data hoje/futura: elegível para análise, mas não confirma que as inscrições estejam abertas.
- Salário ausente: `null` no JSON; nunca estimar.
- Coleta parcial/falha: não publica dados novos.
- Nenhum script deste repositório acessa ou modifica o Supabase.

## GitHub Actions
Workflow em `.github/workflows/coleta-diaria.yml` agendado diariamente às 10:15 UTC (07:15 no horário de Recife) e com execução manual em **Actions → Coleta diária de concursos PCI → Run workflow**.

## Arquivos publicados
Após uma execução bem-sucedida, os dados ficam em `data/`:
- `concursos_elegiveis.json`: registros com data válida hoje/futura; confirmar situação da inscrição na fonte.
- `historico_prazos_vencidos.json`: registros vencidos.
- `concursos_pci_origem.json`: dados de origem.
- `relatorio_processamento.json`, `relatorio_coleta.json`, `relatorio_validacao_qualidade.json`: diagnóstico.

O workflow só faz commit em `data/` após coleta e validação bem-sucedidas. A base original em `resultado_coleta_pci_v3/` é gerada em cada execução e não é versionada.

## Configuração
1. Confirme que os arquivos estão na branch padrão.
2. Abra **Actions** e execute manualmente uma primeira vez.
3. Inspecione logs e os JSON publicados.
4. Somente depois prepare a rotina de leitura do Supabase. Nenhuma sincronização com banco está incluída nesta etapa.

## Desenvolvimento local
```bash
python -m pip install -r requirements.txt
python coletor_pci.py --teste-protecao
python coletor_pci.py
python validar_coleta.py
python processar_concursos.py
```
