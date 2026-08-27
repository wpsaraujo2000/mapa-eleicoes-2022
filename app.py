import streamlit as st
import boto3

st.title("🕵️‍♂️ Novo Capturador (À Prova de Falhas)")

# Conecta no S3 
s3 = boto3.client('s3')
NOME_DO_BUCKET = 'ele-2022-brutos'

chaves_votacao = [
    'votacao_municipio_2022_BRASIL_com_coordenads_caracteristicas.csv',
    'votacao/votacao_municipio_2022_BRASIL_com_coordenads_caracteristicas.csv'
]

chaves_despesas = [
    'despesas_candidatos.csv',
    'despesas/despesas_candidatos.csv'
]

st.markdown("### 🗳️ Votação:")
for chave in chaves_votacao:
    try:
        # Range='bytes=0-1000' pega só o comecinho do arquivo. Impossível dar falta de memória.
        obj = s3.get_object(Bucket=NOME_DO_BUCKET, Key=chave, Range='bytes=0-1000')
        texto = obj['Body'].read().decode('utf-8', errors='ignore') # Ignora erros de acento
        primeira_linha = texto.split('\n')[0]
        st.success(f"SUCESSO! Lendo: {chave}")
        st.code(primeira_linha)
        break
    except Exception as e:
        st.error(f"Erro em {chave}: {e}")

st.markdown("### 💸 Despesas:")
for chave in chaves_despesas:
    try:
        obj = s3.get_object(Bucket=NOME_DO_BUCKET, Key=chave, Range='bytes=0-1000')
        texto = obj['Body'].read().decode('utf-8', errors='ignore')
        primeira_linha = texto.split('\n')[0]
        st.success(f"SUCESSO! Lendo: {chave}")
        st.code(primeira_linha)
        break
    except Exception as e:
        st.error(f"Erro em {chave}: {e}")
