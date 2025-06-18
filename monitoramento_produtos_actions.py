import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, Border, Side, Alignment
from openpyxl.utils import get_column_letter

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

chromedriver_path = r'C:\Users\zz\Desktop\Nebraska Códigos\Código Itens Cumbuca\chromedriver.exe'

options = Options()
options.add_argument('--headless')
options.add_argument('--disable-gpu')
options.add_argument('--window-size=1920,1080')

service = Service(chromedriver_path)
driver = webdriver.Chrome(service=service, options=options)

dados_produtos = []
contagem_por_secao = {}

try:
    url = 'https://www.ifood.com.br/delivery/rio-de-janeiro-rj/cumbuca-catete/e2c3f587-3c83-4ea7-8418-a4b693caaaa4'
    driver.get(url)

    wait = WebDriverWait(driver, 20)
    wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'restaurant-menu-group__title')))

    sections = driver.find_elements(By.CLASS_NAME, 'restaurant-menu-group')

    print("🛒 Produtos por Seção:\n")

    total_produtos = 0

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

        for idx, product in enumerate(products, start=1):
            name = product.find_element(By.CLASS_NAME, 'dish-card__description').text.strip()

            try:
                description = product.find_element(By.CLASS_NAME, 'dish-card__details').text.strip()
            except NoSuchElementException:
                description = "Descrição não encontrada"

            price_display = extrair_preco(product)

            print(f"{idx:02d}. {name} - {price_display}")

            dados_produtos.append({
                'Seção': section_title,
                'Produto': name,
                'Preço': price_display,
                'Descrição': description
            })

        print("\n")

    print(f"✅ Total de produtos: {total_produtos}")

except TimeoutException:
    print("❌ Tempo esgotado esperando a página carregar os produtos.")
except Exception as e:
    print(f"❌ Erro inesperado: {str(e)}")
finally:
    driver.quit()

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
arquivo_excel = os.path.join(diretorio_atual, 'produtos_cumbuca.xlsx')

df = pd.DataFrame(dados_produtos)
df = df[['Seção', 'Produto', 'Preço', 'Descrição']]

df_contagem = pd.DataFrame(list(contagem_por_secao.items()), columns=['Seção', 'Quantidade de Itens'])

linha_em_branco = pd.DataFrame([{'Seção': '', 'Produto': '', 'Preço': '', 'Descrição': ''}])
linha_total = pd.DataFrame([{'Seção': 'TOTAL DE PRODUTOS', 'Produto': total_produtos}])

with pd.ExcelWriter(arquivo_excel, engine='openpyxl', mode='w') as writer:
    df.to_excel(writer, sheet_name='Produtos', index=False)
    linha_em_branco.to_excel(writer, sheet_name='Produtos', index=False, header=False, startrow=len(df)+1)
    df_contagem.to_excel(writer, sheet_name='Produtos', index=False, startrow=len(df)+2)
    linha_total.to_excel(writer, sheet_name='Produtos', index=False, header=False, startrow=len(df)+2+len(df_contagem)+1)

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

for cell in ws[1]:
    cell.font = bold_font
    cell.alignment = center_align
    cell.border = thin_border

max_row = ws.max_row
max_col = ws.max_column
for row in ws.iter_rows(min_row=2, max_row=max_row, min_col=1, max_col=max_col):
    for cell in row:
        cell.border = thin_border

wb.save(arquivo_excel)

print(f"\n✅ Dados formatados e salvos com sucesso em: {arquivo_excel}")
