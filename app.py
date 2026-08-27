import streamlit as st
import pandas as pd
import boto3

st.title("🕵️‍♂️ Capturador de Colunas (Modo Espião)")

# Conecta no S3 usando as credenciais que já estão no seu Streamlit Cloud
s3 = boto3.client('s3')
NOME_DO_BUCKET = 'ele-2022-brutos'

# Tenta ler nas pastas novas, se falhar, tenta na raiz
chaves_votacao = [
    'votacao/votacao_municipio_2022_BRASIL_com_coordenads_caracteristicas.csv',
    'votacao_municipio_2022_BRASIL_com_coordenads_caracteristicas.csv'
]
chaves_despesas = [
    'despesas/despesas_candidatos.csv',
    'despesas_candidatos.csv'
]

st.markdown("### 🗳️ Arquivo de Votação:")
for chave in chaves_votacao:
    try:
        obj = s3.get_object(Bucket=NOME_DO_BUCKET, Key=chave)
        df = pd.read_csv(obj['Body'], nrows=0, sep=None, engine='python')
        st.success(f"Encontrado em: {chave}")
        st.code(", ".join(df.columns))
        break
    except Exception:
        continue

st.markdown("### 💸 Arquivo de Despesas:")
for chave in chaves_despesas:
    try:
        obj = s3.get_object(Bucket=NOME_DO_BUCKET, Key=chave)
        df = pd.read_csv(obj['Body'], nrows=0, sep=None, engine='python')
        st.success(f"Encontrado em: {chave}")
        st.code(", ".join(df.columns))
        break
    except Exception:
        continue

st.stop()
