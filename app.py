import streamlit as st
import pandas as pd
import boto3

# 1. Configuração do Cliente AWS
# (O Streamlit vai pegar as chaves automaticamente do Secrets)
s3 = boto3.client('s3')
NOME_DO_BUCKET = 'ele-2022-brutos'

# Nomes EXATOS capturados pelo nosso diagnóstico
ARQUIVO_VOTACAO = 'votacao_municipio_2022_BRASIL_com_coordenads_caracteristicas.csv'
ARQUIVO_DESPESAS = 'despesas_candidatos.csv'

# 2. Função de carregamento com Cache (Para não baixar do S3 toda hora)
@st.cache_data(ttl=3600)
def carregar_dados_votacao():
    # Fazemos apenas a requisição do objeto, sem baixar tudo de uma vez
    obj = s3.get_object(Bucket=NOME_DO_BUCKET, Key=ARQUIVO_VOTACAO)
    
    # Colunas que seu mapa e filtros realmente precisam (ajuste se necessário)
    colunas_necessarias = [
        'NM_UE', 'DS_CARGO', 'NM_CANDIDATO', 'SQ_CANDIDATO', 
        'code_meso', 'name_meso', 'QT_VOTOS_NOMINAIS_VALIDOS', 
        'latitude', 'longitude'
    ]
    
    # Otimização extrema de tipos (category gasta MUITO menos RAM que object/string)
    tipos_otimizados = {
        'NM_UE': 'category',
        'DS_CARGO': 'category',
        'NM_CANDIDATO': 'category',
        'code_meso': 'category',
        'name_meso': 'category',
        'QT_VOTOS_NOMINAIS_VALIDOS': 'int32', # int32 ocupa metade do espaço do int64 padrão
        'latitude': 'float32',
        'longitude': 'float32'
    }

    # Passamos o obj['Body'] direto para o Pandas. Ele lê o stream de rede.
    df = pd.read_csv(
        obj['Body'], 
        usecols=colunas_necessarias, 
        dtype=tipos_otimizados,
        encoding='utf-8' # ou 'latin1' se você tiver problemas de acentuação
    )
    return df

@st.cache_data(ttl=3600)
def carregar_dados_despesas():
    obj = s3.get_object(Bucket=NOME_DO_BUCKET, Key=ARQUIVO_DESPESAS)
    
    colunas_necessarias = ['SQ_CANDIDATO', 'TOTAL_DESPESA'] # Ajuste para as colunas reais de despesa
    tipos_otimizados = {
        'TOTAL_DESPESA': 'float32'
    }
    
    df = pd.read_csv(
        obj['Body'], 
        usecols=colunas_necessarias, 
        dtype=tipos_otimizados,
        encoding='utf-8',
        # Como o SQ_CANDIDATO no arquivo de votação pode virar float/string, 
        # mantenha-o como string para facilitar os filtros (joins).
        converters={'SQ_CANDIDATO': str} 
    )
    return df

# === Execução ===
st.title("🗳️ Mapa de Votação (AWS S3)")

with st.spinner("Baixando e otimizando dados gigantes do S3..."):
    try:
        df_votacao = carregar_dados_votacao()
        st.success(f"Dados de votação carregados! Linhas: {len(df_votacao):,}")
        
        # A partir daqui, você utiliza o df_votacao para alimentar os st.selectbox
        # do estado, cargo e candidato do seu código original!
        
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")


import os
import streamlit as st
import pandas as pd
import pydeck as pdk
import numpy as np
import boto3
from io import StringIO
from dotenv import load_dotenv

# Carrega chaves locais se existirem (para desenvolvimento local)
load_dotenv()

st.title("🗳️ Mapa de Votação por Mesorregião (2022)")

# === Configuração de Acesso AWS S3 ===
AWS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REG = os.getenv("AWS_REGION", "us-east-2")
BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")

if not AWS_KEY or not AWS_SECRET or not BUCKET_NAME:
    st.error("❌ Credenciais da AWS S3 não encontradas. Configure em Advanced Settings -> Secrets no Streamlit Cloud.")
    st.stop()

# Inicializa o cliente oficial da AWS
@st.cache_resource
def iniciar_cliente_s3():
    return boto3.client(
        "s3",
        aws_access_key_id=AWS_KEY,
        aws_secret_access_key=AWS_SECRET,
        region_name=AWS_REG
    )

s3_client = iniciar_cliente_s3()

