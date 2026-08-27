import streamlit as st
import boto3

st.title("🕵️‍♂️ Novo Capturador (Agora apontando para o Secrets)")

# Pega as chaves exatamente de onde guardamos no Passo 2.2
chave_id = st.secrets["connections"]["aws_athena"]["AWS_ACCESS_KEY_ID"]
chave_secreta = st.secrets["connections"]["aws_athena"]["AWS_SECRET_ACCESS_KEY"]
regiao = st.secrets["connections"]["aws_athena"]["AWS_DEFAULT_REGION"]

# Cria o cliente S3 entregando as chaves na mão dele
s3 = boto3.client(
    's3',
    aws_access_key_id=chave_id,
    aws_secret_access_key=chave_secreta,
    region_name=regiao
)

NOME_DO_BUCKET = 'ele-2022-brutos'

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
