import streamlit as st
import boto3

st.title("🕵️‍♂️ Novo Capturador (À Prova de Falhas)")

s3 = boto3.client('s3')
NOME_DO_BUCKET = 'ele-2022-brutos'

# Exatamente os caminhos com as pastas que você criou!
chave_votacao = 'votacao/votacao_municipio_2022_BRASIL_com_coordenads_caracteristicas.csv'
chave_despesas = 'despesas/despesas_candidatos.csv'

st.markdown("### 🗳️ Votação:")
try:
    obj = s3.get_object(Bucket=NOME_DO_BUCKET, Key=chave_votacao, Range='bytes=0-1000')
    texto = obj['Body'].read().decode('utf-8', errors='ignore')
    primeira_linha = texto.split('\n')[0]
    st.success(f"SUCESSO! Lendo a pasta votacao...")
    st.code(primeira_linha)
except Exception as e:
    st.error(f"Erro ao ler Votação: {e}")

st.markdown("### 💸 Despesas:")
try:
    obj = s3.get_object(Bucket=NOME_DO_BUCKET, Key=chave_despesas, Range='bytes=0-1000')
    texto = obj['Body'].read().decode('utf-8', errors='ignore')
    primeira_linha = texto.split('\n')[0]
    st.success(f"SUCESSO! Lendo a pasta despesas...")
    st.code(primeira_linha)
except Exception as e:
    st.error(f"Erro ao ler Despesas: {e}")
