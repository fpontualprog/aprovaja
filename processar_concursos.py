#!/usr/bin/env python3
"""Processa localmente a coleta PCI para futura integração com APROVAJÁ."""
from __future__ import annotations
import csv, json, sys
from datetime import date
from pathlib import Path
PASTA_ENTRADA=Path(__file__).resolve().parent/"resultado_coleta_pci_v3"
ARQUIVO_ENTRADA=PASTA_ENTRADA/"concursos_pci_nordeste.json"
PASTA_SAIDA=PASTA_ENTRADA/"processamento_aprovaja_local"
CAMPOS=["uf","concurso","vagas","nivel","salario","inscricao_ate","situacao_prazo","campos_ausentes","fonte_url","coletado_em","fonte","observacao_status","motivo_exclusao"]
def ler_data(valor):
    if not isinstance(valor,str) or not valor.strip(): return None
    try: return date.fromisoformat(valor.strip())
    except ValueError: return None
def salvar_json(caminho,dados):
    tmp=caminho.with_suffix(caminho.suffix+".tmp"); tmp.write_text(json.dumps(dados,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(caminho)
def salvar_csv(caminho,dados):
    tmp=caminho.with_suffix(caminho.suffix+".tmp")
    with tmp.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=CAMPOS,delimiter=";",extrasaction="ignore"); w.writeheader()
        for item in dados: w.writerow({k:("" if item.get(k) is None else item.get(k)) for k in CAMPOS})
    tmp.replace(caminho)
def main():
    if not ARQUIVO_ENTRADA.exists(): print(f"ERRO: arquivo não encontrado: {ARQUIVO_ENTRADA}",file=sys.stderr); return 2
    try: origem=json.loads(ARQUIVO_ENTRADA.read_text(encoding="utf-8-sig"))
    except Exception as exc: print(f"ERRO ao ler JSON: {exc}",file=sys.stderr); return 2
    if not isinstance(origem,list): print("ERRO: o JSON deve conter uma lista.",file=sys.stderr); return 2
    hoje=date.today(); elegiveis=[]; historico=[]; excluidos=[]; problemas=[]; vistos=set(); duplicatas=0
    for indice,original in enumerate(origem,start=1):
        if not isinstance(original,dict): problemas.append({"linha":indice,"motivo":"registro_nao_e_objeto_json"}); continue
        item=dict(original); url=str(item.get("fonte_url") or "").strip().rstrip("/").casefold()
        if url and url in vistos: duplicatas+=1; problemas.append({"linha":indice,"motivo":"url_duplicada","fonte_url":item.get("fonte_url")}); continue
        if url: vistos.add(url)
        d=ler_data(item.get("inscricao_ate")); item["situacao_prazo"]="data_nao_informada" if d is None else ("prazo_vencido" if d<hoje else "prazo_futuro_ou_hoje_a_confirmar")
        item["observacao_status"]=("Excluído da base elegível: data de inscrição ausente ou inválida." if d is None else "Prazo vencido; mantido somente no histórico." if d<hoje else "Data futura ou de hoje; confirmar edital e situação efetiva das inscrições antes de anunciar como aberta.")
        if d is None: item["motivo_exclusao"]="data_inscricao_nao_informada_ou_invalida"; excluidos.append(item)
        elif d<hoje: historico.append(item)
        else: elegiveis.append(item)
    elegiveis.sort(key=lambda x:(x.get("inscricao_ate","9999-12-31"),x.get("uf",""),x.get("concurso","")))
    historico.sort(key=lambda x:(x.get("inscricao_ate",""),x.get("uf",""),x.get("concurso","")),reverse=True)
    excluidos.sort(key=lambda x:(x.get("uf",""),x.get("concurso","")))
    PASTA_SAIDA.mkdir(parents=True,exist_ok=True)
    for nome,regs in {"concursos_elegiveis_aprovaja":elegiveis,"historico_prazos_vencidos":historico,"excluidos_sem_data":excluidos}.items():
        salvar_json(PASTA_SAIDA/f"{nome}.json",regs); salvar_csv(PASTA_SAIDA/f"{nome}.csv",regs)
    rel={"data_processamento":hoje.isoformat(),"origem":str(ARQUIVO_ENTRADA.name),"total_origem":len(origem),"elegiveis_com_data_hoje_ou_futura":len(elegiveis),"historico_prazo_vencido":len(historico),"excluidos_sem_data_ou_invalida":len(excluidos),"urls_duplicadas_ignoradas":duplicatas,"registros_problematicos":problemas,"regras":{"data_ausente_nao_entra_na_base_elegivel":True,"prazo_vencido_separado_do_elegivel":True,"data_futura_nao_confirma_inscricao_aberta":True,"salario_ausente_permanece_null":True},"aviso":"Base elegível não comprova que as inscrições estejam abertas; verificar fonte oficial.","supabase_acessado":False,"aprovaja_alterado":False}
    salvar_json(PASTA_SAIDA/"relatorio_processamento.json",rel)
    print("PROCESSAMENTO LOCAL CONCLUÍDO"); print(f"Registros de origem: {len(origem)}"); print(f"Elegíveis com data hoje/futura (confirmar inscrições): {len(elegiveis)}"); print(f"Histórico com prazo vencido: {len(historico)}"); print(f"Excluídos por data ausente/inválida: {len(excluidos)}"); print(f"URLs duplicadas ignoradas: {duplicatas}"); print(f"Relatório: {PASTA_SAIDA/'relatorio_processamento.json'}"); print("Nenhum arquivo de origem foi alterado. APROVAJÁ e Supabase não foram acessados.")
    return 0
if __name__=="__main__": raise SystemExit(main())
