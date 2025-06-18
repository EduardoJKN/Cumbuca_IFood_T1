# Arquivo atualizado com envio de Excel para Telegram
import os, requests

def horario_brasil():
    import datetime
    return datetime.datetime.now() - datetime.timedelta(hours=3)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GITHUB_REPOSITORY = os.getenv('GITHUB_REPOSITORY')
GITHUB_ACTOR = os.getenv('GITHUB_ACTOR')

def enviar_alerta_telegram(mensagem, produtos_off=None, produtos_desaparecidos=None, total_produtos_ativos=0, todos_produtos=None):
    """Envia alerta para um grupo no Telegram, incluindo o relatório em Excel"""
    try:
        url_dashboard = f"https://{GITHUB_ACTOR}.github.io/{GITHUB_REPOSITORY.split('/')[1]}" if GITHUB_ACTOR and GITHUB_REPOSITORY else None
        
        texto = f"🚨 ALERTA: Monitoramento de Produtos iFood 🚨\n\n"
        texto += f"Data/Hora: {horario_brasil().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
        texto += f"✅ Produtos ativos no site: {total_produtos_ativos}\n\n"

        if produtos_desaparecidos:
            texto += f"⚠️ {len(produtos_desaparecidos)} produtos DESAPARECERAM (OFF):\n"
            for p in produtos_desaparecidos[:10]:
                texto += f"- {p['Seção']} - {p['Produto']} - Preço: {p['Preço']}\n"
            if len(produtos_desaparecidos) > 10:
                texto += f"... e mais {len(produtos_desaparecidos) - 10} produtos\n"
            texto += "\n"

        if produtos_off:
            texto += f"⚠️ {len(produtos_off)} produtos marcados como OFF no site:\n"
            for p in produtos_off[:5]:
                texto += f"- {p['Seção']} - {p['Produto']} - Preço: {p['Preço']}\n"
            if len(produtos_off) > 5:
                texto += f"... e mais {len(produtos_off) - 5} produtos\n"
            texto += "\n"

        if todos_produtos:
            produtos_por_secao = {}
            for produto in todos_produtos:
                secao = produto['Seção']
                if secao not in produtos_por_secao:
                    produtos_por_secao[secao] = {'total': 0, 'off': 0, 'desaparecidos': 0}
                produtos_por_secao[secao]['total'] += 1
                if 'Desapareceu' in produto.get('Status', ''):
                    produtos_por_secao[secao]['desaparecidos'] += 1
                    produtos_por_secao[secao]['off'] += 1
                elif produto.get('Status') != 'ON':
                    produtos_por_secao[secao]['off'] += 1

            texto += "📊 Status por Seção:\n"
            for secao, contagem in sorted(produtos_por_secao.items()):
                on = contagem['total'] - contagem['off']
                texto += f"- {secao}: 🟢 {on} ON | 🔴 {contagem['off']} OFF"
                if contagem['desaparecidos'] > 0:
                    texto += f" (inclui {contagem['desaparecidos']} desaparecidos)"
                texto += "\n"
            texto += "\n"

        texto += f"{mensagem}\n\n"
        if url_dashboard:
            texto += f"🔗 Dashboard: {url_dashboard}"
        else:
            texto += "🔗 Dashboard em HTML"

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": texto}
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            print("✅ Alerta enviado com sucesso para o Telegram")
        else:
            print(f"❌ Erro ao enviar alerta para o Telegram: {response.text}")

        try:
            with open('produtos_cumbuca.xlsx', 'rb') as f:
                files = {'document': f}
                data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': '📊 Relatório completo em Excel'}
                response_doc = requests.post(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument', data=data, files=files)
            
            if response_doc.status_code == 200:
                print("✅ Arquivo Excel enviado com sucesso para o Telegram")
            else:
                print(f"❌ Erro ao enviar arquivo Excel: {response_doc.text}")
        except Exception as e:
            print(f"❌ Exceção ao enviar arquivo Excel: {str(e)}")

        return True

    except Exception as e:
        print(f"❌ Erro ao enviar alerta para o Telegram: {str(e)}")
        return False
