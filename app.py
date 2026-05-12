import streamlit as st
import pandas as pd
import psycopg2
from psycopg2 import extras
import google.generativeai as genai
import tempfile
import os
import re
import plotly.express as px
from datetime import datetime
import bcrypt
import warnings
warnings.filterwarnings('ignore')

# ===============================================
# CONFIGURAÇÃO DE PÁGINA
# ===============================================
st.set_page_config(page_title="ERP Semprexpressivo Cloud", layout="wide", page_icon="🏢")

# ===============================================
# CONEXÃO BLINDADA (Anti-Quedas)
# ===============================================
@st.cache_resource(ttl=60)
def get_connection():
    try:
        conn = psycopg2.connect(st.secrets["DATABASE_URL"], connect_timeout=3)
        return conn
    except Exception as e:
        return None

def run_query(query, params=None, fetch=False):
    conn = get_connection()
    if not conn: 
        st.error("A religar ao servidor... tente novamente num segundo.")
        return None
    try:
        with conn.cursor(cursor_factory=extras.DictCursor) as cur:
            cur.execute(query, params)
            if fetch:
                res = cur.fetchall()
                return res
            conn.commit()
    except Exception as e:
        st.cache_resource.clear()
        conn.rollback()
    return None

@st.cache_resource
def init_db():
    queries = [
        "CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nome TEXT UNIQUE, senha TEXT, perfil TEXT)",
        "CREATE TABLE IF NOT EXISTS clientes (id SERIAL PRIMARY KEY, nome TEXT UNIQUE, pais TEXT, responsavel TEXT, email TEXT, prazo_pagamento TEXT)",
        "CREATE TABLE IF NOT EXISTS pastas_personalizadas (id SERIAL PRIMARY KEY, nome TEXT UNIQUE)",
        "CREATE TABLE IF NOT EXISTS despesas (id SERIAL PRIMARY KEY, data DATE, fornecedor TEXT, centro_custo TEXT, valor NUMERIC, iva NUMERIC, categoria TEXT, tipo_custo TEXT, link_ficheiro TEXT, num_fatura TEXT, status TEXT, criado_por TEXT)",
        "CREATE TABLE IF NOT EXISTS receitas (id SERIAL PRIMARY KEY, data DATE, cliente TEXT, valor NUMERIC, iva NUMERIC, categoria TEXT, link_ficheiro TEXT, status TEXT, criado_por TEXT)",
        "CREATE TABLE IF NOT EXISTS socio_movimentos (id SERIAL PRIMARY KEY, data DATE, tipo TEXT, valor NUMERIC, descricao TEXT, usuario TEXT)"
    ]
    for q in queries: run_query(q)
    
    run_query("DELETE FROM usuarios")
    
    acessos = [("Leonidas Castilho", "123456", "Admin"), ("Gracielle Malvestio", "123456", "Admin"), 
               ("Fabio de Freitas", "123456", "Admin"), ("Johnny D´Paula", "123456", "Admin"), ("Carlos Matos", "123456", "Admin")]
    
    for nome, senha, perfil in acessos:
        salt = bcrypt.gensalt()
        hash_senha = bcrypt.hashpw(senha.encode('utf-8'), salt).decode('utf-8')
        run_query("INSERT INTO usuarios (nome, senha, perfil) VALUES (%s, %s, %s)", (nome, hash_senha, perfil))

init_db()

