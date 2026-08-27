import streamlit as st
from pyathena import connect

st.title("🔍 Diagnóstico do Athena")

try:
    # 1. Pega as credenciais
    chave_id = st.secrets["connections"]["aws_athena"]["AWS_ACCESS_KEY_ID"]
    chave_secreta = st.secrets["connections"]["aws_athena"]["AWS_SECRET_ACCESS_KEY"]
    
    # Pasta onde o Athena salva os resultados
    pasta_resultados = "s3://ele-2022-brutos/resultados-athena/" 
    regiao = "us-east-2"

    st.write("⏳ Conectando à AWS...")
    
    # 2. Conecta diretamente usando PyAthena
    conn = connect(
        aws_access_key_id=chave_id,
        aws_secret_access_key=chave_secreta,
        s3_staging_dir=pasta_resultados,
        region_name=regiao
    )

    cursor = conn.cursor()
    
    st.write("⏳ Rodando consulta de teste na tabela de votação...")
    # Tenta rodar a mesma consulta que está dando erro no seu app
    cursor.execute("SELECT DISTINCT NM_UE FROM eleicoes.votacao ORDER BY NM_UE LIMIT 5")
    
    resultados = cursor.fetchall()
    st.success("✅ Conexão perfeita! Consulta executada com sucesso.")
    st.write(resultados)

except Exception as e:
    st.error("🚨 O erro real bloqueando o aplicativo é:")
    st.code(str(e))
