import requests
from celery import Celery
from celery.schedules import crontab
from geopy.distance import great_circle
import logging
import json
import os
import time
from pydantic import BaseModel
from datetime import datetime
import pytz
import smtplib
import ssl
from email.message import EmailMessage
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do ficheiro .env (EMAIL_HOST_USER, etc.)
load_dotenv()

# --- Modelos e Constantes ---
class Alerta(BaseModel):
    email: str
    linha: str
    latitude_ponto: float
    longitude_ponto: float

ALERTS_FILE = "alerts.json"
NOTIFICATIONS_LOG_FILE = "sent_notifications.json" 
NOTIFICATION_COOLDOWN_SECONDS = 1800 

# --- Funções de Carregamento de Dados ---
def carregar_alertas_tarefa() -> list[Alerta]:
    if not os.path.exists(ALERTS_FILE): return []
    try:
        with open(ALERTS_FILE, 'r') as f:
            return [Alerta(**alerta) for alerta in json.load(f)]
    except (json.JSONDecodeError, TypeError): return []

def carregar_log_notificacoes() -> dict:
    if not os.path.exists(NOTIFICATIONS_LOG_FILE): return {}
    try:
        with open(NOTIFICATIONS_LOG_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, TypeError): return {}

def salvar_log_notificacoes(log: dict):
    with open(NOTIFICATIONS_LOG_FILE, 'w') as f:
        json.dump(log, f, indent=4)

# --- INÍCIO DA ATUALIZAÇÃO: Função de Envio de E-mail ---
def enviar_email_alerta(alerta: Alerta, dados_onibus: dict, distancia_km: float):
    """Função para construir e enviar o e-mail de notificação."""
    email_remetente = os.getenv("EMAIL_HOST_USER")
    email_senha = os.getenv("EMAIL_HOST_PASSWORD")
    email_destinatario = alerta.email

    if not email_remetente or not email_senha:
        logger.error("Credenciais de e-mail não configuradas no ficheiro .env. O e-mail não será enviado.")
        return

    assunto = f"Alerta de Ônibus: Linha {alerta.linha} está a chegar!"
    corpo = f"""
    Olá!

    O ônibus da linha {alerta.linha}, ordem {dados_onibus.get('ordem')}, está a aproximadamente {distancia_km:.2f} km do seu ponto de partida.

    Prepare-se!

    - Velocidade atual: {dados_onibus.get('velocidade', 'N/A')} km/h
    - Última atualização: {dados_onibus.get('hora_atualizacao', 'N/A')}

    Atenciosamente,
    Sistema de Alerta de Ônibus RJ
    """

    em = EmailMessage()
    em['From'] = email_remetente
    em['To'] = email_destinatario
    em['Subject'] = assunto
    em.set_content(corpo)

    contexto_ssl = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=contexto_ssl) as smtp:
            smtp.login(email_remetente, email_senha)
            smtp.sendmail(email_remetente, email_destinatario, em.as_string())
        logger.info(f"E-mail de alerta enviado com sucesso para {email_destinatario}")
    except Exception as e:
        logger.error(f"Falha ao enviar e-mail para {email_destinatario}: {e}")
# --- FIM DA ATUALIZAÇÃO ---

# --- Configuração do Celery ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

celery_app = Celery('tasks', broker='redis://127.0.0.1:6379/0', backend='redis://127.0.0.1:6379/0')
celery_app.conf.beat_schedule = {
    'verificar-alertas-a-cada-minuto': { 'task': 'tasks.verificar_alertas', 'schedule': crontab() },
}
celery_app.conf.timezone = 'America/Sao_Paulo'

@celery_app.task
def verificar_alertas():
    logger.info("Iniciando verificação de alertas...")
    alertas_cadastrados = carregar_alertas_tarefa()
    if not alertas_cadastrados:
        logger.info("Nenhum alerta salvo para verificar.")
        return

    try:
        response = requests.get("https://dados.mobilidade.rio/gps/sppo", headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        response.raise_for_status()
        todos_os_onibus_raw = response.json()
    except requests.RequestException as e:
        logger.error(f"Falha ao buscar dados dos ônibus: {e}")
        return

    def get_timestamp(onibus):
        try: return int(onibus.get("datahora", 0))
        except (ValueError, TypeError): return 0

    onibus_ordenados = sorted(todos_os_onibus_raw, key=get_timestamp, reverse=True)
    ordens_vistas, onibus_unicos = set(), []
    for dados in onibus_ordenados:
        ordem = dados.get("ordem")
        if ordem and ordem not in ordens_vistas:
            onibus_unicos.append(dados); ordens_vistas.add(ordem)
    
    onibus_de_hoje = []
    fuso_horario_rj = pytz.timezone('America/Sao_Paulo')
    hoje = datetime.now(fuso_horario_rj).date()
    for dados in onibus_unicos:
        if get_timestamp(dados) > 0 and datetime.fromtimestamp(get_timestamp(dados) / 1000, tz=fuso_horario_rj).date() == hoje:
            onibus_de_hoje.append(dados)

    notification_log = carregar_log_notificacoes()
    agora = time.time()

    for alerta in alertas_cadastrados:
        for dados_onibus in onibus_de_hoje:
            if dados_onibus.get("linha") == alerta.linha:
                try:
                    ordem_onibus = dados_onibus.get("ordem")
                    if not ordem_onibus: continue

                    notification_key = f"{alerta.email}_{ordem_onibus}"
                    if (agora - notification_log.get(notification_key, 0)) < NOTIFICATION_COOLDOWN_SECONDS:
                        continue
                    
                    ponto_alerta = (alerta.latitude_ponto, alerta.longitude_ponto)
                    posicao_onibus = (float(str(dados_onibus.get('latitude', '0')).replace(',', '.')), float(str(dados_onibus.get('longitude', '0')).replace(',', '.')))
                    distancia_km = great_circle(ponto_alerta, posicao_onibus).kilometers
                    
                    if distancia_km <= 1.5:
                        # ATUALIZAÇÃO: Prepara os dados e chama a função de envio de e-mail
                        timestamp_ms = get_timestamp(dados_onibus)
                        hora_atualizacao = datetime.fromtimestamp(timestamp_ms / 1000, tz=fuso_horario_rj).strftime('%H:%M:%S') if timestamp_ms > 0 else "N/A"
                        
                        dados_onibus_formatados = {
                            "ordem": ordem_onibus,
                            "velocidade": dados_onibus.get("velocidade"),
                            "hora_atualizacao": hora_atualizacao
                        }
                        
                        enviar_email_alerta(alerta, dados_onibus_formatados, distancia_km)
                        notification_log[notification_key] = agora
                        
                except (ValueError, TypeError, KeyError):
                    continue
    
    salvar_log_notificacoes(notification_log)
    logger.info("Verificação de alertas concluída.")

