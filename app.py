import os
import streamlit as st
import pandas as pd
import pydeck as pdk
import numpy as np
import boto3
from smart_open import open as s3_open
from dotenv import load_dotenv

# Carrega chaves locais se existiren (para desenvolvimento local)
load_dotenv()

st.title("🗳️ Mapa de Votação por Mesorregião (2022)")

# === Configuração de Acesso AWS S3 ===
AWS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REG = os.getenv("AWS_REGION", "us-east-2")
BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")

if not AWS_KEY or not AWS_SECRET or not BUCKET_NAME:
    st.error("❌ Credenciais da AWS S3 não encontradas. Configure as Advanced Settings -> Secrets no Streamlit Cloud.")
    st.stop()

# === Função auxiliar para ler direto do S3 ===
def abrir_arquivo_s3(nome_arquivo, encoding="utf-8"):
    try:
        session = boto3.Session(
            aws_access_key_id=AWS_KEY,
            aws_secret_access_key=AWS_SECRET,
            region_name=AWS_REG
        )
        uri = f"s3://{BUCKET_NAME}/{nome_arquivo}"
        return s3_open(uri, mode="r", encoding=encoding, transport_params={"client": session.client("s3")})
    except Exception as e:
        st.error(f"❌ Erro de conexão com o S3: {e}")
        st.stop()

# === 1. Carregar dados ===
@st.cache_data
def carregar_dados(nome_arquivo):
    with st.spinner("Baixando e processando base de votação do S3 (isso pode levar um momento)..."):
        with abrir_arquivo_s3(nome_arquivo, encoding="utf-8") as f:
            df = pd.read_csv(f, sep=",")

        primeira_coluna = df.columns[0]
        if "Unnamed" in primeira_coluna or primeira_coluna.strip().isdigit():
            df = df.drop(columns=[primeira_coluna])

        df.columns = df.columns.str.strip()

        colunas_necessarias = ["latitude", "longitude", "QT_VOTOS_NOMINAIS_VALIDOS"]
        faltando = [col for col in colunas_necessarias if col not in df.columns]
        if faltando:
            st.error(f"❌ Colunas ausentes no arquivo: {faltando}")
            st.stop()

        df = df.dropna(subset=colunas_necessarias)
        return df

NOME_ARQUIVO_VOTOS = "votacao_municipio_2022_BRASIL_com_coordenads.csv"
df = carregar_dados(NOME_ARQUIVO_VOTOS)

# === 2. Filtros ===
ufs = sorted(df["NM_UE"].dropna().unique())
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

# Seleção segura do código do candidato
filtro_cand = df_estado[
    (df_estado["DS_CARGO"] == cargo_selecionado) &
    (df_estado["NM_CANDIDATO"] == candidato_selecionado)
]

if not filtro_cand.empty:
    sq_candidato_selecionado = filtro_cand["SQ_CANDIDATO"].iloc[0]
else:
    sq_candidato_selecionado = "N/A"

st.markdown(f"🔑 **SQ_CANDIDATO:** `{sq_candidato_selecionado}`")

# === 3. Agrupamentos e Cálculos ===
df_zona = (
    filtro_cand.groupby(["code_meso", "name_meso"])
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

votos_totais = 0

if not df_zona.empty:
    df_zona = df_zona.merge(df_total_meso, on=['code_meso', 'name_meso'], how='left')

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

    # Evita quebras caso lat/lon venham vazios ou NaN
    lat_centro = df_zona["latitude"].mean() if not np.isnan(df_zona["latitude"].mean()) else -14.2350
    lon_centro = df_zona["longitude"].mean() if not np.isnan(df_zona["longitude"].mean()) else -51.9253

    view_state = pdk.ViewState(
        latitude=lat_centro,
        longitude=lon_centro,
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

# === 4. Carregar Despesas ===
@st.cache_data
def carregar_despesas(nome_arquivo):
    with st.spinner("Buscando dados de despesas no S3..."):
        with abrir_arquivo_s3(nome_arquivo, encoding="latin1") as f:
            df = pd.read_csv(f, sep=",")
        df.columns = df.columns.str.strip().str.upper()
        return df

NOME_ARQUIVO_DESPESAS = "despesas_candidatos.csv"
df_despesas = carregar_despesas(NOME_ARQUIVO_DESPESAS)

st.markdown("### 💸 Despesas do candidato")

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
