import streamlit as st
import pandas as pd
import pydeck as pdk
import numpy as np
from pyathena import connect

# === 1. Conexão com o AWS Athena ===
# Criamos uma conexão direta que imita a facilidade do BigQuery
@st.cache_resource
def conectar_aws():
    return connect(
        aws_access_key_id=st.secrets["connections"]["aws_athena"]["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["connections"]["aws_athena"]["AWS_SECRET_ACCESS_KEY"],
        s3_staging_dir="s3://ele-2022-brutos/resultados-athena/",
        region_name="us-east-2"
    )

# Função mágica que faz o Athena se comportar igual ao BigQuery (conn.query)
@st.cache_data(ttl=3600)
def query_aws(query_str):
    conn = conectar_aws()
    cursor = conn.cursor()
    cursor.execute(query_str)
    colunas = [desc[0].upper() for desc in cursor.description] # Força colunas em MAIÚSCULO
    df = pd.DataFrame(cursor.fetchall(), columns=colunas)
    return df

TABELA = "eleicoes.votacao"
TABELA_DESPESAS = "eleicoes.despesas"

st.title("🗳️ Mapa de Votação por Mesorregião (2022)")

# === 2. Filtros Dinâmicos ===
@st.cache_data(ttl=3600)
def obter_ufs():
    df_ufs = query_aws(f"SELECT DISTINCT NM_UE FROM {TABELA} ORDER BY NM_UE")
    ufs = df_ufs["NM_UE"].dropna().tolist()
    if "BRASIL" not in ufs:
        ufs.insert(0, "BRASIL")
    return ufs

estado_selecionado = st.selectbox("🌎 Selecione o estado (ou BRASIL):", obter_ufs())

where_uf = f"NM_UE = '{estado_selecionado}'" if estado_selecionado != "BRASIL" else "1=1"

@st.cache_data(ttl=3600)
def obter_cargos(where_clause):
    df_cargos = query_aws(f"SELECT DISTINCT DS_CARGO FROM {TABELA} WHERE {where_clause} ORDER BY DS_CARGO")
    return df_cargos["DS_CARGO"].dropna().tolist()

cargo_selecionado = st.selectbox("🔍 Selecione o cargo:", obter_cargos(where_uf))

@st.cache_data(ttl=3600)
def obter_candidatos(where_clause, cargo):
    query = f"SELECT DISTINCT NM_CANDIDATO FROM {TABELA} WHERE {where_clause} AND DS_CARGO = '{cargo}' ORDER BY NM_CANDIDATO"
    df_candidatos = query_aws(query)
    return df_candidatos["NM_CANDIDATO"].dropna().tolist()

candidato_selecionado = st.selectbox("🔍 Selecione um candidato:", obter_candidatos(where_uf, cargo_selecionado))

query_sq = f"SELECT DISTINCT SQ_CANDIDATO FROM {TABELA} WHERE {where_uf} AND DS_CARGO = '{cargo_selecionado}' AND NM_CANDIDATO = '{candidato_selecionado}' LIMIT 1"
df_sq = query_aws(query_sq)
sq_candidato_selecionado = df_sq.iloc[0]["SQ_CANDIDATO"] if not df_sq.empty else "N/A"

st.markdown(f"🔑 **SQ_CANDIDATO:** `{sq_candidato_selecionado}`")

# === 3. Consultas Analíticas ===
query_zona = f"""
    SELECT 
        code_meso, 
        name_meso, 
        SUM(CAST(QT_VOTOS_NOMINAIS_VALIDOS AS DOUBLE)) as VOTOS_CANDIDATO,
        AVG(CAST(latitude AS DOUBLE)) as latitude,
        AVG(CAST(longitude AS DOUBLE)) as longitude
    FROM {TABELA}
    WHERE {where_uf} 
      AND DS_CARGO = '{cargo_selecionado}' 
      AND NM_CANDIDATO = '{candidato_selecionado}'
    GROUP BY code_meso, name_meso
"""
df_zona = query_aws(query_zona)

query_total_meso = f"""
    SELECT 
        code_meso, 
        name_meso, 
        SUM(CAST(QT_VOTOS_NOMINAIS_VALIDOS AS DOUBLE)) as VOTOS_TOTAL_MESO
    FROM {TABELA}
    WHERE {where_uf} 
      AND DS_CARGO = '{cargo_selecionado}'
    GROUP BY code_meso, name_meso
"""
df_total_meso = query_aws(query_total_meso)

# === 4. Processamento Visual e PyDeck ===
if not df_zona.empty:
    df_zona = df_zona.merge(df_total_meso, on=['CODE_MESO', 'NAME_MESO'], how='left')

    # PROTEÇÃO: Garante que os votos são números, mesmo que a AWS envie sujeira
    df_zona["VOTOS_CANDIDATO"] = pd.to_numeric(df_zona["VOTOS_CANDIDATO"], errors='coerce').fillna(0)
    df_zona["VOTOS_TOTAL_MESO"] = pd.to_numeric(df_zona["VOTOS_TOTAL_MESO"], errors='coerce').fillna(0)

    votos_totais = int(df_zona["VOTOS_CANDIDATO"].sum())
    df_zona["PERCENTUAL_TOTAL"] = (df_zona["VOTOS_CANDIDATO"] / votos_totais * 100).round(2) if votos_totais > 0 else 0
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
        get_position='[LONGITUDE, LATITUDE]',
        get_elevation="VOTOS_CANDIDATO",
        elevation_scale=10,
        radius=5000,
        get_fill_color="color",
        pickable=True,
        auto_highlight=True,
    )

    view_state = pdk.ViewState(
        latitude=df_zona["LATITUDE"].mean(),
        longitude=df_zona["LONGITUDE"].mean(),
        zoom=7,
        pitch=45,
        bearing=0,
    )

    tooltip = {
        "html": "<b>Meso:</b> {CODE_MESO}<br/><b>Nome:</b> {NAME_MESO}<br/><b>Votos Candidato:</b> {VOTOS_CANDIDATO}<br/><b>Total Meso:</b> {VOTOS_TOTAL_MESO}",
        "style": {"color": "white"}
    }

    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip, map_style="light"))

    st.markdown("### 📋 Tabela de votos por mesorregião")
    st.write(f"**Total de votos para {candidato_selecionado}: {votos_totais:,}**")

    st.dataframe(
        df_zona[[
            "CODE_MESO", "NAME_MESO",
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
    votos_totais = 0
    st.warning("Não há votos registrados para este candidato nesta seleção.")

# === 5. Despesas do Candidato ===
st.markdown("### 💸 Despesas do candidato")
sq_candidato_str = str(sq_candidato_selecionado).strip()

query_despesas = f"""
    SELECT * 
    FROM {TABELA_DESPESAS} 
    WHERE CAST(SQ_CANDIDATO AS STRING) = '{sq_candidato_str}'
"""

dados_despesa = query_aws(query_despesas)

if not dados_despesa.empty:
    dados_despesa.columns = dados_despesa.columns.str.strip().str.upper()
    colunas_despesa = [col for col in dados_despesa.columns if "DESPESA" in col]
    
    try:
        total = float(dados_despesa["TOTAL_DESPESA"].values[0])
    except ValueError:
        total = float(str(dados_despesa["TOTAL_DESPESA"].values[0]).replace(',', '.'))
        
    gasto_por_voto = total / votos_totais if votos_totais > 0 else 0

    st.metric("💰 Total de despesas declaradas", f"R$ {total:,.2f}")
    st.metric("📊 Gasto por voto", f"R$ {gasto_por_voto:,.2f}")

    st.markdown("#### 🧾 Detalhamento das despesas")
    st.dataframe(dados_despesa[colunas_despesa].T.rename(columns={dados_despesa.index[0]: "Valor (R$)"}))
else:
    st.warning("🚫 Nenhuma despesa encontrada para este candidato.")
