import os
import sqlite3
import logging
import requests
import smtplib
from datetime import datetime
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuração da pasta raiz do script para evitar erros de caminhos no Windows/Linux
pasta_do_script = os.path.dirname(os.path.abspath(__file__))
caminho_do_env = os.path.join(pasta_do_script, ".env")

# Garante a criação e leitura correta do arquivo de configuração oculto (.env)
if not os.path.exists(caminho_do_env):
    conteudo_inicial = (
        "EMAIL_REMETENTE=thiago.python04@gmail.com\n"
        "EMAIL_SENHA=xzjpqvsofjfjledo\n"
        "EMAIL_DESTINATARIO=trcoutinho0404@gmail.com"
    )
    with open(caminho_do_env, "w", encoding="utf-8") as f:
        f.write(conteudo_inicial)

load_dotenv(dotenv_path=caminho_do_env)

# Configuração de Logs para registrar o comportamento do robô em produção
caminho_do_log = os.path.join(pasta_do_script, "pipeline_cambio.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(caminho_do_log, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Captura das credenciais do ambiente
EMAIL_REMETENTE = os.getenv("EMAIL_REMETENTE")
EMAIL_SENHA = os.getenv("EMAIL_SENHA")
EMAIL_DESTINATARIO = os.getenv("EMAIL_DESTINATARIO")


def criar_banco():
    """Garante a criação do banco de dados SQLite local e da tabela histórica."""
    caminho_banco = os.path.join(pasta_do_script, "cotacoes.db")
    conexao = sqlite3.connect(caminho_banco)
    cursor = conexao.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico_moedas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            moeda TEXT NOT NULL,
            valor_reais REAL NOT NULL,
            data_consulta TEXT NOT NULL
        )
    """)
    conexao.commit()
    conexao.close()


def buscar_cotacoes():
    """Consome a API AwesomeAPI para obter as cotações atuais de USD, EUR e GBP."""
    url = "https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL,GBP-BRL"
    try:
        resposta = requests.get(url, timeout=10)
        resposta.raise_for_status()
        dados = resposta.json()

        return {
            "USD": float(dados["USDBRL"]["bid"]),
            "EUR": float(dados["EURBRL"]["bid"]),
            "GBP": float(dados["GBPBRL"]["bid"])
        }
    except Exception as e:
        logging.error(f"Erro ao consumir a API de cotações: {e}")
        return None


def obter_ultima_cotacao(moeda):
    """Busca o último registro da moeda no banco para fins de comparação de tendência."""
    caminho_banco = os.path.join(pasta_do_script, "cotacoes.db")
    conexao = sqlite3.connect(caminho_banco)
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT valor_reais FROM historico_moedas 
        WHERE moeda = ? 
        ORDER BY id DESC LIMIT 1
    """, (moeda,))

    resultado = cursor.fetchone()
    conexao.close()
    return resultado[0] if resultado else None


def enviar_alerta_email(moeda, valor_atual, valor_anterior, variacao_ou_msg):
    """Envia alertas customizados em formato HTML para múltiplos destinatários via SMTP."""
    if not EMAIL_REMETENTE or not EMAIL_SENHA or not EMAIL_DESTINATARIO:
        logging.error("Credenciais de e-mail ausentes. Envio cancelado.")
        return

    # Converte a string de e-mails em uma lista aceita pelo smtplib
    lista_destinatarios = [email.strip() for email in EMAIL_DESTINATARIO.split(",")]

    msg = MIMEMultipart()
    msg['From'] = EMAIL_REMETENTE
    msg['To'] = EMAIL_DESTINATARIO
    msg['Subject'] = f"📊 ALERTA DE MERCADO: Movimentação expressiva no {moeda}!"

    # Define a cor e o texto dinâmico baseado no tipo de alerta (fixo ou percentual)
    if isinstance(variacao_ou_msg, (int, float)):
        status_alerta = f"{variacao_ou_msg:+.2f}%"
        cor_status = 'green' if variacao_ou_msg < 0 else 'red'
    else:
        status_alerta = str(variacao_ou_msg)
        cor_status = 'orange'

    texto_valor_anterior = f"R$ {valor_anterior:.4f}" if valor_anterior else "N/A"

    corpo_html = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #d9534f;">🚨 Flutuação Cambial Detectada</h2>
            <p>Olá,</p>
            <p>O sistema automatizado identificou uma movimentação relevante na moeda <strong>{moeda}</strong>:</p>
            <table border="1" cellpadding="8" style="border-collapse: collapse; border-color: #ddd;">
                <tr style="background-color: #f5f5f5;"><th>Métrica</th><th>Valor</th></tr>
                <tr><td>Cotação Atual</td><td><strong>R$ {valor_atual:.4f}</strong></td></tr>
                <tr><td>Cotação Anterior</td><td>{texto_valor_anterior}</td></tr>
                <tr><td>Status do Alerta</td><td style="color: {cor_status};"><strong>{status_alerta}</strong></td></tr>
            </table>
            <br>
            <p><em>Relatório automatizado gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</em></p>
        </body>
    </html>
    """
    msg.attach(MIMEText(corpo_html, 'html'))

    try:
        servidor = smtplib.SMTP('smtp.gmail.com', 587)
        servidor.starttls()
        servidor.login(EMAIL_REMETENTE, EMAIL_SENHA)
        servidor.sendmail(EMAIL_REMETENTE, lista_destinatarios, msg.as_string())
        servidor.quit()
        logging.info(f"✅ Alerta enviado com sucesso para {len(lista_destinatarios)} destinatários.")
    except Exception as e:
        logging.error(f"Falha ao disparar e-mail: {e}")


def processar_pipeline():
    """Executa o fluxo completo (ETL) e aplica as regras de negócio."""
    logging.info("Iniciando execução do pipeline de dados cambiais...")
    criar_banco()

    dados_atuais = buscar_cotacoes()
    if not dados_atuais:
        return

    caminho_banco = os.path.join(pasta_do_script, "cotacoes.db")
    conexao = sqlite3.connect(caminho_banco)
    cursor = conexao.cursor()
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for moeda, valor_atual in dados_atuais.items():
        valor_anterior = obter_ultima_cotacao(moeda)

        # Regra 1: Validação de Tendência Percentual (Oscilações acima de 0.1%)
        if valor_anterior:
            variacao = ((valor_atual - valor_anterior) / valor_anterior) * 100
            if abs(variacao) >= 0.1:
                enviar_alerta_email(moeda, valor_atual, valor_anterior, variacao)

        # Regra 2: Alerta de Segurança de Teto Crítico Fixo (Dólar >= R$ 5,05)
        if moeda == "USD" and valor_atual >= 5.05:
            enviar_alerta_email(
                moeda=moeda,
                valor_atual=valor_atual,
                valor_anterior=valor_anterior if valor_anterior else valor_atual,
                variacao_ou_msg="ULTRAPASSOU o limite crítico fixo de R$ 5,05!"
            )

        # Gravação final no banco de dados local
        cursor.execute("""
            INSERT INTO historico_moedas (moeda, valor_reais, data_consulta)
            VALUES (?, ?, ?)
        """, (moeda, valor_atual, data_atual))
        logging.info(f"Registro persistido: {moeda} -> R$ {valor_atual:.4f}")

    conexao.commit()
    conexao.close()
    logging.info("🏁 Pipeline finalizado com sucesso.")


if __name__ == "__main__":
    processar_pipeline()