# === 1. Função Nativa de Carregamento S3 ===
def carregar_dados_s3(nome_arquivo):
    colunas_para_ler = [
        "NM_UE", "DS_CARGO", "SQ_CANDIDATO", "NM_CANDIDATO", 
        "code_meso", "name_meso", "latitude", "longitude", "QT_VOTOS_NOMINAIS_VALIDOS"
    ]
    
    tipos_dados = {
        "NM_UE": "category",
        "DS_CARGO": "category",
        "SQ_CANDIDATO": "str",
        "code_meso": "category",
        "QT_VOTOS_NOMINAIS_VALIDOS": "int32"
    }

    objeto_s3 = s3_client.get_object(Bucket=BUCKET_NAME, Key=nome_arquivo)
    corpo_arquivo = objeto_s3["Body"].read().decode("utf-8")
    
    df = pd.read_csv(StringIO(corpo_arquivo), sep=",", usecols=colunas_para_ler, dtype=tipos_dados)
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["latitude", "longitude", "QT_VOTOS_NOMINAIS_VALIDOS"])
    return df

# === 2. Diagnóstico de Nome do Arquivo ===
NOME_ARQUIVO_VOTOS = "votacao_municipio_2022_BRASIL_com_coordenads_caracteristicas.csv"

@st.cache_data
def testar_e_carregar_dados(nome_arquivo):
    with st.spinner("Conectando à AWS e processando dados de votação..."):
        try:
            return carregar_dados_s3(nome_arquivo)
        except Exception as e:
            st.error(f"❌ Erro ao baixar arquivo de votos do S3: {e}")
            
            # Bloco de diagnóstico: lista os arquivos reais do seu S3 na tela
            try:
                st.info("🔍 Analisando seu Bucket... Confira abaixo a lista dos nomes EXATOS dos arquivos salvos na AWS S3:")
                resposta = s3_client.list_objects_v2(Bucket=BUCKET_NAME)
                if 'Contents' in resposta:
                    for obj in resposta['Contents']:
                        st.code(obj['Key'])
                    st.caption("💡 Se o nome acima for diferente, copie ele e substitua na linha 53 do seu app.py no GitHub.")
                else:
                    st.warning("O Bucket parece estar vazio ou sem arquivos acessíveis.")
            except Exception as erro_lista:
                st.error(f"Não foi possível listar o bucket: {erro_lista}")
                
            st.stop()

# Executa o carregamento seguro da base de votação
df = testar_e_carregar_dados(NOME_ARQUIVO_VOTOS)

# === 3. Filtros e Lógica da Interface ===
ufs = sorted(df["NM_UE"].dropna().unique())
if "BRASIL" not in ufs:
    ufs.insert(0, "BRASIL")
estado_selecionado = st.selectbox("🌎 Selecione o estado (ou BRASIL):", ufs)

if estado_selecionado != "BRASIL":
    df_estado = df[df["NM_UE"] == estado_selecionado]
else:
    df_estado = df.copy()

cargos = sorted(df_estado["DS_CARGO"].dropna().unique())
cargo_selecionado = st.selectbox("🔍 Selecione o cargo:", cargos)

candidatos = sorted(df_estado[df_estado["DS_CARGO"] == cargo_selecionado]["NM_CANDIDATO"].dropna().unique())
candidato_selecionado = st.selectbox("🔍 Selecione um candidato:", candidatos)

filtro_cand_base = df_estado[
    (df_estado["DS_CARGO"] == cargo_selecionado) &
    (df_estado["NM_CANDIDATO"] == candidato_selecionado)
]

if not filtro_cand_base.empty:
    sq_candidato_selecionado = filtro_cand_base["SQ_CANDIDATO"].iloc[0]
else:
    sq_candidato_selecionado = "N/A"

st.markdown(f"🔑 **SQ_CANDIDATO:** `{sq_candidato_selecionado}`")

# === 4. Agrupamentos e Cálculos Analíticos ===
df_zona = (
    filtro_cand_base.groupby(["code_meso", "name_meso"])
    .agg({
        "QT_VOTOS_NOMINAIS_VALIDOS": "sum",
        "latitude": "mean",
        "longitude": "mean"
    })
    .reset_index()
    .rename(columns={'QT_VOTOS_NOMINAIS_VALIDOS': 'VOTOS_CANDIDATO'})
)

df_total_meso = (
    df_estado
    .groupby(['code_meso', 'name_meso'], as_index=False)
    ['QT_VOTOS_NOMINAIS_VALIDOS'].sum()
    .rename(columns={'QT_VOTOS_NOMINAIS_VALIDOS': 'VOTOS_TOTAL_MESO'})
)

df_zona = df_zona.merge(df_total_meso, on=['code_meso', 'name_meso'], how='left')

votos_totais = 0