# ===============================================
# LOGIN E SESSÃO (Criptografia Ativa)
# ===============================================
if 'autenticado' not in st.session_state: st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.markdown("<br><br><h1 style='text-align: center;'>🏢 ERP Semprexpressivo Cloud</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        with st.container(border=True):
            user = st.selectbox("Utilizador", ["Leonidas Castilho", "Gracielle Malvestio", "Fabio de Freitas", "Johnny D´Paula", "Carlos Matos"])
            pw = st.text_input("Palavra-passe", type="password")
            if st.button("Entrar", use_container_width=True, type="primary"):
                res = run_query("SELECT nome, senha FROM usuarios WHERE nome=%s", (user,), fetch=True)
                if res:
                    hash_no_banco = res[0][1].encode('utf-8')
                    if bcrypt.checkpw(pw.encode('utf-8'), hash_no_banco):
                        st.session_state.autenticado = True
                        st.session_state.usuario_nome = user
                        st.rerun()
                    else: st.error("Acesso negado. Palavra-passe incorreta.")
                else: st.error("Acesso negado. Palavra-passe incorreta.")
    st.stop()

# ===============================================
# UTILITÁRIOS & CACHE DE DADOS (MEMÓRIA TURBO)
# ===============================================
CATEGORIAS_BASE = ["Salários/Folha", "Segurança Social", "Finanças (IVA/IRC)", "Viagens", "Hospedagem/Alojamento", "Alimentação", "Combustível", "Portagens", "Manutenção/Oficina", "Materiais/Ferramentas", "Contabilidade", "Seguros", "Telecomunicações/Internet", "Água/Luz/Gás", "Outros"]

@st.cache_data(ttl=300)
def obter_todas_pastas():
    res = run_query("SELECT nome FROM pastas_personalizadas", fetch=True)
    return CATEGORIAS_BASE + [r[0] for r in res] if res else CATEGORIAS_BASE

@st.cache_data(ttl=300)
def obter_clientes():
    res = run_query("SELECT nome FROM clientes ORDER BY nome", fetch=True)
    return [r[0] for r in res] if res else []

@st.cache_data(ttl=60)
def obter_dados_dashboard(mes_at):
    conn = get_connection()
    df_evol = pd.read_sql_query("SELECT TO_CHAR(data, 'YYYY-MM') as mes, 'Receita' as tipo, SUM(valor) as total FROM receitas WHERE status='Pago' GROUP BY mes UNION ALL SELECT TO_CHAR(data, 'YYYY-MM') as mes, 'Despesa' as tipo, SUM(valor) as total FROM despesas WHERE status='Pago' GROUP BY mes", conn)
    df_pie = pd.read_sql_query("SELECT categoria, SUM(valor) as total FROM despesas WHERE status='Pago' GROUP BY categoria", conn)
    df_list = pd.read_sql_query("SELECT id, data, fornecedor, centro_custo, valor, iva, status FROM despesas ORDER BY status DESC, data DESC LIMIT 15", conn)
    return df_evol, df_pie, df_list

@st.cache_data(ttl=60)
def obter_dados_pastas(pasta):
    return pd.read_sql_query(f"SELECT data, fornecedor, valor FROM despesas WHERE categoria='{pasta}'", get_connection())

def formatar_moeda(valor):
    v = float(valor) if valor else 0.0
    return f"{v:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.')

def extrair_valor_ia(texto):
    if not texto: return 0.0
    numeros = re.findall(r'\d+[.,\d]*', str(texto))
    if numeros:
        n = numeros[-1].replace(',', '.')
        if n.count('.') > 1: n = n.replace('.', '', n.count('.') - 1)
        try: return float(n)
        except: return 0.0
    return 0.0

def limpar_memoria():
    st.cache_data.clear()

# ===============================================
# MENU LATERAL
# ===============================================
st.sidebar.title("🏢 ERP Nuvem")
st.sidebar.markdown(f"👤 Sessão: **{st.session_state.usuario_nome}**")
st.sidebar.markdown("---")

try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except: st.sidebar.error("⚠️ Chave Google em falta!")

if 'menu' not in st.session_state: st.session_state.menu = "Dashboard"

if st.sidebar.button("📊 Dashboard Financeiro", use_container_width=True): st.session_state.menu = "Dashboard"
if st.sidebar.button("📈 Relatórios / DRE", use_container_width=True): st.session_state.menu = "Relatorios"
if st.sidebar.button("🧑‍💼 Conta Pessoal Fábio", use_container_width=True): st.session_state.menu = "Socio"
if st.sidebar.button("👥 Clientes (C. Custos)", use_container_width=True): st.session_state.menu = "Clientes"
if st.sidebar.button("📥 Registar Despesa", use_container_width=True): st.session_state.menu = "Faturas"
if st.sidebar.button("💰 Registar Receita", use_container_width=True): st.session_state.menu = "Receitas"
if st.sidebar.button("📂 Explorador de Pastas", use_container_width=True): st.session_state.menu = "Pastas"
if st.sidebar.button("⚙️ Perfil e Segurança", use_container_width=True): st.session_state.menu = "Perfil"

st.sidebar.markdown("---")
if st.sidebar.button("🚪 Terminar Sessão", type="primary", use_container_width=True):
    st.session_state.autenticado = False
    st.rerun()

# ===============================================
# GESTÃO DE PERFIL E SENHAS
# ===============================================
if st.session_state.menu == "Perfil":
    st.title("⚙️ O Meu Perfil e Segurança")
    
    with st.container(border=True):
        st.subheader("🔑 Alterar a minha Palavra-passe")
        st.write(f"Você está a alterar a senha da conta: **{st.session_state.usuario_nome}**")
        
        with st.form("form_senha"):
            c1, c2, c3 = st.columns(3)
            senha_atual = c1.text_input("Palavra-passe Atual", type="password")
            nova_senha = c2.text_input("Nova Palavra-passe", type="password")
            confirma_senha = c3.text_input("Confirmar Nova Palavra-passe", type="password")
            
            if st.form_submit_button("Atualizar Palavra-passe", use_container_width=True):
                res = run_query("SELECT id, senha FROM usuarios WHERE nome=%s", (st.session_state.usuario_nome,), fetch=True)
                if not res or not bcrypt.checkpw(senha_atual.encode('utf-8'), res[0][1].encode('utf-8')):
                    st.error("A Palavra-passe Atual está incorreta.")
                elif nova_senha != confirma_senha:
                    st.error("As novas palavras-passe não coincidem!")
                elif len(nova_senha) < 4:
                    st.error("A nova palavra-passe deve ter pelo menos 4 caracteres.")
                else:
                    nova_hash = bcrypt.hashpw(nova_senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    run_query("UPDATE usuarios SET senha=%s WHERE nome=%s", (nova_hash, st.session_state.usuario_nome))
                    st.success("✅ Palavra-passe alterada com segurança máxima!")
                    
    st.write("---")
    st.subheader("👥 Equipa com Acesso ao Sistema")
    df_users = pd.read_sql_query("SELECT nome as Nome, perfil as Perfil FROM usuarios ORDER BY nome", get_connection())
    if not df_users.empty:
        st.dataframe(df_users, use_container_width=True, hide_index=True)

# ===============================================
# DASHBOARD CLOUD
# ===============================================
elif st.session_state.menu == "Dashboard":
    st.title("📊 Painel de Controlo (Dados na Nuvem)")
    
    t_rec = run_query("SELECT SUM(valor) FROM receitas WHERE status='Pago'", fetch=True)
    t_rec = t_rec[0][0] if t_rec and t_rec[0][0] else 0
    t_pago = run_query("SELECT SUM(valor) FROM despesas WHERE status='Pago'", fetch=True)
    t_pago = t_pago[0][0] if t_pago and t_pago[0][0] else 0
    t_pend = run_query("SELECT SUM(valor) FROM despesas WHERE status='Pendente'", fetch=True)
    t_pend = t_pend[0][0] if t_pend and t_pend[0][0] else 0
    
    mes_at = datetime.now().strftime('%Y-%m')
    iva_s = run_query(f"SELECT SUM(iva) FROM despesas WHERE TO_CHAR(data, 'YYYY-MM') = '{mes_at}'", fetch=True)
    iva_s = iva_s[0][0] if iva_s and iva_s[0][0] else 0
    iva_l = run_query(f"SELECT SUM(iva) FROM receitas WHERE TO_CHAR(data, 'YYYY-MM') = '{mes_at}'", fetch=True)
    iva_l = iva_l[0][0] if iva_l and iva_l[0][0] else 0

    with st.container(border=True):
        st.subheader("📈 Visão Global de Caixa")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 Faturado", formatar_moeda(t_rec))
        c2.metric("💸 Total Pago", formatar_moeda(t_pago), delta_color="inverse")
        c3.metric("💶 Saldo Caixa", formatar_moeda(t_rec - t_pago), delta="Lucro" if (t_rec-t_pago)>=0 else "Prejuízo")
        c4.metric("⏳ A Pagar", formatar_moeda(t_pend), delta_color="inverse")

    with st.container(border=True):
        st.subheader(f"⚖️ Balanço IVA ({mes_at})")
        ci1, ci2, ci3 = st.columns(3)
        ci1.metric("IVA Suportado (Compras)", formatar_moeda(iva_s))
        ci2.metric("IVA Liquidado (Vendas)", formatar_moeda(iva_l), delta_color="inverse")
        ci3.metric("Saldo IVA", formatar_moeda(iva_s - iva_l), delta="A Recuperar" if (iva_s - iva_l) > 0 else "A Pagar")

    df_evol, df_pie, df_list = obter_dados_dashboard(mes_at)

    st.write("")
    col_g1, col_g2 = st.columns([2, 1])
    with col_g1:
        st.subheader("Evolução Mensal")
        if not df_evol.empty: st.plotly_chart(px.bar(df_evol.sort_values('mes'), x='mes', y='total', color='tipo', barmode='group'), use_container_width=True)
    with col_g2:
        st.subheader("Distribuição Despesas")
        if not df_pie.empty: st.plotly_chart(px.pie(df_pie, values='total', names='categoria', hole=0.4), use_container_width=True)
    
    st.subheader("🧾 Contas a Pagar (Despesas)")
    if not df_list.empty:
        df_list['valor'] = df_list['valor'].apply(formatar_moeda)
        df_list['iva'] = df_list['iva'].apply(formatar_moeda)
        st.dataframe(df_list, use_container_width=True, hide_index=True)
    else: st.info("Sem despesas registadas.")

# ===============================================
# REGISTAR DESPESA (IA MILITAR)
# ===============================================
elif st.session_state.menu == "Faturas":
    st.title("📥 Registar Despesa (Cloud)")
    clis = obter_clientes()
    pasts = obter_todas_pastas()
    
    t_ia, t_man = st.tabs(["🤖 Leitura Automática (IA)", "✍️ Registo Manual"])
    with t_ia:
        up = st.file_uploader("Arraste a Fatura da Despesa", type=['png', 'jpg', 'pdf'])
        if up:
            with st.spinner("🤖 IA a ler o documento... aguarde..."):
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{up.name.split('.')[-1]}") as tmp:
                    tmp.write(up.getvalue()); t_path = tmp.name
                
                modelo = genai.GenerativeModel('gemini-2.5-flash')
                # ORDEM MILITAR PARA A IA
                prompt_desp = f"Aja como um robô extrator de dados. Analise a fatura e responda APENAS com 6 valores separados pelo símbolo |. Sem texto adicional. Formato: Fornecedor | Data(YYYY-MM-DD) | Valor Total | Valor IVA | Categoria | Nº Fatura. Categorias válidas: {pasts}. Exemplo de resposta perfeita: Galp | 2024-05-10 | 50.00 | 11.50 | Combustível | FT123"
                res = modelo.generate_content([genai.upload_file(t_path), prompt_desp])
                
                # Corta a resposta pelas barras |
                dados = res.text.replace('**', '').strip().split('|')
                
                # Garantir que a lista tem 6 espaços mesmo se a IA falhar
                while len(dados) < 6: dados.append("")
                
                with st.form("f_ia"):
                    c1, c2, c3 = st.columns(3)
                    f_forn = c1.text_input("Fornecedor", dados[0].strip())
                    f_dat = c2.text_input("Data", dados[1].strip())
                    f_num = c3.text_input("Nº Fatura", dados[5].strip())
                    
                    c4, c5, c6, c7 = st.columns(4)
                    f_val = c4.number_input("Valor Total (€)", value=extrair_valor_ia(dados[2]))
                    f_iva = c5.number_input("IVA (€)", value=extrair_valor_ia(dados[3]))
                    f_stat = c6.selectbox("Status", ["Pendente", "Pago"])
                    f_cc = c7.selectbox("Centro Custo", ["Sede"] + clis)
                    
                    if st.form_submit_button("Guardar Despesa na Nuvem", use_container_width=True):
                        run_query("INSERT INTO despesas (data, fornecedor, num_fatura, valor, iva, status, centro_custo, criado_por) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                                  (f_dat, f_forn, f_num, f_val, f_iva, f_stat, f_cc, st.session_state.usuario_nome))
                        st.success("Despesa Guardada no Supabase!")
                        limpar_memoria() 
                        st.rerun()

    with t_man:
        with st.form("f_man_desp"):
            c1, c2, c3 = st.columns(3); fm = c1.text_input("Fornecedor"); dm = c2.date_input("Data"); nm = c3.text_input("Nº Fatura", "S/N")
            c4, c5, c6, c7 = st.columns(4); vm = c4.number_input("Valor (€)"); im = c5.number_input("IVA (€)")
            cm = c6.selectbox("Centro Custo", ["Sede"] + clis); sm = c7.selectbox("Status", ["Pago", "Pendente"])
            if st.form_submit_button("Registar Despesa Manual", use_container_width=True):
                run_query("INSERT INTO despesas (data, fornecedor, num_fatura, valor, iva, status, centro_custo, criado_por) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", 
                          (str(dm), fm, nm, vm, im, sm, cm, st.session_state.usuario_nome))
                st.success("Registado!")
                limpar_memoria()
                st.rerun()

# ===============================================
# REGISTAR RECEITA (IA MILITAR)
# ===============================================
elif st.session_state.menu == "Receitas":
    st.title("💰 Registar Faturação (Receitas)")
    clis = obter_clientes()
    t_ia_rec, t_man_rec = st.tabs(["🤖 Leitura Automática (IA)", "✍️ Registo Manual"])
    
    with t_ia_rec:
        up_r = st.file_uploader("Arraste a Fatura Emitida", type=['png', 'jpg', 'pdf'])
        if up_r:
            with st.spinner("🤖 IA a processar documento... aguarde..."):
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{up_r.name.split('.')[-1]}") as tmp:
                    tmp.write(up_r.getvalue()); t_path = tmp.name
                
                modelo = genai.GenerativeModel('gemini-2.5-flash')
                # ORDEM MILITAR PARA A IA
                prompt_rec = "Aja como um robô extrator de dados. Analise a fatura e responda APENAS com 4 valores separados pelo símbolo |. Sem texto adicional. Formato: Cliente | Data(YYYY-MM-DD) | Valor Total | Valor IVA. Exemplo perfeito: Empresa XYZ | 2024-05-10 | 1500.00 | 345.00"
                res = modelo.generate_content([genai.upload_file(t_path), prompt_rec])
                
                # Corta a resposta pelas barras |
                dados = res.text.replace('**', '').strip().split('|')
                
                # Garantir que a lista tem 4 espaços mesmo se a IA falhar
                while len(dados) < 4: dados.append("")
                
                with st.form("f_ia_rec"):
                    c1, c2 = st.columns(2)
                    c_ia = c1.text_input("Cliente (Lido pela IA)", dados[0].strip())
                    stat_ia = c2.selectbox("Status", ["Pendente", "Pago"])
                    
                    c3, c4, c5 = st.columns(3)
                    d_ia = c3.text_input("Data", dados[1].strip())
                    iv_ia = c4.number_input("IVA (€)", value=extrair_valor_ia(dados[3]))
                    v_ia = c5.number_input("Total a Receber (€)", value=extrair_valor_ia(dados[2]))
                    
                    if st.form_submit_button("Guardar Receita na Nuvem", use_container_width=True):
                        if c_ia: run_query("INSERT INTO clientes (nome) VALUES (%s) ON CONFLICT (nome) DO NOTHING", (c_ia,))
                        run_query("INSERT INTO receitas (data, cliente, valor, iva, categoria, status, criado_por) VALUES (%s,%s,%s,%s,%s,%s,%s)", 
                                  (d_ia, c_ia, v_ia, iv_ia, "Serviço Prestado", stat_ia, st.session_state.usuario_nome))
                        st.success("Receita Guardada!")
                        limpar_memoria()
                        st.rerun()

    with t_man_rec:
        with st.form("f_man_rec"):
            c1, c2 = st.columns(2)
            cm = c1.selectbox("Selecione o Cliente", clis if clis else ["Nenhum"])
            sm = c2.selectbox("Status", ["Pago", "Pendente"])
            c3, c4, c5 = st.columns(3)
            dm = c3.date_input("Data")
            ivm = c4.number_input("IVA (€)", min_value=0.0)
            vm = c5.number_input("Total (€)", min_value=0.0)
            if st.form_submit_button("Registar Receita Manual", use_container_width=True):
                run_query("INSERT INTO receitas (data, cliente, valor, iva, categoria, status, criado_por) VALUES (%s,%s,%s,%s,%s,%s,%s)", 
                          (str(dm), cm, vm, ivm, "Serviço Prestado", sm, st.session_state.usuario_nome))
                st.success("Registado!")
                limpar_memoria()
                st.rerun()
                
    st.write("")
    st.subheader("🧾 Contas a Receber (Receitas Registadas)")
    df_rec = pd.read_sql_query("SELECT id, data, cliente, valor, iva, status FROM receitas ORDER BY status DESC, data DESC LIMIT 15", get_connection())
    if not df_rec.empty:
        df_rec['valor'] = df_rec['valor'].apply(formatar_moeda)
        df_rec['iva'] = df_rec['iva'].apply(formatar_moeda)
        st.dataframe(df_rec.drop(columns=['id']), use_container_width=True, hide_index=True)
    else: st.info("Sem receitas registadas.")

# ===============================================
# CONTA SÓCIO, CLIENTES, RELATÓRIOS E PASTAS
# ===============================================
elif st.session_state.menu == "Socio":
    st.title("🧑‍💼 Conta Pessoal Fábio")
    col_in, col_vi = st.columns([1, 2])
    with col_in:
        with st.form("f_soc"):
            tipo = st.selectbox("Tipo", ["Aporte (Fábio -> Empresa)", "Reembolso (Empresa -> Fábio)"])
            val = st.number_input("Valor (€)", min_value=0.0)
            desc = st.text_area("Motivo")
            if st.form_submit_button("Registar Movimento", use_container_width=True):
                run_query("INSERT INTO socio_movimentos (data, tipo, valor, descricao, usuario) VALUES (%s,%s,%s,%s,%s)", 
                          (str(datetime.now().date()), tipo, val, desc, st.session_state.usuario_nome))
                st.rerun()
    with col_vi:
        df_s = pd.read_sql_query("SELECT data, tipo, valor, descricao, usuario FROM socio_movimentos ORDER BY data DESC", get_connection())
        st.dataframe(df_s, use_container_width=True, hide_index=True)

elif st.session_state.menu == "Clientes":
    st.title("👥 Gestão de Clientes")
    with st.form("f_cli"):
        c1, c2 = st.columns(2); n = c1.text_input("Nome Cliente"); p = c2.text_input("País")
        if st.form_submit_button("Criar Cliente"):
            run_query("INSERT INTO clientes (nome, pais) VALUES (%s,%s)", (n, p))
            limpar_memoria()
            st.rerun()
    df_c = pd.read_sql_query("SELECT nome, pais, responsavel, email FROM clientes", get_connection())
    st.dataframe(df_c, use_container_width=True, hide_index=True)

elif st.session_state.menu == "Relatorios":
    st.title("📈 Relatórios DRE e Rentabilidade")
    t_r = run_query("SELECT SUM(valor) FROM receitas WHERE status='Pago'", fetch=True)[0][0] or 0
    t_d = run_query("SELECT SUM(valor) FROM despesas WHERE status='Pago'", fetch=True)[0][0] or 0
    st.metric("📊 LUCRO LÍQUIDO REALIZADO", formatar_moeda(t_r - t_d))
    st.write("---")
    df_cat = pd.read_sql_query("SELECT categoria, SUM(valor) as total FROM despesas WHERE status='Pago' GROUP BY categoria ORDER BY total DESC", get_connection())
    if not df_cat.empty:
        st.subheader("Onde se gasta mais dinheiro?")
        st.plotly_chart(px.pie(df_cat, values='total', names='categoria', hole=0.3), use_container_width=True)

elif st.session_state.menu == "Pastas":
    st.title("📂 Explorador de Pastas")
    st.warning("Aviso Cloud: O arquivo digital (PDFs) continuará a ser gerado na sua máquina local até ativarmos o Storage em Nuvem.")
    pasta = st.selectbox("Escolha a Categoria Principal", CATEGORIAS_BASE)
    
    df_p = obter_dados_pastas(pasta)
    st.dataframe(df_p, use_container_width=True, hide_index=True)
