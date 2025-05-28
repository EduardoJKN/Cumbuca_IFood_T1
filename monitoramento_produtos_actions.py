import os
import json
import time
import datetime
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

# Configurações do Telegram
# Estas serão substituídas pelos secrets do GitHub Actions
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "7538392371:AAH3-eZcq7wrf3Uycv9zPq1PjlSvWfLtYlc")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1002593932783")

# Configurações do GitHub
# Estas serão substituídas pelos secrets do GitHub Actions
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")
GITHUB_ACTOR = os.environ.get("GITHUB_ACTOR", "")

# Função para obter o horário atual no fuso horário de Brasília (UTC-3)
def horario_brasil():
    """Retorna o horário atual no fuso horário de Brasília (UTC-3)"""
    return datetime.datetime.now() - datetime.timedelta(hours=3)

def limpar_preco(texto):
    """Limpa e formata o texto do preço, removendo repetições"""
    if not texto:
        return None
    
    if "R$" in texto:
        partes = texto.split("R$")
        if len(partes) > 1:
            prefixo = partes[0].strip() + " " if partes[0].strip() else ""
            valor = "R$" + partes[1].split()[0].strip()
            return prefixo + valor
    
    return texto.strip()

def extrair_preco(product):
    """Extrai e formata o preço do produto sem repetições"""
    try:
        try:
            price_discount = product.find_element(By.CLASS_NAME, "dish-card__price--discount").text.strip()
            price_discount = limpar_preco(price_discount)
        except NoSuchElementException:
            price_discount = None

        try:
            price_original = product.find_element(By.CLASS_NAME, "dish-card__price--original").text.strip()
            price_original = limpar_preco(price_original)
        except NoSuchElementException:
            price_original = None

        try:
            price_normal = product.find_element(By.CLASS_NAME, "dish-card__price").text.strip()
            price_normal = limpar_preco(price_normal)
        except NoSuchElementException:
            price_normal = None

        if price_discount and price_original:
            return f"De {price_original} por {price_discount}"
        elif price_discount:
            return price_discount
        elif price_original:
            return price_original
        elif price_normal:
            return price_normal
        else:
            return "Preço não encontrado"

    except Exception as e:
        print(f"Erro ao extrair preço: {str(e)}")
        return "Erro ao obter preço"

