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
from openpyxl.chart import BarChart, Reference

# Configurações do Telegram
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

# Configurações do GitHub
GITHUB_TOKEN = os.environ['GITHUB_TOKEN']
GITHUB_REPOSITORY = os.environ['GITHUB_REPOSITORY']
GITHUB_ACTOR = os.environ['GITHUB_ACTOR']

# Função para obter o horário atual no fuso horário de Brasília (UTC-3)
def horario_brasil():
    """Retorna o horário atual no fuso horário de Brasília (UTC-3)"""
    return datetime.datetime.now() - datetime.timedelta(hours=3)

def limpar_preco(texto):
    """Limpa e formata o texto do preço, removendo repetições"""
    if not texto:
        return None
    
    if 'R$' in texto:
        partes = texto.split('R$')
        if len(partes) > 1:
            prefixo = partes[0].strip() + ' ' if partes[0].strip() else ''
            valor = 'R$' + partes[1].split()[0].strip()
            return prefixo + valor
    
    return texto.strip()

def extrair_preco(product):
    """Extrai e formata o preço do produto sem repetições"""
    try:
        try:
            price_discount = product.find_element(By.CLASS_NAME, 'dish-card__price--discount').text.strip()
            price_discount = limpar_preco(price_discount)
        except NoSuchElementException:
            price_discount = None

        try:
            price_original = product.find_element(By.CLASS_NAME, 'dish-card__price--original').text.strip()
            price_original = limpar_preco(price_original)
        except NoSuchElementException:
            price_original = None

        try:
            price_normal = product.find_element(By.CLASS_NAME, 'dish-card__price').text.strip()
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
    arquivo_estado = 'estado_produtos.json'
    
    estado = {}
    for produto in dados_produtos:
        chave = f"{produto['Seção']}|{produto['Produto']}"
        estado[chave] = {
            'Preço': produto['Preço'],
            'Descrição': produto.get('Descrição', ''),
            'Status': produto.get('Status', 'ON'),
            'Última verificação': horario_brasil().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    with open(arquivo_estado, 'w', encoding='utf-8') as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Estado atual salvo com {len(estado)} produtos")
    fazer_upload_github(arquivo_estado, arquivo_estado)
    return estado

def carregar_estado_anterior():
    """Carrega o estado anterior dos produtos para comparação"""
    arquivo_estado = 'estado_produtos.json'
    baixar_arquivo_github(arquivo_estado)
    
    if not os.path.exists(arquivo_estado):
        print("⚠️ Nenhum estado anterior encontrado. Esta parece ser a primeira execução.")
        return {}
    
    try:
        with open(arquivo_estado, 'r', encoding='utf-8') as f:
            estado = json.load(f)
            print(f"✅ Estado anterior carregado com {len(estado)} produtos")
            return estado
    except Exception as e:
        print(f"❌ Erro ao carregar estado anterior: {str(e)}")
        return {}

def carregar_historico_status():
    """Carrega o histórico de status dos produtos"""
    arquivo_historico = 'historico_status.json'
    baixar_arquivo_github(arquivo_historico)
    
    if not os.path.exists(arquivo_historico):
        print("⚠️ Nenhum histórico encontrado. Criando novo arquivo de histórico.")
        return {}
    
    try:
        with open(arquivo_historico, 'r', encoding='utf-8') as f:
            historico = json.load(f)
            print(f"✅ Histórico carregado com {len(historico)} produtos")
            return historico
    except Exception as e:
        print(f"❌ Erro ao carregar histórico: {str(e)}")
        return {}

def atualizar_historico_status(dados_produtos, produtos_desaparecidos):
    """Atualiza o histórico de status dos produtos"""
    arquivo_historico = 'historico_status.json'
    historico = carregar_historico_status()
    
    timestamp = horario_brasil().strftime('%Y-%m-%d %H:%M:%S')
    
    for produto in dados_produtos:
        chave = f"{produto['Seção']}|{produto['Produto']}"
        if chave not in historico:
            historico[chave] = {
                'nome': produto['Produto'],
                'secao': produto['Seção'],
                'status_atual': produto['Status'],
                'preco_atual': produto['Preço'],
                'ultima_verificacao': timestamp,
                'historico': []
            }
        else:
            if historico[chave]['status_atual'] != produto['Status']:
                historico[chave]['historico'].append({
                    'status': historico[chave]['status_atual'],
                    'preco': historico[chave]['preco_atual'],
                    'timestamp': historico[chave]['ultima_verificacao']
                })
            
            historico[chave]['status_atual'] = produto['Status']
            historico[chave]['preco_atual'] = produto['Preço']
            historico[chave]['ultima_verificacao'] = timestamp
    
    for produto in produtos_desaparecidos:
        chave = f"{produto['Seção']}|{produto['Produto']}"
        if chave not in historico:
            historico[chave] = {
                'nome': produto['Produto'],
                'secao': produto['Seção'],
                'status_atual': 'OFF (Desapareceu)',
                'preco_atual': produto['Preço'],
                'ultima_verificacao': timestamp,
                'historico': []
            }
        else:
            if historico[chave]['status_atual'] != 'OFF (Desapareceu)':
                historico[chave]['historico'].append({
                    'status': historico[chave]['status_atual'],
                    'preco': historico[chave]['preco_atual'],
                    'timestamp': historico[chave]['ultima_verificacao']
                })
            
            historico[chave]['status_atual'] = 'OFF (Desapareceu)'
            historico[chave]['ultima_verificacao'] = timestamp
    
    # Calcular estatísticas para cada produto
    for produto_info in historico.values():
        produto_info['estatisticas'] = calcular_estatisticas_produto(produto_info)
    
    with open(arquivo_historico, 'w', encoding='utf-8') as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Histórico atualizado com {len(historico)} produtos")
    fazer_upload_github(arquivo_historico, arquivo_historico)
    return historico

def calcular_estatisticas_produto(historico_produto):
    """Calcula estatísticas para um produto com base em seu histórico"""
    if not historico_produto['historico']:
        return {
            'total_mudancas': 0,
            'tempo_medio_on': 'N/A',
            'tempo_medio_off': 'N/A',
            'porcentagem_on': 100 if historico_produto['status_atual'] == 'ON' else 0,
            'ultima_mudanca': 'Nunca'
        }
    
    historico_completo = historico_produto['historico'] + [{
        'status': historico_produto['status_atual'],
        'timestamp': historico_produto['ultima_verificacao']
    }]
    
    historico_ordenado = sorted(historico_completo, key=lambda x: x['timestamp'])
    
    tempo_total_on = 0
    tempo_total_off = 0
    contagem_on = 0
    contagem_off = 0
    
    for i in range(len(historico_ordenado) - 1):
        status_atual = historico_ordenado[i]['status']
        timestamp_atual = datetime.datetime.strptime(historico_ordenado[i]['timestamp'], '%Y-%m-%d %H:%M:%S')
        timestamp_proximo = datetime.datetime.strptime(historico_ordenado[i+1]['timestamp'], '%Y-%m-%d %H:%M:%S')
        
        duracao = (timestamp_proximo - timestamp_atual).total_seconds() / 3600
        
        if status_atual == 'ON':
            tempo_total_on += duracao
            contagem_on += 1
        else:
            tempo_total_off += duracao
            contagem_off += 1
    
    tempo_medio_on = tempo_total_on / contagem_on if contagem_on > 0 else 0
    tempo_medio_off = tempo_total_off / contagem_off if contagem_off > 0 else 0
    
    tempo_total = tempo_total_on + tempo_total_off
    porcentagem_on = (tempo_total_on / tempo_total * 100) if tempo_total > 0 else (100 if historico_produto['status_atual'] == 'ON' else 0)
    
    if historico_produto['historico']:
        ultima_mudanca = historico_produto['historico'][-1]['timestamp']
    else:
        ultima_mudanca = 'Nunca'
    
    return {
        'total_mudancas': len(historico_produto['historico']),
        'tempo_medio_on': f"{tempo_medio_on:.2f} horas" if contagem_on > 0 else 'N/A',
        'tempo_medio_off': f"{tempo_medio_off:.2f} horas" if contagem_off > 0 else 'N/A',
        'porcentagem_on': round(porcentagem_on, 2),
        'ultima_mudanca': ultima_mudanca
    }

def gerar_relatorio_diario():
    """Gera um relatório Excel consolidado do dia"""
    try:
        data_atual = horario_brasil().strftime("%d-%m-%Y")
        nome_arquivo = f"relatorio_diario_{data_atual}.xlsx"
        historico = carregar_historico_status()
        
        # Preparar dados detalhados
        dados = []
        for chave, info in historico.items():
            secao, nome = chave.split("|", 1)
            dados.append({
                "Seção": secao,
                "Produto": nome,
                "Status Atual": info["status_atual"],
                "Preço Atual": info["preco_atual"],
                "Última Atualização": info["ultima_verificacao"],
                "Mudanças de Status": info.get("estatisticas", {}).get("total_mudancas", 0),
                "Disponibilidade (%)": info.get("estatisticas", {}).get("porcentagem_on", "N/A"),
                "Tempo Médio ON": info.get("estatisticas", {}).get("tempo_medio_on", "N/A"),
                "Tempo Médio OFF": info.get("estatisticas", {}).get("tempo_medio_off", "N/A"),
                "Última Mudança": info.get("estatisticas", {}).get("ultima_mudanca", "Nunca")
            })
        
        df_detalhes = pd.DataFrame(dados)
        
        # Preparar resumo por seção
        resumo_secao = df_detalhes.groupby("Seção")["Status Atual"].value_counts().unstack().fillna(0)
        resumo_secao["Total"] = resumo_secao.sum(axis=1)
        
        # Preparar resumo geral
        total_produtos = len(df_detalhes)
        total_on = len(df_detalhes[df_detalhes["Status Atual"] == "ON"])
        total_off = len(df_detalhes[df_detalhes["Status Atual"] != "ON"])
        total_desaparecidos = len(df_detalhes[df_detalhes["Status Atual"] == "OFF (Desapareceu)"])
        
        resumo_geral = pd.DataFrame({
            "Métrica": ["Total de Produtos", "Produtos ON", "Produtos OFF", "Produtos Desaparecidos"],
            "Valor": [total_produtos, total_on, total_off, total_desaparecidos]
        })
        
        # Salvar em Excel com formatação
        with pd.ExcelWriter(nome_arquivo, engine='openpyxl') as writer:
            # Detalhes
            df_detalhes.to_excel(writer, sheet_name='Detalhes', index=False)
            
            # Resumo por Seção
            resumo_secao.to_excel(writer, sheet_name='Resumo por Seção')
            
            # Resumo Geral
            resumo_geral.to_excel(writer, sheet_name='Resumo Geral', index=False)
            
            # Formatação
            workbook = writer.book
            formatar_planilha(workbook)
            
        return nome_arquivo
        
    except Exception as e:
        print(f"Erro ao gerar relatório diário: {str(e)}")
        return None

def formatar_planilha(workbook):
    """Aplica formatação às planilhas do Excel"""
    # Formatar planilha de Detalhes
    if 'Detalhes' in workbook.sheetnames:
        ws = workbook['Detalhes']
        
        # Formatar cabeçalhos
        header_fill = PatternFill(start_color="FFD700", end_color="FFD700", fill_type="solid")
        header_font = Font(bold=True, color="000000")
        header_border = Border(bottom=Side(style='medium'))
        
        for col in range(1, ws.max_column + 1):
            cell = ws.cell(row=1, column=col)
            cell.fill = header_fill
            cell.font = header_font
            cell.border = header_border
        
        # Autoajustar largura das colunas
        for column in ws.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
                
            adjusted_width = (max_length + 2) * 1.2
            ws.column_dimensions[column_letter].width = adjusted_width
        
        # Adicionar filtros
        ws.auto_filter.ref = ws.dimensions
    
    # Formatar planilha de Resumo por Seção
    if 'Resumo por Seção' in workbook.sheetnames:
        ws = workbook['Resumo por Seção']
        
        # Formatar cabeçalhos
        for col in range(1, ws.max_column + 1):
            cell = ws.cell(row=1, column=col)
            cell.fill = PatternFill(start_color="C0C0C0", end_color="C0C0C0", fill_type="solid")
            cell.font = Font(bold=True)
        
        # Adicionar bordas
        for row in ws.iter_rows():
            for cell in row:
                cell.border = Border(left=Side(style='thin'), right=Side(style='thin'),
                                    top=Side(style='thin'), bottom=Side(style='thin'))
    
    # Formatar planilha de Resumo Geral
    if 'Resumo Geral' in workbook.sheetnames:
        ws = workbook['Resumo Geral']
        
        # Formatar cabeçalhos
        for col in range(1, ws.max_column + 1):
            cell = ws.cell(row=1, column=col)
            cell.fill = PatternFill(start_color="A9D08E", end_color="A9D08E", fill_type="solid")
            cell.font = Font(bold=True)
        
        # Formatar valores
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if cell.column == 2:  # Coluna de valores
                    cell.font = Font(bold=True)
                    cell.alignment = Alignment(horizontal='center')

def enviar_relatorio_telegram(arquivo_excel):
    """Envia o arquivo Excel para o Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        data_atual = horario_brasil().strftime('%d/%m/%Y')
        
        with open(arquivo_excel, 'rb') as file:
            files = {'document': file}
            data = {
                'chat_id': TELEGRAM_CHAT_ID,
                'caption': f"📊 *RELATÓRIO DIÁRIO* - {data_atual}\n"
                          f"Resumo completo dos produtos monitorados no iFood\n"
                          f"#RelatórioDiário #iFoodMonitoramento",
                'parse_mode': 'Markdown'
            }
            
            response = requests.post(url, files=files, data=data)
            
            if response.status_code == 200:
                print("✅ Relatório enviado com sucesso para o Telegram")
                return True
            else:
                print(f"❌ Erro ao enviar relatório: {response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Erro ao enviar relatório para o Telegram: {str(e)}")
        return False

def baixar_arquivo_github(nome_arquivo):
    """Baixa um arquivo do repositório GitHub"""
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        print(f"⚠️ Configurações do GitHub incompletas. Não foi possível baixar {nome_arquivo}.")
        return False
    
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/contents/{nome_arquivo}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            conteudo_base64 = response.json()["content"]
            conteudo = base64.b64decode(conteudo_base64).decode('utf-8')
            
            with open(nome_arquivo, 'w', encoding='utf-8') as f:
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
        with open(arquivo_local, 'r', encoding='utf-8') as f:
            conteudo = f.read()
        
        conteudo_base64 = base64.b64encode(conteudo.encode('utf-8')).decode('utf-8')
        
        url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/contents/{nome_arquivo_github}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            sha = response.json()["sha"]
            
            payload = {
                "message": f"Atualizar {nome_arquivo_github} - {horario_brasil().strftime('%Y-%m-%d %H:%M:%S')}",
                "content": conteudo_base64,
                "sha": sha
            }
        else:
            payload = {
                "message": f"Adicionar {nome_arquivo_github} - {horario_brasil().strftime('%Y-%m-%d %H:%M:%S')}",
                "content": conteudo_base64
            }
        
        response = requests.put(url, headers=headers, json=payload)
        
        if response.status_code in [200, 201]:
            print(f"✅ Arquivo {nome_arquivo_github} enviado com sucesso para o GitHub")
            
            if nome_arquivo_github == 'index.html':
                url_dashboard = f"https://{GITHUB_ACTOR}.github.io/{GITHUB_REPOSITORY.split('/')[1]}"
                print(f"📊 Dashboard disponível em: {url_dashboard}")
                return url_dashboard
            
            return True
        else:
            print(f"❌ Erro ao enviar arquivo para o GitHub: {response.text}")
            return False
    
    except Exception as e:
        print(f"❌ Erro ao fazer upload para o GitHub: {str(e)}")
        return False

def verificar_status_produto(product):
    """Verifica se o produto está ON (disponível) ou OFF (indisponível)"""
    try:
        try:
            indisponivel = product.find_element(By.CLASS_NAME, 'dish-card--unavailable')
            return "OFF"
        except NoSuchElementException:
            pass
            
        try:
            texto_indisponivel = product.find_element(By.CSS_SELECTOR, '.dish-card__unavailable-label')
            if texto_indisponivel:
                return "OFF"
        except NoSuchElementException:
            pass
            
        try:
            botao_adicionar = product.find_element(By.CSS_SELECTOR, 'button[disabled]')
            if botao_adicionar:
                return "OFF"
        except NoSuchElementException:
            pass
            
        return "ON"
        
    except Exception as e:
        print(f"Erro ao verificar status do produto: {str(e)}")
        return "Erro"

def monitorar_produtos():
    """Função principal para monitorar produtos"""
    timestamp = horario_brasil().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n🔍 Iniciando monitoramento de produtos em {timestamp}")
    salvar_log(f"Iniciando monitoramento de produtos")
    
    estado_anterior = carregar_estado_anterior()
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(20)
    
    dados_produtos = []
    contagem_por_secao = {}
    produtos_off = []
    
    try:
        url = 'https://www.ifood.com.br/delivery/rio-de-janeiro-rj/cumbuca-catete/e2c3f587-3c83-4ea7-8418-a4b693caaaa4'
        driver.get(url)
        
        wait = WebDriverWait(driver, 20)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'restaurant-menu-group__title')))
        
        sections = driver.find_elements(By.CLASS_NAME, 'restaurant-menu-group')
        
        print("🛒 Produtos por Seção:\n")
        
        total_produtos = 0
        total_produtos_off = 0
        
        for section in sections:
            title_element = section.find_element(By.CLASS_NAME, 'restaurant-menu-group__title')
            section_title = title_element.text.strip()
            
            products = section.find_elements(By.CLASS_NAME, 'dish-card')
            quantidade_seção = len(products)
            contagem_por_secao[section_title] = quantidade_seção
            total_produtos += quantidade_seção
            
            print(f"🔹 {section_title} ({quantidade_seção} item{'s' if quantidade_seção != 1 else ''}):\n")
            
            if not products:
                print("  ⚠️ Nenhum produto encontrado nessa seção.\n")
                continue
            
            produtos_off_secao = 0
            
            for idx, product in enumerate(products, start=1):
                name = product.find_element(By.CLASS_NAME, 'dish-card__description').text.strip()
                
                try:
                    description = product.find_element(By.CLASS_NAME, 'dish-card__details').text.strip()
                except NoSuchElementException:
                    description = "Descrição não encontrada"
                
                price_display = extrair_preco(product)
                status = verificar_status_produto(product)
                
                status_icon = "✅" if status == "ON" else "❌"
                print(f"{idx:02d}. {name} - {price_display} - Status: {status_icon} {status}")
                
                produto_info = {
                    'Seção': section_title,
                    'Produto': name,
                    'Preço': price_display,
                    'Descrição': description,
                    'Status': status
                }
                
                dados_produtos.append(produto_info)
                
                if status == "OFF":
                    produtos_off.append(produto_info)
                    produtos_off_secao += 1
                    total_produtos_off += 1
            
            print(f"  ℹ️ Produtos OFF nesta seção: {produtos_off_secao}\n")
        
        print(f"✅ Total de produtos: {total_produtos}")
        print(f"❌ Total de produtos marcados como OFF: {total_produtos_off}")
        
        produtos_atuais = {}
        for produto in dados_produtos:
            chave = f"{produto['Seção']}|{produto['Produto']}"
            produtos_atuais[chave] = produto
        
        produtos_desaparecidos = []
        for chave, info in estado_anterior.items():
            if chave not in produtos_atuais:
                secao, nome = chave.split('|', 1)
                produtos_desaparecidos.append({
                    'Seção': secao,
                    'Produto': nome,
                    'Preço': info.get('Preço', 'N/A'),
                    'Status': 'OFF (Desapareceu)',
                    'Última verificação': info.get('Última verificação', 'Desconhecido'),
                    'Descrição': info.get('Descrição', '')
                })
        
        if produtos_desaparecidos:
            print(f"\n⚠️ ALERTA: {len(produtos_desaparecidos)} produtos desapareceram desde a última verificação!")
            salvar_log(f"ALERTA: {len(produtos_desaparecidos)} produtos desapareceram")
            
            for p in produtos_desaparecidos[:5]:  # Mostrar apenas os 5 primeiros para não poluir o log
                print(f"  ❌ {p['Seção']} - {p['Produto']} - Última verificação: {p['Última verificação']}")
        else:
            print("\n✅ Nenhum produto desapareceu desde a última verificação.")
        
        salvar_estado_produtos(dados_produtos)
        historico = atualizar_historico_status(dados_produtos, produtos_desaparecidos)
        gerar_dashboard_html(historico)
        
        # Salvar dados em Excel
        arquivo_excel = 'produtos_cumbuca.xlsx'
        
        for produto in produtos_desaparecidos:
            dados_produtos.append(produto)
            total_produtos_off += 1
        
        df = pd.DataFrame(dados_produtos)
        
        for coluna in ['Seção', 'Produto', 'Preço', 'Descrição', 'Status', 'Última verificação']:
            if coluna not in df.columns:
                df[coluna] = ''
        
        colunas = ['Seção', 'Produto', 'Preço', 'Descrição', 'Status']
        if 'Última verificação' in df.columns:
            colunas.append('Última verificação')
        df = df[colunas]
        
        df_contagem = pd.DataFrame(list(contagem_por_secao.items()), columns=['Seção', 'Quantidade de Itens'])
        
        linha_em_branco = pd.DataFrame([{col: '' for col in df.columns}])
        linha_total = pd.DataFrame([{
            'Seção': 'TOTAL DE PRODUTOS', 
            'Produto': total_produtos, 
            'Status': f'OFF: {total_produtos_off} ({len(produtos_desaparecidos)} desaparecidos)'
        }])
        
        with pd.ExcelWriter(arquivo_excel, engine='openpyxl', mode='w') as writer:
            df.to_excel(writer, sheet_name='Produtos', index=False)
            linha_em_branco.to_excel(writer, sheet_name='Produtos', index=False, header=False, startrow=len(df)+1)
            df_contagem.to_excel(writer, sheet_name='Produtos', index=False, startrow=len(df)+2)
            linha_total.to_excel(writer, sheet_name='Produtos', index=False, header=False, startrow=len(df)+2+len(df_contagem)+1)
        
        # Formatar Excel
        wb = load_workbook(arquivo_excel)
        ws = wb['Produtos']
        
        bold_font = Font(bold=True)
        center_align = Alignment(horizontal='center', vertical='center')
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        fill_off = PatternFill(start_color="FFCCCC", end_color="FFCCCC", fill_type="solid")
        fill_on = PatternFill(start_color="CCFFCC", end_color="CCFFCC", fill_type="solid")
        fill_desaparecido = PatternFill(start_color="FFEECC", end_color="FFEECC", fill_type="solid")
        
        for cell in ws[1]:
            cell.font = bold_font
            cell.alignment = center_align
            cell.border = thin_border
        
        max_row = ws.max_row
        max_col = ws.max_column
        for row in ws.iter_rows(min_row=2, max_row=max_row, min_col=1, max_col=max_col):
            for cell in row:
                cell.border = thin_border
                
                if cell.column == 5:  # Coluna de Status
                    if cell.value == "OFF":
                        cell.fill = fill_off
                    elif cell.value == "ON":
                        cell.fill = fill_on
                    elif cell.value and "Desapareceu" in str(cell.value):
                        cell.fill = fill_desaparecido
                        for c in row:
                            c.fill = fill_desaparecido
        
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
        fazer_upload_github(arquivo_excel, arquivo_excel)
        
        print(f"\n✅ Dados formatados e salvos com sucesso em: {arquivo_excel}")
        salvar_log(f"Monitoramento concluído. Total: {total_produtos}, OFF: {total_produtos_off}, Desaparecidos: {len(produtos_desaparecidos)}")
        
        total_produtos_ativos = total_produtos - total_produtos_off
        
        # Enviar relatório diário às 23h
        if horario_brasil().hour == 23:  # Horário de Brasília
            print("\n🕚 Horário de gerar relatório diário (23h)")
            nome_relatorio = gerar_relatorio_diario()
            if nome_relatorio:
                if enviar_relatorio_telegram(nome_relatorio):
                    os.remove(nome_relatorio)  # Limpar arquivo após envio
        
        if produtos_off or produtos_desaparecidos:
            total_problemas = len(produtos_off) + len(produtos_desaparecidos)
            print(f"\n⚠️ ALERTA: {total_problemas} produtos com problemas!")
            salvar_log(f"ALERTA: {total_problemas} produtos com problemas")
            
            mensagem = f"Total de {total_problemas} produtos com problemas. Verifique o relatório completo."
            
            enviar_alerta_telegram(
                mensagem, 
                produtos_off, 
                produtos_desaparecidos, 
                total_produtos_ativos,
                dados_produtos
            )
            
        else:
            print("\n✅ Todos os produtos estão ON e nenhum desapareceu!")
            salvar_log("Todos os produtos estão ON e nenhum desapareceu")
            
            mensagem = "✅ Todos os produtos estão ON e nenhum desapareceu!"
            enviar_alerta_telegram(
                mensagem,
                None,
                None,
                total_produtos,
                dados_produtos
            )
        
        return {
            'total_produtos': total_produtos,
            'produtos_off': produtos_off,
            'produtos_desaparecidos': produtos_desaparecidos,
            'total_produtos_ativos': total_produtos_ativos,
            'timestamp': timestamp
        }
        
    except TimeoutException:
        erro_msg = "❌ Tempo
