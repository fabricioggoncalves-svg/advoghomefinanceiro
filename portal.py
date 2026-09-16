import streamlit as st
import modulo_tarefas
import modulo_financeiro

st.set_page_config(
    page_title="Portal Jurídico - Dra. Fabíola",
    page_icon="⚖️",
    layout="wide"
)

# Estilização do Banner e Cards da Tela Inicial
st.markdown("""
<style>
    .portal-banner {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        color: #ffffff;
        padding: 35px 25px;
        border-radius: 12px;
        text-align: center;
        margin-bottom: 30px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.15);
    }
    .portal-title {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 6px;
    }
    .portal-subtitle {
        font-size: 1.05rem;
        color: #94a3b8;
    }
    .app-card {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 12px;
        min-height: 160px;
    }
    .app-card h3 {
        color: #0f172a;
        margin-top: 0px;
        font-size: 1.35rem;
    }
    .app-card p {
        color: #475569;
        font-size: 0.95rem;
        line-height: 1.5;
    }
</style>
""", unsafe_allow_html=True)

if "app_ativo" not in st.session_state:
    st.session_state["app_ativo"] = None

# Menu Lateral de Navegação
st.sidebar.title("🏢 Escritório")
st.sidebar.caption("Dra. Fabíola & Fabrício")

opcoes = ["🏠 Tela Inicial (Portal)", "📋 Gestão de Tarefas", "💵 Controle Financeiro"]
idx = 0
if st.session_state["app_ativo"] == "tarefas":
    idx = 1
elif st.session_state["app_ativo"] == "financeiro":
    idx = 2

nav = st.sidebar.radio("Navegar para:", opcoes, index=idx)

if nav == "📋 Gestão de Tarefas":
    st.session_state["app_ativo"] = "tarefas"
elif nav == "💵 Controle Financeiro":
    st.session_state["app_ativo"] = "financeiro"
elif nav == "🏠 Tela Inicial (Portal)":
    st.session_state["app_ativo"] = None

# Roteamento dos Sistemas
if st.session_state["app_ativo"] is None:
    st.markdown("""
        <div class="portal-banner">
            <div class="portal-title">⚖️ ESCRITÓRIO DRA. FABÍOLA</div>
            <div class="portal-subtitle">Portal Unificado • Gestão Operacional & Financeira</div>
        </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown("""
            <div class="app-card">
                <h3>📋 Gestão de Tarefas</h3>
                <p>
                    Controle conjunto de prazos e obrigações, acompanhamento de mini projetos com 
                    barra de progresso e filtros por período (Hoje, Amanhã, Semana, Atrasadas).
                </p>
            </div>
        """, unsafe_allow_html=True)
        if st.button("Acessar Gestão de Tarefas", use_container_width=True, type="primary"):
            st.session_state["app_ativo"] = "tarefas"
            st.rerun()

    with col2:
        st.markdown("""
            <div class="app-card">
                <h3>💵 Controle Financeiro</h3>
                <p>
                    Acesso completo ao sistema financeiro original: plano de contas, 
                    lançamentos, baixas em lote, acerto de sócios (50/50) e relatórios.
                </p>
            </div>
        """, unsafe_allow_html=True)
        if st.button("Acessar Controle Financeiro", use_container_width=True, type="primary"):
            st.session_state["app_ativo"] = "financeiro"
            st.rerun()

elif st.session_state["app_ativo"] == "tarefas":
    modulo_tarefas.render()

elif st.session_state["app_ativo"] == "financeiro":
    modulo_financeiro.render()