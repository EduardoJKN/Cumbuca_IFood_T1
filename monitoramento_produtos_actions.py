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

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Configurações do Telegram
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "7538392371:AAH3-eZcq7wrf3Uycv9zPq1PjlSvWfLtYlc")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1002593932783")

# Configurações do GitHub
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")
GITHUB_ACTOR = os.environ.get("GITHUB_ACTOR", "")

def horario_brasil():
    return datetime.datetime.now() - datetime.timedelta(hours=3)

def limpar_preco(texto):
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
    arquivo_estado = "estado_produtos.json"
    estado = {}
    for produto in dados_produtos:
        chave = f"{produto['Seção']}|{produto['Produto']}"
        estado[chave] = {
            "Preço": produto["Preço"],
            "Descrição": produto.get("Descrição", ""),
            "Status": produto.get("Status", "ON"),
            "Última verificação": horario_brasil().strftime("%Y-%m-%d %H:%M:%S")
        }

    with open(arquivo_estado, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)

    print(f"✅ Estado salvo com {len(estado)} produtos")
    fazer_upload_github(arquivo_estado, arquivo_estado)
    return estado

def carregar_estado_anterior():
    arquivo_estado = "estado_produtos.json"
    baixar_arquivo_github(arquivo_estado)

    if not os.path.exists(arquivo_estado):
        print("⚠️ Nenhum estado anterior encontrado")
        return {}

    try:
        with open(arquivo_estado, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Erro ao carregar estado: {str(e)}")
        return {}

def enviar_alerta_telegram(mensagem, produtos_off=None, produtos_desaparecidos=None, total_produtos_ativos=0, todos_produtos=None, google_sheet_link=None):
    try:
        url_dashboard = f"https://{GITHUB_ACTOR}.github.io/{GITHUB_REPOSITORY.split('/')[1]}" if GITHUB_ACTOR and GITHUB_REPOSITORY else None
        texto = f"🍔 Monitoramento iFood - Atualização 🕒\n\n"
        texto += f"⏰ {horario_brasil().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
        texto += f"✅ PRODUTOS ATIVOS: {total_produtos_ativos}\n"

        if produtos_off or produtos_desaparecidos:
            total_problemas = (len(produtos_off) if produtos_off else 0) + (len(produtos_desaparecidos) if produtos_desaparecidos else 0)
            texto += f"⚠️ PROBLEMAS: {total_problemas}\n\n"

        if produtos_desaparecidos:
            texto += f"🔴 {len(produtos_desaparecidos)} REMOVIDOS:\n"
            for p in produtos_desaparecidos[:5]:
                texto += f"- {p['Seção']} - {p['Produto']}\n"
            if len(produtos_desaparecidos) > 5:
                texto += f"... +{len(produtos_desaparecidos)-5} itens\n"
            texto += "\n"

        if produtos_off:
            texto += f"⚫ {len(produtos_off)} INDISPONÍVEIS:\n"
            for p in produtos_off[:3]:
                texto += f"- {p['Seção']} - {p['Produto']}\n"
            if len(produtos_off) > 3:
                texto += f"... +{len(produtos_off)-3} itens\n"
            texto += "\n"

        if todos_produtos:
            secao_stats = {}
            for p in todos_produtos:
                secao = p["Seção"]
                if secao not in secao_stats:
                    secao_stats[secao] = {"total": 0, "off": 0}
                secao_stats[secao]["total"] += 1
                if p.get("Status") != "ON":
                    secao_stats[secao]["off"] += 1

            texto += "📊 STATUS POR SEÇÃO:\n"
            for secao, stats in sorted(secao_stats.items()):
                on = stats["total"] - stats["off"]
                texto += f"- {secao}: {'🟢'*on}{'🔴'*stats['off']} ({on} ON | {stats['off']} OFF)\n"

        texto += "\n🔗 LINKS:\n"
        if url_dashboard:
            texto += f"- Dashboard: {url_dashboard}\n"
        if google_sheet_link:
            texto += f"- Planilha: {google_sheet_link}\n"

        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": texto,
                "parse_mode": "HTML"
            }
        )

        if response.status_code == 200:
            print("✅ Mensagem enviada ao Telegram")
            return True
        print(f"❌ Erro no Telegram: {response.text}")
        return False
    except Exception as e:
        print(f"❌ Falha no Telegram: {str(e)}")
        return False

