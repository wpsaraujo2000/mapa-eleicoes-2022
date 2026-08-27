import streamlit as st
import pandas as pd
import pydeck as pdk
import numpy as np

# === 1. Conexão com o AWS Athena ===
# O Streamlit vai ler as credenciais automaticamente do seu painel de Secrets
conn = st.connection("aws_athena", type="sql")

# Nome exato das tabelas que acabamos de criar na AWS
TABELA_VOTACAO = "eleicoes.votacao"
TABELA_DESPESAS = "eleicoes.despesas"

st.title("🗳️ Mapa de Votação por Mesorregião (2022)")

# === 2. Filtros Dinâmicos (Buscando direto da AWS Athena) ===
@st.cache_data(ttl=3600)
def obter_ufs():
    df_ufs = conn.query(f"SELECT DISTINCT NM_UE FROM {TABELA_VOTACAO} ORDER BY NM_UE")
    ufs = df_ufs["NM_UE"].dropna().tolist()
    if "BRASIL" not in ufs:
        ufs.insert(0, "BRASIL")
    return ufs

estado_selecionado = st.selectbox("🌎 Selecione o estado (ou BRASIL):", obter_ufs())

# Cria a regra para filtrar o estado (se for BRASIL, ignora o filtro)
where_uf = f"NM_UE = '{estado_selecionado}'" if estado_selecionado != "BRASIL" else "1=1"

@st.cache_data(ttl=3600)
def obter_cargos(where_clause):
    df_cargos = conn.query(f"SELECT DISTINCT DS_CARGO FROM {TABELA_VOTACAO} WHERE {where_clause} ORDER BY DS_CARGO")
    return df_cargos["DS_CARGO"].dropna().tolist()

cargo_selecionado = st.selectbox("🔍 Selecione o cargo:", obter_cargos(where_uf))

@st.cache_data(ttl=3600)
def obter_candidatos(where_clause, cargo):
    query = f"SELECT DISTINCT NM_CANDIDATO FROM {TABELA_VOTACAO} WHERE {where_clause} AND DS_CARGO = '{cargo}' ORDER BY NM_CANDIDATO"
    df_candidatos = conn.query(query)
    return df_candidatos["NM_CANDIDATO"].dropna().tolist()

candidato_selecionado = st.selectbox("🔍 Selecione um candidato:", obter_candidatos(where_uf, cargo_selecionado))

# Puxa o código do candidato (SQ_CANDIDATO)
query_sq = f"SELECT DISTINCT SQ_CANDIDATO FROM {TABELA_VOTACAO} WHERE {where_uf} AND DS_CARGO = '{cargo_selecionado}' AND NM_CANDIDATO = '{candidato_selecionado}' LIMIT 1"
df_sq = conn.query(query_sq)
sq_candidato_selecionado = df_sq.iloc[0]["SQ_CANDIDATO"] if not df_sq.empty else "N/A"

st.markdown(f"🔑 **SQ_CANDIDATO:** `{sq_candidato_selecionado}`")

# === 3. Consultas Analíticas (A Mágica do SQL Serverless na AWS) ===
# Agrupa os votos por mesorregião e tira a média da latitude/longitude
query_zona = f"""
    SELECT 
        code_meso, 
        name_meso, 
        SUM(QT_VOTOS_NOMINAIS_VALIDOS) as VOTOS_CANDIDATO,
        AVG(latitude) as latitude,
        AVG(longitude) as longitude
    FROM {TABELA_VOTACAO}
    WHERE {where_uf} 
      AND DS_CARGO = '{cargo_selecionado}' 
      AND NM_CANDIDATO = '{candidato_selecionado}'
    GROUP BY code_meso, name_meso
"""
df_zona = conn.query(query_zona, ttl=3600)

# Calcula o total de votos de todos os candidatos daquela meso para fazer o percentual
query_total_meso = f"""
    SELECT 
        code_meso, 
        name_meso, 
        SUM(QT_VOTOS_NOMINAIS_VALIDOS) as VOTOS_TOTAL_MESO
    FROM {TABELA_VOTACAO}
    WHERE {where_uf} 
      AND DS_CARGO = '{cargo_selecionado}'
    GROUP BY code_meso, name_meso
"""
df_total_meso = conn.query(query_total_meso, ttl=3600)

# === 4. Processamento Visual e PyDeck ===
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

    view_state = pdk.ViewState(
        latitude=df_zona["latitude"].mean(),
        longitude=df_zona["longitude"].mean(),
        zoom=7,
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
    votos_totais = 0
    st.warning("Não há votos registrados para este candidato nesta seleção.")

# === 5. Despesas do Candidato ===
st.markdown("### 💸 Despesas do candidato")

sq_candidato_str = str(sq_candidato_selecionado).strip()

# O Athena usa a função de conversão SQL padrão para tratar o texto
query_despesas = f"""
    SELECT * 
    FROM {TABELA_DESPESAS} 
    WHERE CAST(SQ_CANDIDATO AS VARCHAR) = '{sq_candidato_str}'
"""

dados_despesa = conn.query(query_despesas, ttl=3600)

if not dados_despesa.empty:
    # Padroniza as colunas para maiúsculo
    dados_despesa.columns = dados_despesa.columns.str.strip().str.upper()
    
    # Filtra colunas que tenham "DESPESA" no nome
    colunas_despesa = [col for col in dados_despesa.columns if "DESPESA" in col]
    
    # Tratamento caso o valor venha com formato diferente
    try:
        total = float(dados_despesa["TOTAL_DESPESA"].values[0])
    except ValueError:
        total = float(str(dados_despesa["TOTAL_DESPESA"].values[0]).replace(',', '.'))
        
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
    st.markdown(f"🔍 Código pesquisado: `{sq_candidato_str}`")
