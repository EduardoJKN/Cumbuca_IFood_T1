import os
import json
import time
import datetime  # Mantenha esta importação
from datetime import timedelta  # Adicione esta importação
import base64
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, Border, Side, Alignment, PatternFill
from openpyxl.utils import get_column_letter

# Função auxiliar para obter o horário correto
def get_local_time():
    """Retorna o horário atual ajustado para UTC-3 (Brasília)"""
    return datetime.datetime.now() - timedelta(hours=3)

# Configurações do Telegram (removi os valores hardcoded por segurança)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Configurações do GitHub
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPOSITORY = os.environ.get('GITHUB_REPOSITORY')
GITHUB_ACTOR = os.environ.get('GITHUB_ACTOR')

# ... (mantenha todas as outras funções como estão, exceto pelas substituições abaixo)

# Substitua todas as ocorrências de datetime.timedelta(hours=3) por get_local_time()

# Na função salvar_estado_produtos:
def salvar_estado_produtos(dados_produtos):
    """Salva o estado atual dos produtos para comparação futura"""
    arquivo_estado = 'estado_produtos.json'
    
    estado = {}
    for produto in dados_produtos:
        chave = f"{produto['Seção']}|{produto['Produto']}"
        estado[chave] = {
            'Preço': produto['Preço'],
            'Descrição': produto.get('Descrição', ''),
            'Status': produto.get('Status', 'ON'),
            'Última verificação': get_local_time().strftime('%Y-%m-%d %H:%M:%S')  # Modificado aqui
        }
    
    with open(arquivo_estado, 'w', encoding='utf-8') as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Estado atual salvo com {len(estado)} produtos")
    fazer_upload_github(arquivo_estado, arquivo_estado)
    return estado

# Na função gerar_dashboard_html:
def gerar_dashboard_html(historico):
    """Gera um dashboard HTML com o status de todos os produtos e histórico"""
    arquivo_dashboard = 'index.html'
    
    # ... (código anterior mantido)
    
    html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <!-- ... (cabeçalho mantido) -->
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Dashboard de Produtos iFood</h1>
                <p class="timestamp">Última atualização: {get_local_time().strftime('%d/%m/%Y %H:%M:%S')}</p>  <!-- Modificado aqui -->
            </div>
            <!-- ... (restante do HTML mantido) -->
    """
    # ... (restante da função mantido)

# Na função enviar_alerta_telegram:
def enviar_alerta_telegram(mensagem, produtos_off=None, produtos_desaparecidos=None, total_produtos_ativos=0, todos_produtos=None):
    """Envia alerta para um grupo no Telegram"""
    try:
        texto = f"🚨 ALERTA: Monitoramento de Produtos iFood 🚨\n\n"
        texto += f"Data/Hora: {get_local_time().strftime('%d/%m/%Y %H:%M:%S')}\n\n"  # Modificado aqui
        # ... (restante da função mantido)

# Na função salvar_log:
def salvar_log(mensagem):
    """Salva mensagem de log em arquivo"""
    arquivo_log = 'monitoramento_log.txt'
    baixar_arquivo_github(arquivo_log)
    
    timestamp = get_local_time().strftime('%Y-%m-%d %H:%M:%S')  # Modificado aqui
    
    with open(arquivo_log, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {mensagem}\n")
    
    fazer_upload_github(arquivo_log, arquivo_log)

# Na função monitorar_produtos:
def monitorar_produtos():
    """Função principal para monitorar produtos"""
    timestamp = get_local_time().strftime('%Y-%m-%d %H:%M:%S')  # Modificado aqui
    print(f"\n🔍 Iniciando monitoramento de produtos em {timestamp}")
    salvar_log(f"Iniciando monitoramento de produtos")
    
    # ... (restante da função mantido)

# ... (mantenha o restante do código igual)

if __name__ == "__main__":
    # Executar monitoramento
    resultado = monitorar_produtos()
    
    # Imprimir resumo
    if resultado:
        print("\n📋 Resumo do monitoramento:")
        print(f"- Total de produtos: {resultado['total_produtos']}")
        print(f"- Produtos OFF: {len(resultado['produtos_off'])}")
        print(f"- Produtos desaparecidos: {len(resultado['produtos_desaparecidos'])}")
        print(f"- Produtos ativos: {resultado['total_produtos_ativos']}")
        print(f"- Timestamp: {resultado['timestamp']}")