if not df_zona.empty:
    votos_totais = int(df_zona["VOTOS_CANDIDATO"].sum())
    df_zona["PERCENTUAL_TOTAL"] = (df_zona["VOTOS_CANDIDATO"] / votos_totais * 100).round(2)
    df_zona["PERCENTUAL_MESO"] = (df_zona["VOTOS_CANDIDATO"] / df_zona["VOTOS_TOTAL_MESO"] * 100).round(2)

    max_votos = df_zona["VOTOS_CANDIDATO"].max()
    min_votos = df_zona["VOTOS_CANDIDATO"].min()

    def gerar_cor(v):
        intensidade = int(255 * (v - min_votos) / (max_votos - min_votos)) if max_votos != min_votos else 128
        r = int(255 - 66 * (intensidade / 255))
        g = int(255 - 255 * (intensidade / 255))
        b = int(178 - 140 * (intensidade / 255))
        return [r, g, b]

    df_zona["color"] = df_zona["VOTOS_CANDIDATO"].apply(gerar_cor)

    layer = pdk.Layer(
        "ColumnLayer",
        data=df_zona,
        get_position='[longitude, latitude]',
        get_elevation="VOTOS_CANDIDATO",
        elevation_scale=10,
        radius=5000,
        get_fill_color="color",
        pickable=True,
        auto_highlight=True,
    )

    lat_mapa = df_zona["latitude"].mean() if not np.isnan(df_zona["latitude"].mean()) else -14.2350
    lon_mapa = df_zona["longitude"].mean() if not np.isnan(df_zona["longitude"].mean()) else -51.9253

    view_state = pdk.ViewState(
        latitude=lat_mapa,
        longitude=lon_mapa,
        zoom=4,
        pitch=45,
        bearing=0,
    )

    tooltip = {
        "html": "<b>Meso:</b> {code_meso}<br/><b>Nome:</b> {name_meso}<br/><b>Votos Candidato:</b> {VOTOS_CANDIDATO}<br/><b>Total Meso:</b> {VOTOS_TOTAL_MESO}",
        "style": {"color": "white"}
    }

    st.pydeck_chart(pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip,
        map_style="light"
    ))

    st.markdown("### 📋 Tabela de votos por mesorregião")
    st.write(f"**Total de votos para {candidato_selecionado}: {votos_totais:,}**")

    st.dataframe(
        df_zona[[
            "code_meso", "name_meso",
            "VOTOS_CANDIDATO", "VOTOS_TOTAL_MESO",
            "PERCENTUAL_TOTAL", "PERCENTUAL_MESO"
        ]].sort_values(by="VOTOS_CANDIDATO", ascending=False)
        .rename(columns={
            "VOTOS_CANDIDATO": "VOTOS CANDIDATO",
            "VOTOS_TOTAL_MESO": "VOTOS TOTAL MESO",
            "PERCENTUAL_TOTAL": "% TOTAL BRASIL",
            "PERCENTUAL_MESO": "% NA MESORREGIÃO"
        })
    )
else:
    st.warning("Nenhum dado de votação encontrado para os filtros selecionados.")

# === 5. Carregar Dados de Despesas ===
@st.cache_data
def carregar_despesas_s3(nome_arquivo):
    with st.spinner("Buscando dados de despesas no S3..."):
        try:
            objeto_s3 = s3_client.get_object(Bucket=BUCKET_NAME, Key=nome_arquivo)
            corpo_arquivo = objeto_s3["Body"].read().decode("latin1")
            
            df_amostra = pd.read_csv(StringIO(corpo_arquivo), nrows=1)
            df_amostra.columns = df_amostra.columns.str.strip().str.upper()
            colunas_necessarias = [col for col in df_amostra.columns if "DESPESA" in col or col == "SQ_CANDIDATO"]
            
            df = pd.read_csv(StringIO(corpo_arquivo), sep=",", usecols=lambda c: c.strip().upper() in colunas_necessarias)
            df.columns = df.columns.str.strip().str.upper()
            return df
        except Exception as e:
            st.error(f"❌ Erro ao baixar arquivo de despesas: {e}")
            return pd.DataFrame()

NOME_ARQUIVO_DESPESAS = "despesas_candidatos.csv"
df_despesas = carregar_despesas_s3(NOME_ARQUIVO_DESPESAS)

st.markdown("### 💸 Despesas do candidato")

if not df_despesas.empty and sq_candidato_selecionado != "N/A":
    df_despesas["SQ_CANDIDATO"] = df_despesas["SQ_CANDIDATO"].astype(str).str.strip()
    sq_candidato_str = str(sq_candidato_selecionado).strip()

    dados_despesa = df_despesas[df_despesas["SQ_CANDIDATO"] == sq_candidato_str]

    if not dados_despesa.empty:
        colunas_despesa = [col for col in dados_despesa.columns if "DESPESA" in col]
        total = float(dados_despesa["TOTAL_DESPESA"].values[0])
        gasto_por_voto = total / votos_totais if votos_totais > 0 else 0

        st.metric("💰 Total de despesas declaradas", f"R$ {total:,.2f}")
        st.metric("📊 Gasto por voto", f"R$ {gasto_por_voto:,.2f}")

        st.markdown("#### 🧾 Detalhamento das despesas")
        st.dataframe(
            dados_despesa[colunas_despesa]
            .T
            .rename(columns={dados_despesa.index[0]: "Valor (R$)"})
        )
    else:
        st.warning("🚫 Nenhuma despesa encontrada para este candidato.")
