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

# === 1. Carregar dados de Votos Nativo (Sem smart_open) ===
@st.cache_data
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

    with st.spinner("Conectando à AWS e processando dados de votação..."):
        try:
            # Busca o objeto diretamente via API oficial da AWS
            objeto_s3 = s3_client.get_object(Bucket=BUCKET_NAME, Key=nome_arquivo)
            corpo_arquivo = objeto_s3["Body"].read().decode("utf-8")
            
            # Carrega na memória convertendo em string de dados do Pandas
            df = pd.read_csv(StringIO(corpo_arquivo), sep=",", usecols=colunas_para_ler, dtype=tipos_dados)
            df.columns = df.columns.str.strip()
            df = df.dropna(subset=["latitude", "longitude", "QT_VOTOS_NOMINAIS_VALIDOS"])
            return df
        except Exception as e:
            st.error(f"❌ Erro ao baixar arquivo de votos do S3: {e}")
            st.stop()

NOME_ARQUIVO_VOTOS = "votacao_municipio_2022_BRASIL_com_coordenads.csv"
df = carregar_dados_s3(NOME_ARQUIVO_VOTOS)

# === 2. Filtros e Lógica do App ===
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

# === 3. Carregar dados de Despesas Nativo ===
@st.cache_data
def carregar_despesas_s3(nome_arquivo):
    with st.spinner("Buscando dados de despesas no S3..."):
        try:
            objeto_s3 = s3_client.get_object(Bucket=BUCKET_NAME, Key=nome_arquivo)
            corpo_arquivo = objeto_s3["Body"].read().decode("latin1")
            
            # Carrega apenas as colunas necessárias para economizar memória RAM
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