def salvar_estado_produtos(dados_produtos):
    """Salva o estado atual dos produtos para comparação futura"""
    # No GitHub Actions, salvamos no diretório de trabalho
    arquivo_estado = "estado_produtos.json"
    
    # Criar dicionário com informações essenciais
    estado = {}
    for produto in dados_produtos:
        # Usar nome do produto como chave
        chave = f"{produto["Seção"]}|{produto["Produto"]}"
        estado[chave] = {
            "Preço": produto["Preço"],
            "Descrição": produto.get("Descrição", ""),
            "Status": produto.get("Status", "ON"),
            "Última verificação": horario_brasil().strftime("%Y-%m-%d %H:%M:%S")
        }
    
    # Salvar no arquivo
    with open(arquivo_estado, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Estado atual salvo com {len(estado)} produtos")
    
    # Fazer upload do arquivo para o GitHub
    fazer_upload_github(arquivo_estado, arquivo_estado)
    
    return estado

def carregar_estado_anterior():
    """Carrega o estado anterior dos produtos para comparação"""
    arquivo_estado = "estado_produtos.json"
    
    # Tentar baixar o arquivo do GitHub primeiro
    baixar_arquivo_github(arquivo_estado)
    
    if not os.path.exists(arquivo_estado):
        print("⚠️ Nenhum estado anterior encontrado. Esta parece ser a primeira execução.")
        return {}
    
    try:
        with open(arquivo_estado, "r", encoding="utf-8") as f:
            estado = json.load(f)
            print(f"✅ Estado anterior carregado com {len(estado)} produtos")
            return estado
    except Exception as e:
        print(f"❌ Erro ao carregar estado anterior: {str(e)}")
        return {}

def carregar_historico_status():
    """Carrega o histórico de status dos produtos"""
    arquivo_historico = "historico_status.json"
    
    # Tentar baixar o arquivo do GitHub primeiro
    baixar_arquivo_github(arquivo_historico)
    
    if not os.path.exists(arquivo_historico):
        print("⚠️ Nenhum histórico encontrado. Criando novo arquivo de histórico.")
        return {}
    
    try:
        with open(arquivo_historico, "r", encoding="utf-8") as f:
            historico = json.load(f)
            print(f"✅ Histórico carregado com {len(historico)} produtos")
            return historico
    except Exception as e:
        print(f"❌ Erro ao carregar histórico: {str(e)}")
        return {}

def atualizar_historico_status(dados_produtos, produtos_desaparecidos):
    """Atualiza o histórico de status dos produtos"""
    arquivo_historico = "historico_status.json"
    historico = carregar_historico_status()
    
    timestamp = horario_brasil().strftime("%Y-%m-%d %H:%M:%S")
    
    # Atualizar produtos atuais
    for produto in dados_produtos:
        chave = f"{produto["Seção"]}|{produto["Produto"]}"
        if chave not in historico:
            historico[chave] = {
                "nome": produto["Produto"],
                "secao": produto["Seção"],
                "status_atual": produto["Status"],
                "preco_atual": produto["Preço"],
                "ultima_verificacao": timestamp,
                "historico": []
            }
        else:
            # Se o status mudou, adicionar ao histórico
            if historico[chave]["status_atual"] != produto["Status"]:
                historico[chave]["historico"].append({
                    "status": historico[chave]["status_atual"],
                    "preco": historico[chave]["preco_atual"],
                    "timestamp": historico[chave]["ultima_verificacao"]
                })
            
            # Atualizar status atual
            historico[chave]["status_atual"] = produto["Status"]
            historico[chave]["preco_atual"] = produto["Preço"]
            historico[chave]["ultima_verificacao"] = timestamp
    
    # Atualizar produtos desaparecidos
    for produto in produtos_desaparecidos:
        chave = f"{produto["Seção"]}|{produto["Produto"]}"
        if chave not in historico:
            historico[chave] = {
                "nome": produto["Produto"],
                "secao": produto["Seção"],
                "status_atual": "OFF (Desapareceu)",
                "preco_atual": produto["Preço"],
                "ultima_verificacao": timestamp,
                "historico": []
            }
        else:
            # Se o status mudou, adicionar ao histórico
            if historico[chave]["status_atual"] != "OFF (Desapareceu)":
                historico[chave]["historico"].append({
                    "status": historico[chave]["status_atual"],
                    "preco": historico[chave]["preco_atual"],
                    "timestamp": historico[chave]["ultima_verificacao"]
                })
            
            # Atualizar status atual
            historico[chave]["status_atual"] = "OFF (Desapareceu)"
            historico[chave]["ultima_verificacao"] = timestamp
    
    # Salvar histórico atualizado
    with open(arquivo_historico, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Histórico atualizado com {len(historico)} produtos")
    
    # Fazer upload do arquivo para o GitHub
    fazer_upload_github(arquivo_historico, arquivo_historico)
    
    return historico

def calcular_estatisticas_produto(historico_produto):
    """Calcula estatísticas para um produto com base em seu histórico"""
    if not historico_produto["historico"]:
        return {
            "total_mudancas": 0,
            "tempo_medio_on": "N/A",
            "tempo_medio_off": "N/A",
            "porcentagem_on": 100 if historico_produto["status_atual"] == "ON" else 0,
            "ultima_mudanca": "Nunca"
        }
    
    # Adicionar o status atual ao histórico para cálculos
    historico_completo = historico_produto["historico"] + [{
        "status": historico_produto["status_atual"],
        "timestamp": historico_produto["ultima_verificacao"]
    }]
    
    # Ordenar histórico por timestamp
    historico_ordenado = sorted(historico_completo, key=lambda x: x["timestamp"])
    
    # Calcular estatísticas
    total_mudancas = len(historico_produto["historico"])
    
    # Calcular tempos médios e porcentagem
    tempo_total_on = 0
    tempo_total_off = 0
    contagem_on = 0
    contagem_off = 0
    
    for i in range(len(historico_ordenado) - 1):
        status_atual = historico_ordenado[i]["status"]
        timestamp_atual = datetime.datetime.strptime(historico_ordenado[i]["timestamp"], "%Y-%m-%d %H:%M:%S")
        timestamp_proximo = datetime.datetime.strptime(historico_ordenado[i+1]["timestamp"], "%Y-%m-%d %H:%M:%S")
        
        duracao = (timestamp_proximo - timestamp_atual).total_seconds() / 3600  # em horas
        
        if status_atual == "ON":
            tempo_total_on += duracao
            contagem_on += 1
        else:
            tempo_total_off += duracao
            contagem_off += 1
    
    # Calcular médias
    tempo_medio_on = tempo_total_on / contagem_on if contagem_on > 0 else 0
    tempo_medio_off = tempo_total_off / contagem_off if contagem_off > 0 else 0
    
    # Calcular porcentagem de tempo ON
    tempo_total = tempo_total_on + tempo_total_off
    porcentagem_on = (tempo_total_on / tempo_total * 100) if tempo_total > 0 else (100 if historico_produto["status_atual"] == "ON" else 0)
    
    # Última mudança
    if historico_produto["historico"]:
        ultima_mudanca = historico_produto["historico"][-1]["timestamp"]
    else:
        ultima_mudanca = "Nunca"
    
    return {
        "total_mudancas": total_mudancas,
        "tempo_medio_on": f"{tempo_medio_on:.2f} horas" if contagem_on > 0 else "N/A",
        "tempo_medio_off": f"{tempo_medio_off:.2f} horas" if contagem_off > 0 else "N/A",
        "porcentagem_on": round(porcentagem_on, 2),
        "ultima_mudanca": ultima_mudanca
    }

def gerar_dashboard_html(historico):
    """Gera um dashboard HTML responsivo com o status de todos os produtos e histórico"""
    arquivo_dashboard = "index.html"
    
    # Agrupar produtos por seção
    produtos_por_secao = {}
    for chave, info in historico.items():
        secao = info["secao"]
        if secao not in produtos_por_secao:
            produtos_por_secao[secao] = []
        
        # Calcular estatísticas para o produto
        estatisticas = calcular_estatisticas_produto(info)
        info["estatisticas"] = estatisticas
        
        produtos_por_secao[secao].append(info)
    
    # Contar produtos ON e OFF
    total_produtos = len(historico)
    produtos_off = sum(1 for info in historico.values() if info["status_atual"] != "ON")
    produtos_on = total_produtos - produtos_off
    
    # Contar produtos desaparecidos
    produtos_desaparecidos = sum(1 for info in historico.values() if "Desapareceu" in info["status_atual"])
    
    # Gerar HTML
    html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dashboard de Produtos iFood</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{
                font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 10px;
                background-color: #f5f5f5;
                color: #333;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                background-color: white;
                padding: 15px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            h1, h2, h3 {{
                color: #ff6000;
                margin-top: 0;
            }}
            h1 {{ font-size: 1.8em; }}
            h3 {{ font-size: 1.1em; }}
            .header {{
                display: flex;
                flex-direction: column;
                align-items: flex-start;
                margin-bottom: 15px;
                border-bottom: 1px solid #eee;
                padding-bottom: 10px;
            }}
            .header h1 {{ margin-bottom: 5px; }}
            .timestamp {{
                color: #666;
                font-size: 0.9em;
            }}
            .stats {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 15px;
                margin-bottom: 15px;
            }}
            .stat-card {{
                padding: 10px;
                border-radius: 8px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                text-align: center;
            }}
            .stat-card.total {{
                background-color: #e3f2fd;
                border-left: 5px solid #2196f3;
            }}
            .stat-card.on {{
                background-color: #e8f5e9;
                border-left: 5px solid #4caf50;
            }}
            .stat-card.off {{
                background-color: #ffebee;
                border-left: 5px solid #f44336;
            }}
            .stat-value {{
                font-size: 1.8em;
                font-weight: bold;
                margin: 5px 0;
            }}
            .stat-card h3 {{ margin-bottom: 5px; }}
            .stat-card div {{ font-size: 0.9em; color: #666; }}
            .section {{
                margin-bottom: 20px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 15px;
                display: block;
                overflow-x: auto;
                white-space: nowrap;
            }}
            th, td {{
                padding: 10px 12px;
                text-align: left;
                border-bottom: 1px solid #ddd;
                white-space: normal;
            }}
            th {{
                background-color: #f8f8f8;
                font-weight: bold;
            }}
            tr:hover {{
                background-color: #f5f5f5;
            }}
            .status {{
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 0.9em;
                white-space: nowrap;
            }}
            .status-on {{
                background-color: #e8f5e9;
                color: #2e7d32;
            }}
            .status-off {{
                background-color: #ffebee;
                color: #c62828;
            }}
            .status-desapareceu {{
                background-color: #fff3e0;
                color: #e65100;
            }}
            .footer {{
                margin-top: 20px;
                text-align: center;
                color: #666;
                font-size: 0.9em;
                border-top: 1px solid #eee;
                padding-top: 15px;
            }}
            .accordion {{
                background-color: #f8f8f8;
                color: #444;
                cursor: pointer;
                padding: 12px 15px;
                width: 100%;
                text-align: left;
                border: none;
                outline: none;
                transition: 0.4s;
                border-radius: 4px;
                margin-bottom: 5px;
                font-weight: bold;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .active, .accordion:hover {{
                background-color: #eee;
            }}
            .panel {{
                padding: 0 15px;
                background-color: white;
                max-height: 0;
                overflow: hidden;
                transition: max-height 0.2s ease-out;
                margin-bottom: 10px;
            }}
            .section-count {{
                background-color: #ff6000;
                color: white;
                padding: 2px 8px;
                border-radius: 12px;
                font-size: 0.8em;
                white-space: nowrap;
            }}
            .search-container {{
                margin-bottom: 15px;
            }}
            #searchInput {{
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 1em;
                box-sizing: border-box;
            }}
            .hidden {{
                display: none;
            }}
            .filters {{
                display: flex;
                gap: 8px;
                margin-bottom: 15px;
                flex-wrap: wrap;
            }}
            .filter-btn {{
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                background-color: #f0f0f0;
                cursor: pointer;
                transition: background-color 0.3s;
                font-size: 0.9em;
            }}
            .filter-btn:hover, .filter-btn.active {{
                background-color: #ff6000;
                color: white;
            }}
            .legenda {{
                margin: 15px 0;
                padding: 10px;
                background-color: #f9f9f9;
                border-radius: 4px;
                border: 1px solid #eee;
            }}
            .legenda h3 {{ margin-bottom: 8px; }}
            .legenda-item {{
                display: flex;
                align-items: center;
                margin-bottom: 5px;
                font-size: 0.9em;
            }}
            .legenda-cor {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                margin-right: 8px;
                flex-shrink: 0;
            }}
            .legenda-cor.on {{
                background-color: #e8f5e9;
                border: 1px solid #2e7d32;
            }}
            .legenda-cor.off {{
                background-color: #ffebee;
                border: 1px solid #c62828;
            }}
            .legenda-cor.desapareceu {{
                background-color: #fff3e0;
                border: 1px solid #e65100;
            }}
            .history-container {{
                margin-top: 10px;
                padding: 10px;
                background-color: #f9f9f9;
                border-radius: 4px;
                border: 1px solid #eee;
            }}
            .history-title {{
                font-weight: bold;
                margin-bottom: 8px;
                color: #555;
                display: flex;
                justify-content: space-between;
                align-items: center;
                font-size: 1em;
            }}
            .history-toggle {{
                background-color: #f0f0f0;
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 0.8em;
            }}
            .history-list {{
                max-height: 0;
                overflow: hidden;
                transition: max-height 0.3s ease-out;
            }}
            .history-list.show {{
                max-height: 300px;
                overflow-y: auto;
            }}
            .history-item {{
                padding: 6px;
                border-bottom: 1px solid #eee;
                display: flex;
                justify-content: space-between;
                align-items: center;
                font-size: 0.9em;
            }}
            .history-item:last-child {{
                border-bottom: none;
            }}
            .history-status {{
                font-weight: bold;
                flex-basis: 100px;
                flex-shrink: 0;
            }}
            .history-status.on {{ color: #2e7d32; }}
            .history-status.off {{ color: #c62828; }}
            .history-status.desapareceu {{ color: #e65100; }}
            .history-price {{ flex-basis: 100px; text-align: right; flex-shrink: 0; }}
            .history-date {{
                color: #666;
                font-size: 0.9em;
                flex-basis: 150px;
                text-align: right;
                flex-shrink: 0;
            }}
            .stats-container {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
                gap: 8px;
                margin-top: 10px;
            }}
            .stat-item {{
                background-color: #f0f0f0;
                padding: 6px;
                border-radius: 4px;
                text-align: center;
            }}
            .stat-item-label {{
                font-size: 0.75em;
                color: #666;
            }}
            .stat-item-value {{
                font-weight: bold;
                font-size: 1em;
                margin-top: 3px;
            }}
            .availability-bar {{
                height: 15px;
                width: 100%;
                min-width: 80px;
                background-color: #ffcdd2;
                border-radius: 8px;
                overflow: hidden;
                margin-top: 5px;
            }}
            .availability-fill {{
                height: 100%;
                background-color: #a5d6a7;
                border-radius: 8px 0 0 8px;
            }}
            /* Ajustes para mobile */
            @media (max-width: 600px) {{
                body {{ padding: 5px; }}
                .container {{ padding: 10px; }}
                h1 {{ font-size: 1.5em; }}
                .header {{ flex-direction: column; align-items: flex-start; }}
                .stats {{ grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; }}
                .stat-value {{ font-size: 1.5em; }}
                .accordion {{ padding: 10px 12px; }}
                .panel {{ padding: 0 10px; }}
                th, td {{ padding: 8px 10px; font-size: 0.9em; }}
                .filters {{ gap: 5px; }}
                .filter-btn {{ padding: 5px 10px; font-size: 0.85em; }}
                .history-item {{ flex-wrap: wrap; }}
                .history-price, .history-date {{ flex-basis: auto; width: 50%; text-align: left; margin-top: 3px; }}
                .history-date {{ text-align: right; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Dashboard de Produtos iFood</h1>
                <p class="timestamp">Última atualização: {horario_brasil().strftime("%d/%m/%Y %H:%M:%S")}</p>
            </div>
            
            <div class="stats">
                <div class="stat-card total">
                    <h3>Total</h3>
                    <div class="stat-value">{total_produtos}</div>
                </div>
                <div class="stat-card on">
                    <h3>ON</h3>
                    <div class="stat-value">{produtos_on}</div>
                </div>
                <div class="stat-card off">
                    <h3>OFF</h3>
                    <div class="stat-value">{produtos_off}</div>
                    <div>({produtos_desaparecidos} desaparecidos)</div>
                </div>
            </div>
            
            <div class="legenda">
                <h3>Legenda de Status:</h3>
                <div class="legenda-item">
                    <div class="legenda-cor on"></div>
                    <div><strong>ON</strong> - Disponível</div>
                </div>
                <div class="legenda-item">
                    <div class="legenda-cor off"></div>
                    <div><strong>OFF</strong> - Indisponível</div>
                </div>
                <div class="legenda-item">
                    <div class="legenda-cor desapareceu"></div>
                    <div><strong>OFF (Desapareceu)</strong> - Removido</div>
                </div>
            </div>
            
            <div class="search-container">
                <input type="text" id="searchInput" placeholder="Buscar produtos...">
            </div>
            
            <div class="filters">
                <button class="filter-btn active" data-filter="all">Todos</button>
                <button class="filter-btn" data-filter="on">Apenas ON</button>
                <button class="filter-btn" data-filter="off">Apenas OFF</button>
                <button class="filter-btn" data-filter="desapareceu">Apenas Desaparecidos</button>
                <button class="filter-btn" data-filter="changed">Mudaram Recentemente</button>
            </div>
    """
    
    # Adicionar seções com produtos
    for secao, produtos in sorted(produtos_por_secao.items()):
        produtos_off_secao = sum(1 for p in produtos if p["status_atual"] != "ON")
        produtos_desaparecidos_secao = sum(1 for p in produtos if "Desapareceu" in p["status_atual"])
        
        html += f"""
            <div class="section">
                <button class="accordion">
                    <span>{secao}</span>
                    <span class="section-count">{len(produtos)} produtos ({produtos_off_secao} OFF)</span>
                </button>
                <div class="panel">
                    <table>
                        <thead>
                            <tr>
                                <th>Produto</th>
                                <th>Preço</th>
                                <th>Status</th>
                                <th>Disponibilidade</th>
                                <th>Última Verificação</th>
                            </tr>
                        </thead>
                        <tbody>
        """
        
        for produto in sorted(produtos, key=lambda x: x["nome"]):
            # Determinar classe de status
            if "Desapareceu" in produto["status_atual"]:
                status_class = "status-desapareceu"
                filtro_class = "produto-row filter-off filter-desapareceu"
                status_display = "OFF (Desapareceu)"
            elif produto["status_atual"] == "ON":
                status_class = "status-on"
                filtro_class = "produto-row filter-on"
                status_display = "ON"
            else:
                status_class = "status-off"
                filtro_class = "produto-row filter-off"
                status_display = "OFF"
            
            # Determinar se o produto mudou recentemente (nas últimas 24 horas)
            mudou_recentemente = False
            if produto["historico"]:
                ultima_mudanca = datetime.datetime.strptime(produto["historico"][-1]["timestamp"], "%Y-%m-%d %H:%M:%S")
                agora = horario_brasil()
                if (agora - ultima_mudanca).total_seconds() < 24 * 3600:  # 24 horas em segundos
                    mudou_recentemente = True
                    filtro_class += " filter-changed"
            
            # Barra de disponibilidade
            porcentagem_on = produto["estatisticas"]["porcentagem_on"]
            
            html += f"""
                            <tr class="{filtro_class}">
                                <td>{produto["nome"]}</td>
                                <td>{produto["preco_atual"]}</td>
                                <td><span class="status {status_class}">{status_display}</span></td>
                                <td>
                                    <div class="availability-bar" title="{porcentagem_on}% disponível">
                                        <div class="availability-fill" style="width: {porcentagem_on}%"></div>
                                    </div>
                                </td>
                                <td class="timestamp">{produto["ultima_verificacao"]}</td>
                            </tr>
                            <tr class="history-row {filtro_class}" style="display: none;">
                                <td colspan="5">
                                    <div class="history-container">
                                        <div class="history-title">
                                            <span>Histórico e Estatísticas</span>
                                            <button class="history-toggle" onclick="toggleHistory(this)">Mostrar Histórico</button>
                                        </div>
                                        
                                        <div class="stats-container">
                                            <div class="stat-item">
                                                <div class="stat-item-label">Mudanças</div>
                                                <div class="stat-item-value">{produto["estatisticas"]["total_mudancas"]}</div>
                                            </div>
                                            <div class="stat-item">
                                                <div class="stat-item-label">Disponível</div>
                                                <div class="stat-item-value">{produto["estatisticas"]["porcentagem_on"]} %</div>
                                            </div>
                                            <div class="stat-item">
                                                <div class="stat-item-label">Tempo Médio ON</div>
                                                <div class="stat-item-value">{produto["estatisticas"]["tempo_medio_on"]}</div>
                                            </div>
                                            <div class="stat-item">
                                                <div class="stat-item-label">Tempo Médio OFF</div>
                                                <div class="stat-item-value">{produto["estatisticas"]["tempo_medio_off"]}</div>
                                            </div>
                                        </div>
                                        
                                        <div class="history-list">
            """
            
            # Adicionar itens do histórico
            if produto["historico"]:
                for item in reversed(produto["historico"]):
                    if "Desapareceu" in item["status"]:
                        status_class_hist = "desapareceu"
                        status_hist_display = "OFF (Desapareceu)"
                    elif item["status"] == "ON":
                        status_class_hist = "on"
                        status_hist_display = "ON"
                    else:
                        status_class_hist = "off"
                        status_hist_display = "OFF"
                    
                    html += f"""
                                            <div class="history-item">
                                                <div class="history-status {status_class_hist}">{status_hist_display}</div>
                                                <div class="history-price">{item["preco"]}</div>
                                                <div class="history-date">{item["timestamp"]}</div>
                                            </div>
                    """
            else:
                html += """
                                            <div class="history-item">
                                                <div>Nenhum histórico disponível</div>
                                            </div>
                """
            
            html += """
                                        </div>
                                    </div>
                                </td>
                            </tr>
            """
        
        html += """
                        </tbody>
                    </table>
                </div>
            </div>
        """
    
    # Finalizar HTML
    html += """
            <div class="footer">
                <p>Sistema de Monitoramento de Produtos iFood</p>
                <p>Atualizado automaticamente via GitHub Actions</p>
            </div>
        </div>
        
        <script>
            // Accordion functionality
            document.addEventListener("DOMContentLoaded", function() {
                var acc = document.getElementsByClassName("accordion");
                for (var i = 0; i < acc.length; i++) {
                    acc[i].addEventListener("click", function() {
                        this.classList.toggle("active");
                        var panel = this.nextElementSibling;
                        if (panel.style.maxHeight) {
                            panel.style.maxHeight = null;
                        } else {
                            panel.style.maxHeight = panel.scrollHeight + "px";
                        }
                    });
                }
                
                // Open first section by default if needed
                // if (acc.length > 0) {
                //     acc[0].click();
                // }
                
                // Search functionality
                document.getElementById("searchInput").addEventListener("keyup", function() {
                    var searchTerm = this.value.toLowerCase();
                    var rows = document.getElementsByClassName("produto-row");
                    var historyRows = document.getElementsByClassName("history-row");
                    
                    for (var i = 0; i < rows.length; i++) {
                        var productName = rows[i].getElementsByTagName("td")[0].textContent.toLowerCase();
                        var isVisible = productName.includes(searchTerm);
                        
                        rows[i].style.display = isVisible ? "" : "none";
                        if (historyRows[i]) {
                            historyRows[i].style.display = isVisible && historyRows[i].getAttribute("data-visible") === "true" ? "" : "none";
                        }
                        
                        // Make sure the section is open if a match is found
                        if (isVisible) {
                            var panel = rows[i].closest(".panel");
                            if (panel && !panel.style.maxHeight) {
                                panel.previousElementSibling.click();
                            }
                        }
                    }
                });
                
                // Filter buttons
                var filterButtons = document.querySelectorAll(".filter-btn");
                filterButtons.forEach(function(button) {
                    button.addEventListener("click", function() {
                        filterButtons.forEach(function(btn) { btn.classList.remove("active"); });
                        this.classList.add("active");
                        
                        var filter = this.getAttribute("data-filter");
                        var rows = document.getElementsByClassName("produto-row");
                        var historyRows = document.getElementsByClassName("history-row");
                        
                        for (var i = 0; i < rows.length; i++) {
                            var isVisible = (filter === "all" || rows[i].classList.contains("filter-" + filter));
                            rows[i].style.display = isVisible ? "" : "none";
                            if (historyRows[i]) {
                                historyRows[i].style.display = isVisible && historyRows[i].getAttribute("data-visible") === "true" ? "" : "none";
                            }
                        }
                        
                        // Make sure sections with visible items are open
                        var panels = document.querySelectorAll(".panel");
                        panels.forEach(function(panel) {
                            var visibleRows = panel.querySelectorAll("tr.produto-row:not([style*='display: none'])");
                            if (visibleRows.length > 0 && !panel.style.maxHeight) {
                                panel.previousElementSibling.click();
                            }
                        });
                    });
                });
                
                // Add click event to product rows to show/hide history
                var productRows = document.querySelectorAll(".produto-row");
                productRows.forEach(function(row, index) {
                    row.addEventListener("click", function(e) {
                        // Prevent toggling if clicking on interactive elements within the row if any
                        if (e.target.tagName === "A" || e.target.tagName === "BUTTON") return;
                        
                        var historyRow = document.querySelectorAll(".history-row")[index];
                        var isVisible = historyRow.style.display === "table-row";
                        
                        historyRow.style.display = isVisible ? "none" : "table-row";
                        historyRow.setAttribute("data-visible", !isVisible);
                        
                        // Update panel height
                        var panel = row.closest(".panel");
                        if (panel && panel.style.maxHeight) {
                            panel.style.maxHeight = panel.scrollHeight + "px";
                        }
                    });
                });
            });
            
            // Toggle history visibility
            function toggleHistory(button) {
                var historyList = button.closest(".history-container").querySelector(".history-list");
                historyList.classList.toggle("show");
                
                button.textContent = historyList.classList.contains("show") ? "Ocultar Histórico" : "Mostrar Histórico";
                
                // Update panel height
                var panel = button.closest(".panel");
                if (panel && panel.style.maxHeight) {
                    panel.style.maxHeight = panel.scrollHeight + "px";
                }
            }
        </script>
    </body>
    </html>
    """
    
    # Salvar HTML
    with open(arquivo_dashboard, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"✅ Dashboard HTML responsivo gerado em: {arquivo_dashboard}")
    
    # Fazer upload do arquivo para o GitHub
    fazer_upload_github(arquivo_dashboard, arquivo_dashboard)
    
    return arquivo_dashboard

def baixar_arquivo_github(nome_arquivo):
    """Baixa um arquivo do repositório GitHub"""
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        print(f"⚠️ Configurações do GitHub incompletas. Não foi possível baixar {nome_arquivo}.")
        return False
    
    try:
        # Obter o conteúdo do arquivo do GitHub
        url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/contents/{nome_arquivo}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            # Arquivo existe, baixar
            conteudo_base64 = response.json()["content"]
            conteudo = base64.b64decode(conteudo_base64).decode("utf-8")
            
            # Salvar localmente
            with open(nome_arquivo, "w", encoding="utf-8") as f:
                f.write(conteudo)
            
            print(f"✅ Arquivo {nome_arquivo} baixado com sucesso do GitHub")
            return True
        else:
            print(f"⚠️ Arquivo {nome_arquivo} não encontrado no GitHub ou erro ao baixar: {response.status_code}")
            return False
    
    except Exception as e:
        print(f"❌ Erro ao baixar arquivo do GitHub: {str(e)}")
        return False

def fazer_upload_github(arquivo_local, nome_arquivo_github):
    """Faz upload de um arquivo para o GitHub"""
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        print(f"⚠️ Configurações do GitHub incompletas. Não foi possível fazer upload de {arquivo_local}.")
        return False
    
    try:
        # Ler o conteúdo do arquivo
        with open(arquivo_local, "r", encoding="utf-8") as f:
            conteudo = f.read()
        
        # Codificar o conteúdo em base64
        conteudo_base64 = base64.b64encode(conteudo.encode("utf-8")).decode("utf-8")
        
        # Verificar se o arquivo já existe
        url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/contents/{nome_arquivo_github}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            # Arquivo existe, atualizar
            sha = response.json()["sha"]
            
            payload = {
                "message": f"Atualizar {nome_arquivo_github} - {horario_brasil().strftime("%Y-%m-%d %H:%M:%S")}",
                "content": conteudo_base64,
                "sha": sha
            }
        else:
            # Arquivo não existe, criar
            payload = {
                "message": f"Adicionar {nome_arquivo_github} - {horario_brasil().strftime("%Y-%m-%d %H:%M:%S")}",
                "content": conteudo_base64
            }
        
        # Fazer upload do arquivo
        response = requests.put(url, headers=headers, json=payload)
        
        if response.status_code in [200, 201]:
            print(f"✅ Arquivo {nome_arquivo_github} enviado com sucesso para o GitHub")
            
            # Retornar URL do arquivo
            if nome_arquivo_github == "index.html":
                url_dashboard = f"https://{GITHUB_ACTOR}.github.io/{GITHUB_REPOSITORY.split("/")[1]}"
                print(f"📊 Dashboard disponível em: {url_dashboard}")
                return url_dashboard
            
            return True
        else:
            print(f"❌ Erro ao enviar arquivo para o GitHub: {response.text}")
            return False
    
    except Exception as e:
        print(f"❌ Erro ao fazer upload para o GitHub: {str(e)}")
        return False

def enviar_alerta_telegram(mensagem, produtos_off=None, produtos_desaparecidos=None, total_produtos_ativos=0, todos_produtos=None):
    """Envia alerta para um grupo no Telegram com números coloridos"""
    try:
        # URL do dashboard
        url_dashboard = f"https://{GITHUB_ACTOR}.github.io/{GITHUB_REPOSITORY.split("/")[1]}" if GITHUB_ACTOR and GITHUB_REPOSITORY else None
        
        # Criar mensagem formatada
        texto = f"<b>🚨 ALERTA: Monitoramento de Produtos iFood 🚨</b>\n\n"
        texto += f"Data/Hora: {horario_brasil().strftime("%d/%m/%Y %H:%M:%S")}\n\n"
        
        # Adicionar contagem de produtos ativos
        texto += f"✅ Produtos ativos no site: <b>{total_produtos_ativos}</b>\n\n"
        
        # Produtos desaparecidos (são considerados OFF)
        if produtos_desaparecidos:
            texto += f"⚠️ <b><font color=\"#E65100\">{len(produtos_desaparecidos)}</font></b> produtos DESAPARECERAM (OFF):\n"
            for p in produtos_desaparecidos[:10]:
                texto += f"- {p["Seção"]} - {p["Produto"]} - Preço: {p["Preço"]}\n"
            if len(produtos_desaparecidos) > 10:
                texto += f"... e mais {len(produtos_desaparecidos) - 10} produtos\n"
            texto += "\n"
            
        # Produtos marcados como OFF no site
        if produtos_off:
            texto += f"⚠️ <b><font color=\"#F44336\">{len(produtos_off)}</font></b> produtos marcados como OFF no site:\n"
            for p in produtos_off[:5]:
                texto += f"- {p["Seção"]} - {p["Produto"]} - Preço: {p["Preço"]}\n"
            if len(produtos_off) > 5:
                texto += f"... e mais {len(produtos_off) - 5} produtos\n"
            texto += "\n"
        
        # Adicionar tabela resumida de status por seção com números coloridos
        if todos_produtos:
            # Agrupar produtos por seção
            produtos_por_secao = {}
            for produto in todos_produtos:
                secao = produto["Seção"]
                if secao not in produtos_por_secao:
                    produtos_por_secao[secao] = {"total": 0, "off": 0, "desaparecidos": 0}
                
                produtos_por_secao[secao]["total"] += 1
                
                # Contar produtos OFF e desaparecidos separadamente
                if "Status" in produto and "Desapareceu" in produto.get("Status", ""):
                    produtos_por_secao[secao]["desaparecidos"] += 1
                    produtos_por_secao[secao]["off"] += 1  # Desaparecidos também são OFF
                elif "Status" in produto and produto["Status"] != "ON":
                    produtos_por_secao[secao]["off"] += 1
            
            texto += "<b>📊 Status por Seção:</b>\n"
            for secao, contagem in sorted(produtos_por_secao.items()):
                on_count = contagem["total"] - contagem["off"]
                off_count = contagem["off"]
                desaparecidos = contagem["desaparecidos"]
                
                # Usar números coloridos
                on_texto = f"<b><font color=\"#4CAF50\">{on_count}</font></b> ON"
                off_texto = f"<b><font color=\"#F44336\">{off_count}</font></b> OFF"
                
                status_texto = f"{on_texto} | {off_texto}"
                if desaparecidos > 0:
                    status_texto += f" (inclui <b><font color=\"#E65100\">{desaparecidos}</font></b> desaparecidos)"
                
                texto += f"- {secao}: {status_texto}\n"
            
            texto += "\n"
        
        texto += f"{mensagem}\n\n"
        
        # Adicionar link para o dashboard
        if url_dashboard:
            texto += f"🔗 <a href=\"{url_dashboard}\">Dashboard completo disponível aqui</a>"
        else:
            texto += "🔗 Dashboard completo disponível em HTML."
        
        # Enviar mensagem
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": texto,
            "parse_mode": "HTML"  # Importante para renderizar as cores
        }
        
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            print(f"✅ Alerta enviado com sucesso para o Telegram")
            return True
        else:
            print(f"❌ Erro ao enviar alerta para o Telegram: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Erro ao enviar alerta para o Telegram: {str(e)}")
        return False

def salvar_log(mensagem):
    """Salva mensagem de log em arquivo"""
    arquivo_log = "monitoramento_log.txt"
    
    # Tentar baixar o arquivo de log existente
    baixar_arquivo_github(arquivo_log)
    
    timestamp = horario_brasil().strftime("%Y-%m-%d %H:%M:%S")
    
    # Abrir em modo append para adicionar nova linha
    with open(arquivo_log, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {mensagem}\n")
    
    # Fazer upload do arquivo atualizado
    fazer_upload_github(arquivo_log, arquivo_log)

def verificar_status_produto(product):
    """Verifica se o produto está ON (disponível) ou OFF (indisponível)"""
    try:
        # Verificar se o produto está marcado como indisponível
        # Isso pode variar dependendo de como o iFood marca produtos indisponíveis
        
        # Verificar se há classe de indisponibilidade
        try:
            indisponivel = product.find_element(By.CLASS_NAME, "dish-card--unavailable")
            return "OFF"
        except NoSuchElementException:
            pass
            
        # Verificar texto de indisponibilidade
        try:
            texto_indisponivel = product.find_element(By.CSS_SELECTOR, ".dish-card__unavailable-label")
            if texto_indisponivel:
                return "OFF"
        except NoSuchElementException:
            pass
            
        # Verificar se o botão de adicionar está desabilitado
        try:
            botao_adicionar = product.find_element(By.CSS_SELECTOR, "button[disabled]")
            if botao_adicionar:
                return "OFF"
        except NoSuchElementException:
            pass
            
        # Se nenhuma das verificações acima encontrou indisponibilidade, consideramos o produto como disponível
        return "ON"
        
    except Exception as e:
        print(f"Erro ao verificar status do produto: {str(e)}")
        return "Erro"

def monitorar_produtos():
    """Função principal para monitorar produtos"""
    timestamp = horario_brasil().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n🔍 Iniciando monitoramento de produtos em {timestamp}")
    salvar_log(f"Iniciando monitoramento de produtos")
    
    # Carregar estado anterior para comparação
    estado_anterior = carregar_estado_anterior()
    
    # Configuração do Selenium para GitHub Actions
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36") # User agent
    
    # No GitHub Actions, não precisamos especificar o caminho do chromedriver
    driver = webdriver.Chrome(options=options)
    
    dados_produtos = []
    contagem_por_secao = {}
    produtos_off = []
    
    try:
        url = "https://www.ifood.com.br/delivery/rio-de-janeiro-rj/cumbuca-catete/e2c3f587-3c83-4ea7-8418-a4b693caaaa4"
        driver.get(url)
        
        wait = WebDriverWait(driver, 30) # Aumentar tempo de espera
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "restaurant-menu-group__title")))
        
        # Scroll down to load all products if necessary
        last_height = driver.execute_script("return document.body.scrollHeight")
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2) # Wait for page to load
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            print("Scrolling down...")
            
        sections = driver.find_elements(By.CLASS_NAME, "restaurant-menu-group")
        
        print("🛒 Produtos por Seção:\n")
        
        total_produtos = 0
        total_produtos_off_site = 0 # Apenas os marcados como OFF no site
        
        for section in sections:
            try:
                title_element = section.find_element(By.CLASS_NAME, "restaurant-menu-group__title")
                section_title = title_element.text.strip()
            except NoSuchElementException:
                print("⚠️ Seção sem título encontrada, pulando...")
                continue
            
            products = section.find_elements(By.CLASS_NAME, "dish-card")
            quantidade_seção = len(products)
            contagem_por_secao[section_title] = quantidade_seção
            total_produtos += quantidade_seção
            
            print(f"🔹 {section_title} ({quantidade_seção} item{"s" if quantidade_seção != 1 else ""}):\n")
            
            if not products:
                print("  ⚠️ Nenhum produto encontrado nessa seção.\n")
                continue
            
            produtos_off_secao = 0
            
            for idx, product in enumerate(products, start=1):
                try:
                    name = product.find_element(By.CLASS_NAME, "dish-card__description").text.strip()
                except NoSuchElementException:
                    name = "Nome não encontrado"
                
                try:
                    description = product.find_element(By.CLASS_NAME, "dish-card__details").text.strip()
                except NoSuchElementException:
                    description = "Descrição não encontrada"
                
                price_display = extrair_preco(product)
                
                # Verificar status do produto (ON/OFF)
                status = verificar_status_produto(product)
                
                status_icon = "✅" if status == "ON" else "❌"
                print(f"{idx:02d}. {name} - {price_display} - Status: {status_icon} {status}")
                
                produto_info = {
                    "Seção": section_title,
                    "Produto": name,
                    "Preço": price_display,
                    "Descrição": description,
                    "Status": status
                }
                
                dados_produtos.append(produto_info)
                
                if status == "OFF":
                    produtos_off.append(produto_info)
                    produtos_off_secao += 1
                    total_produtos_off_site += 1
            
            print(f"  ℹ️ Produtos marcados como OFF nesta seção: {produtos_off_secao}\n")
        
        print(f"✅ Total de produtos encontrados no site: {total_produtos}")
        print(f"❌ Total de produtos marcados como OFF no site: {total_produtos_off_site}")
        
        # Comparar com estado anterior para encontrar produtos que desapareceram
        produtos_atuais = {}
        for produto in dados_produtos:
            chave = f"{produto["Seção"]}|{produto["Produto"]}"
            produtos_atuais[chave] = produto
        
        # Encontrar produtos que existiam antes mas não existem mais (desapareceram)
        produtos_desaparecidos = []
        for chave, info in estado_anterior.items():
            if chave not in produtos_atuais:
                secao, nome = chave.split("|", 1)
                produtos_desaparecidos.append({
                    "Seção": secao,
                    "Produto": nome,
                    "Preço": info.get("Preço", "N/A"),
                    "Status": "OFF (Desapareceu)",
                    "Última verificação": info.get("Última verificação", "Desconhecido"),
                    "Descrição": info.get("Descrição", "")
                })
        
        # Adicionar produtos desaparecidos à lista de produtos com problemas
        if produtos_desaparecidos:
            print(f"\n⚠️ ALERTA: {len(produtos_desaparecidos)} produtos desapareceram desde a última verificação!")
            salvar_log(f"ALERTA: {len(produtos_desaparecidos)} produtos desapareceram")
            
            for p in produtos_desaparecidos:
                print(f"  ❌ {p["Seção"]} - {p["Produto"]} - Última verificação: {p["Última verificação"]}")
        else:
            print("\n✅ Nenhum produto desapareceu desde a última verificação.")
        
        # Salvar estado atual para próxima comparação
        salvar_estado_produtos(dados_produtos)
        
        # Atualizar histórico de status e gerar dashboard
        # Adicionar produtos desaparecidos ao histórico
        historico = atualizar_historico_status(dados_produtos, produtos_desaparecidos)
        arquivo_dashboard = gerar_dashboard_html(historico)
        
        # Salvar dados em Excel
        arquivo_excel = "produtos_cumbuca.xlsx"
        
        # Criar DataFrame com todos os produtos (incluindo desaparecidos)
        todos_produtos_para_relatorio = []
        for info in historico.values():
            todos_produtos_para_relatorio.append({
                "Seção": info["secao"],
                "Produto": info["nome"],
                "Preço": info["preco_atual"],
                "Descrição": info.get("Descrição", ""), # Tentar obter descrição do histórico se existir
                "Status": info["status_atual"],
                "Última verificação": info["ultima_verificacao"]
            })
            
        df = pd.DataFrame(todos_produtos_para_relatorio)
        
        # Garantir que todas as colunas necessárias existam
        for coluna in ["Seção", "Produto", "Preço", "Descrição", "Status", "Última verificação"]:
            if coluna not in df.columns:
                df[coluna] = ""
        
        # Organizar colunas
        colunas = ["Seção", "Produto", "Preço", "Descrição", "Status", "Última verificação"]
        df = df[colunas]
        
        # Calcular totais para o Excel
        total_produtos_relatorio = len(historico)
        total_produtos_off_relatorio = sum(1 for info in historico.values() if info["status_atual"] != "ON")
        total_desaparecidos_relatorio = sum(1 for info in historico.values() if "Desapareceu" in info["status_atual"])
        
        df_contagem = pd.DataFrame(list(contagem_por_secao.items()), columns=["Seção", "Quantidade de Itens no Site"])
        
        linha_em_branco = pd.DataFrame([{col: "" for col in df.columns}])
        linha_total = pd.DataFrame([{
            "Seção": "TOTAL DE PRODUTOS", 
            "Produto": total_produtos_relatorio, 
            "Status": f"OFF: {total_produtos_off_relatorio} ({total_desaparecidos_relatorio} desaparecidos)"
        }])
        
        with pd.ExcelWriter(arquivo_excel, engine="openpyxl", mode="w") as writer:
            df.to_excel(writer, sheet_name="Produtos", index=False)
            linha_em_branco.to_excel(writer, sheet_name="Produtos", index=False, header=False, startrow=len(df)+1)
            df_contagem.to_excel(writer, sheet_name="Produtos", index=False, startrow=len(df)+2)
            linha_total.to_excel(writer, sheet_name="Produtos", index=False, header=False, startrow=len(df)+2+len(df_contagem)+1)
        
        # Formatar Excel
        wb = load_workbook(arquivo_excel)
        ws = wb["Produtos"]
        
        bold_font = Font(bold=True)
        center_align = Alignment(horizontal="center", vertical="center")
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin")
        )
        
        # Definir preenchimentos para status
        fill_off = PatternFill(start_color="FFCCCC", end_color="FFCCCC", fill_type="solid")  # Vermelho claro
        fill_on = PatternFill(start_color="CCFFCC", end_color="CCFFCC", fill_type="solid")   # Verde claro
        fill_desaparecido = PatternFill(start_color="FFEECC", end_color="FFEECC", fill_type="solid")  # Laranja claro
        
        # Formatar cabeçalhos
        for cell in ws[1]:
            cell.font = bold_font
            cell.alignment = center_align
            cell.border = thin_border
        
        # Formatar células e destacar status
        max_row = ws.max_row
        max_col = ws.max_column
        for row in ws.iter_rows(min_row=2, max_row=len(df)+1, min_col=1, max_col=max_col):
            for cell in row:
                cell.border = thin_border
                
                # Destacar status
                status_col = 5  # Coluna de Status (E)
                if cell.column == status_col:
                    if cell.value == "OFF":
                        cell.fill = fill_off
                    elif cell.value == "ON":
                        cell.fill = fill_on
                    elif cell.value and "Desapareceu" in str(cell.value):
                        cell.fill = fill_desaparecido
                        # Destacar toda a linha para produtos desaparecidos
                        for c in row:
                            c.fill = fill_desaparecido
        
        # Ajustar largura das colunas
        for col in ws.columns:
            max_length = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.value:
                    valor = str(cell.value)
                    if len(valor) > max_length:
                        max_length = len(valor)
            adjusted_width = max_length + 2
            ws.column_dimensions[col_letter].width = adjusted_width
        
        wb.save(arquivo_excel)
        
        # Fazer upload do Excel para o GitHub
        fazer_upload_github(arquivo_excel, arquivo_excel)
        
        print(f"\n✅ Dados formatados e salvos com sucesso em: {arquivo_excel}")
        salvar_log(f"Monitoramento concluído. Total: {total_produtos_relatorio}, OFF: {total_produtos_off_relatorio}, Desaparecidos: {total_desaparecidos_relatorio}")
        
        # Calcular produtos ativos
        total_produtos_ativos = total_produtos_relatorio - total_produtos_off_relatorio
        
        # Enviar alerta se houver produtos OFF ou desaparecidos
        produtos_off_reais = [p for p in historico.values() if p["status_atual"] == "OFF"]
        produtos_desaparecidos_reais = [p for p in historico.values() if "Desapareceu" in p["status_atual"]]
        
        if produtos_off_reais or produtos_desaparecidos_reais:
            total_problemas = len(produtos_off_reais) + len(produtos_desaparecidos_reais)
            print(f"\n⚠️ ALERTA: {total_problemas} produtos com problemas!")
            salvar_log(f"ALERTA: {total_problemas} produtos com problemas")
            
            # Mensagem para alertas
            mensagem = f"Total de {total_problemas} produtos com problemas. Verifique o relatório completo."
            
            # Enviar alerta para o Telegram
            enviar_alerta_telegram(
                mensagem, 
                produtos_off_reais, 
                produtos_desaparecidos_reais, 
                total_produtos_ativos,
                todos_produtos_para_relatorio # Passar a lista completa para o resumo
            )
            
        else:
            print("\n✅ Todos os produtos estão ON e nenhum desapareceu!")
            salvar_log("Todos os produtos estão ON e nenhum desapareceu")
            
            # Enviar mensagem de status normal para o Telegram
            mensagem = "✅ Todos os produtos estão ON e nenhum desapareceu!"
            enviar_alerta_telegram(
                mensagem,
                None,
                None,
                total_produtos_relatorio,
                todos_produtos_para_relatorio # Passar a lista completa para o resumo
            )
        
        return {
            "total_produtos": total_produtos_relatorio,
            "produtos_off": produtos_off_reais,
            "produtos_desaparecidos": produtos_desaparecidos_reais,
            "total_produtos_ativos": total_produtos_ativos,
            "timestamp": timestamp
        }
        
    except TimeoutException:
        erro_msg = "❌ Tempo esgotado esperando a página carregar os produtos."
        print(erro_msg)
        salvar_log(erro_msg)
    except Exception as e:
        erro_msg = f"❌ Erro inesperado: {str(e)}"
        print(erro_msg)
        salvar_log(erro_msg)
    finally:
        driver.quit()

if __name__ == "__main__":
    # Executar monitoramento
    resultado = monitorar_produtos()
    
    # Imprimir resumo
    if resultado:
        print("\n📋 Resumo do monitoramento:")
        print(f"- Total de produtos: {resultado["total_produtos"]}")
        print(f"- Produtos OFF: {len(resultado["produtos_off"]) + len(resultado["produtos_desaparecidos"])}")
        print(f"- Produtos desaparecidos: {len(resultado["produtos_desaparecidos"])}")
        print(f"- Produtos ativos: {resultado["total_produtos_ativos"]}")
        print(f"- Timestamp: {resultado["timestamp"]}")
