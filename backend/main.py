import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import time
from datetime import datetime
import pytz
import json
import os

# --- Modelos de Dados (Pydantic) ---
class PosicaoOnibusFormatada(BaseModel):
    ordem: str
    linha: str
    latitude: float
    longitude: float
    velocidade: float
    hora_atualizacao: str

class Alerta(BaseModel):
    email: str
    linha: str
    latitude_ponto: float
    longitude_ponto: float

# --- Configuração do App FastAPI ---
app = FastAPI(
    title="API Alerta de Ônibus RJ",
    description="API para consultar posições de ônibus em tempo real e gerenciar alertas.",
    version="2.1.0" # Versão com persistência de alertas
)

# --- Middleware de CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- INÍCIO DA CORREÇÃO: Armazenamento em Ficheiro ---
ALERTS_FILE = "alerts.json"

def carregar_alertas() -> List[Alerta]:
    """Carrega os alertas do ficheiro JSON."""
    if not os.path.exists(ALERTS_FILE):
        return []
    try:
        with open(ALERTS_FILE, 'r') as f:
            data = json.load(f)
            # Valida os dados carregados com o modelo Pydantic
            return [Alerta(**alerta) for alerta in data]
    except (json.JSONDecodeError, TypeError):
        return []

def salvar_alertas(alertas: List[Alerta]):
    """Salva a lista de alertas no ficheiro JSON."""
    with open(ALERTS_FILE, 'w') as f:
        # Converte a lista de objetos Pydantic para uma lista de dicionários
        json.dump([alerta.dict() for alerta in alertas], f, indent=4)
# --- FIM DA CORREÇÃO ---


# --- Cache em Memória (para os dados dos autocarros) ---
cache: Dict[str, Any] = { "dados_completos": None, "ultima_busca": 0 }
TEMPO_VIDA_CACHE_SEGUNDOS = 45

# --- Endpoints da API ---
@app.get("/")
def read_root():
    return {"status": "API Alerta de Ônibus RJ está no ar!"}

@app.post("/api/v1/alertas")
def criar_alerta(alerta: Alerta):
    print(f"INFO: Recebido novo alerta para o e-mail {alerta.email} na linha {alerta.linha}")
    # Carrega os alertas existentes, adiciona o novo e salva tudo de volta no ficheiro.
    alertas_atuais = carregar_alertas()
    alertas_atuais.append(alerta)
    salvar_alertas(alertas_atuais)
    return {"status": "sucesso", "mensagem": "Alerta criado e salvo com sucesso!"}


@app.get("/api/v1/posicoes/{linha_onibus}", response_model=List[PosicaoOnibusFormatada])
def get_posicoes_onibus(linha_onibus: str):
    # Esta função continua a mesma, pois o cache dos autocarros pode continuar em memória.
    global cache
    agora = time.time()

    if not cache["dados_completos"] or (agora - cache["ultima_busca"]) > TEMPO_VIDA_CACHE_SEGUNDOS:
        print("INFO: Cache expirado. Buscando novos dados...")
        api_url = "https://dados.mobilidade.rio/gps/sppo"
        headers = {'User-Agent': 'Mozilla/5.0'}
        try:
            response = requests.get(api_url, headers=headers, timeout=15)
            response.raise_for_status()
            cache["dados_completos"] = response.json()
            cache["ultima_busca"] = agora
        except requests.RequestException as e:
            raise HTTPException(status_code=503, detail=f"Erro de comunicação com a API de dados: {e}")
    
    todos_os_onibus = cache["dados_completos"]
    if not todos_os_onibus or not isinstance(todos_os_onibus, list):
        return []

    def get_timestamp(onibus):
        try: return int(onibus.get("datahora", 0))
        except: return 0

    onibus_ordenados = sorted(todos_os_onibus, key=get_timestamp, reverse=True)
    ordens_vistas = set()
    onibus_unicos = []
    for dados_onibus in onibus_ordenados:
        ordem = dados_onibus.get("ordem")
        if ordem and ordem not in ordens_vistas:
            onibus_unicos.append(dados_onibus)
            ordens_vistas.add(ordem)

    posicoes_filtradas = []
    fuso_horario_rj = pytz.timezone('America/Sao_Paulo')
    hoje = datetime.now(fuso_horario_rj).date()

    for dados_onibus in onibus_unicos:
        if dados_onibus.get("linha") == linha_onibus:
            try:
                timestamp_ms = int(dados_onibus.get("datahora", 0))
                if timestamp_ms == 0: continue
                
                data_onibus_dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=fuso_horario_rj)

                if data_onibus_dt.date() == hoje:
                    dados_formatados = {
                        "ordem": dados_onibus.get("ordem"),
                        "linha": dados_onibus.get("linha"),
                        "latitude": float(str(dados_onibus.get('latitude', '0')).replace(',', '.')),
                        "longitude": float(str(dados_onibus.get('longitude', '0')).replace(',', '.')),
                        "velocidade": dados_onibus.get("velocidade", 0),
                        "hora_atualizacao": data_onibus_dt.strftime('%H:%M:%S')
                    }
                    posicoes_filtradas.append(PosicaoOnibusFormatada(**dados_formatados))
            except (ValueError, TypeError, KeyError):
                continue
    
    return posicoes_filtradas