# (Funções: baixar_arquivo_github, fazer_upload_github, exportar_para_google_sheets devem estar presentes também)

def monitorar_produtos():
    print(f"\n🔍 Iniciando monitoramento em {horario_brasil().strftime('%Y-%m-%d %H:%M:%S')}")
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)
    dados_produtos = []
    produtos_off = []

    try:
        driver.get("https://www.ifood.com.br/delivery/rio-de-janeiro-rj/cumbuca-catete/e2c3f587-3c83-4ea7-8418-a4b693caaaa4")
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CLASS_NAME, "restaurant-menu-group__title")))

        for section in driver.find_elements(By.CLASS_NAME, "restaurant-menu-group"):
            secao = section.find_element(By.CLASS_NAME, "restaurant-menu-group__title").text.strip()
            for product in section.find_elements(By.CLASS_NAME, "dish-card"):
                nome = product.find_element(By.CLASS_NAME, "dish-card__description").text.strip()
                preco = extrair_preco(product)
                status = verificar_status_produto(product)

                produto = {
                    "Seção": secao,
                    "Produto": nome,
                    "Preço": preco,
                    "Status": status
                }

                dados_produtos.append(produto)
                if status != "ON":
                    produtos_off.append(produto)

        estado_anterior = carregar_estado_anterior()
        produtos_desaparecidos = []

        for chave, info in estado_anterior.items():
            if chave not in [f"{p['Seção']}|{p['Produto']}" for p in dados_produtos]:
                secao, nome = chave.split("|", 1)
                produtos_desaparecidos.append({
                    "Seção": secao,
                    "Produto": nome,
                    "Status": "OFF (Desapareceu)",
                    "Preço": info.get("Preço", "N/A")
                })

        salvar_estado_produtos(dados_produtos)
        total_ativos = len([p for p in dados_produtos if p["Status"] == "ON"])

        enviar_alerta_telegram(
            mensagem="Atualização concluída!",
            produtos_off=produtos_off,
            produtos_desaparecidos=produtos_desaparecidos,
            total_produtos_ativos=total_ativos,
            todos_produtos=dados_produtos,
            google_sheet_link=exportar_para_google_sheets("produtos_cumbuca.xlsx")
        )

        return {
            "total_produtos": len(dados_produtos),
            "produtos_off": produtos_off,
            "produtos_desaparecidos": produtos_desaparecidos,
            "total_produtos_ativos": total_ativos
        }

    except Exception as e:
        erro = f"Erro: {str(e)}"
        print(f"❌ {erro}")
        salvar_log(erro)
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": f"🚨 Erro durante execução do monitoramento:\n\n<code>{erro}</code>",
                "parse_mode": "HTML"
            }
        )
        return None
    finally:
        driver.quit()

# FUNÇÕES FINAIS ADICIONADAS

def verificar_status_produto(produto_element):
    """Verifica se o produto está disponível (ON) ou não (OFF)"""
    try:
        indisponivel = produto_element.find_element(By.CLASS_NAME, "dish-card__unavailable")
        if indisponivel:
            return "OFF"
    except NoSuchElementException:
        pass
    return "ON"

def salvar_log(mensagem, nome_arquivo="monitoramento_log.txt"):
    """Salva uma mensagem no log local"""
    timestamp = horario_brasil().strftime("%Y-%m-%d %H:%M:%S")
    with open(nome_arquivo, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {mensagem}\n")
    print(f"📝 Log salvo: {mensagem}")

if __name__ == "__main__":
    resultado = monitorar_produtos()
    if resultado:
        print(f"\n📋 Resumo Final:")
        print(f"- Total de produtos: {resultado['total_produtos']}")
        print(f"- Produtos ativos: {resultado['total_produtos_ativos']}")
        print(f"- Produtos com problemas: {len(resultado['produtos_off']) + len(resultado['produtos_desaparecidos'])}")
