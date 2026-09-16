import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, timedelta
import calendar

DB_NAME = "fabiola_advocacia_sistema.db"
MEMBERS = ["Fabrício", "Dra. Fabíola"]

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Plano de Contas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chart_of_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            level INTEGER NOT NULL
        )
    """)

    # 2. Contatos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact_type TEXT NOT NULL,
            doc TEXT,
            phone TEXT,
            email TEXT,
            notes TEXT
        )
    """)

    # 3. Histórico Padrão
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS standard_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            description TEXT NOT NULL UNIQUE
        )
    """)

    # 4. Lançamentos Financeiros
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financial_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_type TEXT NOT NULL,
            chart_account TEXT NOT NULL,
            contact_id INTEGER,
            contact_name TEXT,
            history_id INTEGER,
            history_desc TEXT NOT NULL,
            history_detail TEXT,
            amount REAL NOT NULL,
            due_date DATE NOT NULL,
            payment_date DATE,
            payer_responsible TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contact_id) REFERENCES contacts (id),
            FOREIGN KEY (history_id) REFERENCES standard_history (id)
        )
    """)

    # Carga padrão inicial
    cursor.execute("SELECT COUNT(*) FROM chart_of_accounts")
    if cursor.fetchone()[0] == 0:
        contas_base = [
            ("1", "Receitas Operacionais", "Receita", 1),
            ("1.1", "Honorários Advocatícios", "Receita", 2),
            ("1.1.01", "Honorários Contratuais", "Receita", 3),
            ("1.1.02", "Honorários Sucumbenciais", "Receita", 3),
            ("1.1.03", "Consultorias e Pareceres", "Receita", 3),
            ("2", "Despesas Operacionais", "Despesa", 1),
            ("2.1", "Custas e Diligências", "Despesa", 2),
            ("2.1.01", "Custas Judiciais e Emolumentos", "Despesa", 3),
            ("2.1.02", "Diligências, Deslocamentos e Cópias", "Despesa", 3),
            ("2.2", "Despesas Administrativas", "Despesa", 2),
            ("2.2.01", "Sistemas, Software e TI", "Despesa", 3),
            ("2.2.02", "Material de Escritório", "Despesa", 3),
            ("2.2.03", "Telefonia e Infraestrutura", "Despesa", 3),
            ("2.2.04", "Marketing e Publicações", "Despesa", 3)
        ]
        cursor.executemany("INSERT INTO chart_of_accounts (code, name, type, level) VALUES (?, ?, ?, ?)", contas_base)

    cursor.execute("SELECT COUNT(*) FROM standard_history")
    if cursor.fetchone()[0] == 0:
        hist_base = [
            ("HP01", "Recebimento de Honorários Advocatícios"),
            ("HP02", "Pagamento de Custas Judiciais"),
            ("HP03", "Assinatura Mensal de Sistema / TI"),
            ("HP04", "Despesas Gerais de Manutenção do Escritório"),
            ("HP05", "Reembolso de Despesas com Diligências")
        ]
        cursor.executemany("INSERT INTO standard_history (code, description) VALUES (?, ?)", hist_base)

    conn.commit()

init_db()

def somar_meses(data_origem, qtd_meses):
    """Calcula a data somando N meses com precisão de calendário."""
    ano = data_origem.year + (data_origem.month + qtd_meses - 1) // 12
    mes = (data_origem.month + qtd_meses - 1) % 12 + 1
    ultimo_dia_mes = calendar.monthrange(ano, mes)[1]
    dia = min(data_origem.day, ultimo_dia_mes)
    return date(ano, mes, dia)

def render():
    conn = get_connection()
    st.sidebar.markdown("---")
    st.sidebar.subheader("Menu Financeiro")

    menu_fin = st.sidebar.radio(
        "Navegação",
        [
            "📊 Painel Geral de Lançamentos",
            "✏️ Alterar / Excluir Lançamentos",
            "📅 Gerar Contas a Pagar",
            "⚡ Baixas Rápidas / em Lote",
            "🤝 Acerto de Sócios (50/50)",
            "📁 Cadastros (Contas, Contatos, Históricos)",
            "📑 Relatórios & DRE"
        ]
    )

    # --------------------------------------------------------------------------
    # 1. PAINEL GERAL DE LANÇAMENTOS (CONSULTA E INCLUSÃO RÁPIDA)
    # --------------------------------------------------------------------------
    if menu_fin == "📊 Painel Geral de Lançamentos":
        st.title("💵 Lançamentos Financeiros")
        st.caption("Visão integrada de receitas e despesas")

        with st.expander("➕ Novo Lançamento Rápido", expanded=False):
            with st.form("form_novo_lanc", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    e_type = st.selectbox("Tipo *", ["Despesa", "Receita"])
                    df_acc = pd.read_sql_query(
                        "SELECT code || ' - ' || name AS full_name FROM chart_of_accounts WHERE type = ? AND level = 3 ORDER BY code",
                        conn, params=(e_type,)
                    )
                    acc_val = st.selectbox("Conta Contábil *", df_acc["full_name"].tolist() if not df_acc.empty else ["Geral"])
                    df_cont = pd.read_sql_query("SELECT id, name FROM contacts ORDER BY name", conn)
                    cont_map = {"Nenhum / Não informado": None}
                    for _, r in df_cont.iterrows():
                        cont_map[r["name"]] = r["id"]
                    sel_contact = st.selectbox("Cliente / Fornecedor", list(cont_map.keys()))

                with c2:
                    df_h = pd.read_sql_query("SELECT id, description FROM standard_history ORDER BY description", conn)
                    h_map = {r["description"]: r["id"] for _, r in df_h.iterrows()}
                    sel_h = st.selectbox("Histórico Padrão *", list(h_map.keys()) if h_map else ["Despesa Geral"])
                    h_detail = st.text_input("Complemento do Histórico", placeholder="Ex: Ref. Processo nº 00123/2026")
                    amount = st.number_input("Valor (R$) *", min_value=0.01, step=10.0, format="%.2f")

                with c3:
                    due_date = st.date_input("Data de Vencimento *", value=date.today())
                    payer = st.selectbox("Responsável / Pago por *", MEMBERS)
                    status_ini = st.selectbox("Situação Inicial *", ["Aberto", "Liquidado"])
                    dt_pagto = due_date if status_ini == "Liquidado" else None

                if st.form_submit_button("Salvar Lançamento", use_container_width=True):
                    cid = cont_map.get(sel_contact)
                    hid = h_map.get(sel_h)
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO financial_entries (entry_type, chart_account, contact_id, contact_name, history_id, history_desc, history_detail, amount, due_date, payment_date, payer_responsible, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (e_type, acc_val, cid, sel_contact if cid else None, hid, sel_h, h_detail, amount, str(due_date), str(dt_pagto) if dt_pagto else None, payer, status_ini))
                    conn.commit()
                    st.success("Lançamento adicionado com sucesso!")
                    st.rerun()

        # Filtros
        st.subheader("Filtragem de Registros")
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            f_tipo = st.multiselect("Tipo", ["Despesa", "Receita"], default=["Despesa", "Receita"])
        with f2:
            f_status = st.multiselect("Situação", ["Aberto", "Liquidado"], default=["Aberto", "Liquidado"])
        with f3:
            f_resp = st.multiselect("Responsável", MEMBERS, default=MEMBERS)
        with f4:
            f_periodo = st.date_input("Período (Vencimento)", value=(date.today().replace(day=1), date.today() + timedelta(days=30)))

        q = "SELECT * FROM financial_entries WHERE 1=1"
        par = []
        if f_tipo:
            q += f" AND entry_type IN ({','.join(['?']*len(f_tipo))})"
            par.extend(f_tipo)
        if f_status:
            q += f" AND status IN ({','.join(['?']*len(f_status))})"
            par.extend(f_status)
        if f_resp:
            q += f" AND payer_responsible IN ({','.join(['?']*len(f_resp))})"
            par.extend(f_resp)
        if isinstance(f_periodo, tuple) and len(f_periodo) == 2:
            q += " AND due_date BETWEEN ? AND ?"
            par.extend([str(f_periodo[0]), str(f_periodo[1])])

        q += " ORDER BY due_date ASC"
        df_fin = pd.read_sql_query(q, conn, params=par)

        rec_liq = df_fin[(df_fin["entry_type"] == "Receita") & (df_fin["status"] == "Liquidado")]["amount"].sum()
        desp_liq = df_fin[(df_fin["entry_type"] == "Despesa") & (df_fin["status"] == "Liquidado")]["amount"].sum()
        saldo = rec_liq - desp_liq
        pend_pagar = df_fin[(df_fin["entry_type"] == "Despesa") & (df_fin["status"] == "Aberto")]["amount"].sum()

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Receitas Liquidadas", f"R$ {rec_liq:,.2f}")
        m2.metric("Despesas Liquidadas", f"R$ {desp_liq:,.2f}")
        m3.metric("Saldo Realizado", f"R$ {saldo:,.2f}")
        m4.metric("Contas a Pagar (Aberto)", f"R$ {pend_pagar:,.2f}", delta_color="inverse")

        st.markdown("---")

        if df_fin.empty:
            st.info("Nenhum lançamento encontrado para os filtros selecionados.")
        else:
            cols_show = ["id", "entry_type", "chart_account", "contact_name", "history_desc", "history_detail", "amount", "due_date", "payer_responsible", "status"]
            st.dataframe(
                df_fin[cols_show],
                column_config={
                    "id": "Cód.",
                    "entry_type": "Tipo",
                    "chart_account": "Conta Contábil",
                    "contact_name": "Favorecido/Cliente",
                    "history_desc": "Histórico",
                    "history_detail": "Complemento",
                    "amount": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                    "due_date": "Vencimento",
                    "payer_responsible": "Responsável",
                    "status": "Situação"
                },
                hide_index=True,
                use_container_width=True
            )

    # --------------------------------------------------------------------------
    # 2. ALTERAR E EXCLUIR LANÇAMENTOS (CRUD COMPLETO)
    # --------------------------------------------------------------------------
    elif menu_fin == "✏️ Alterar / Excluir Lançamentos":
        st.title("✏️ Manutenção de Lançamentos")
        st.caption("Edite dados ou exclua lançamentos do sistema")

        df_all_entries = pd.read_sql_query("SELECT id, due_date, entry_type, history_desc, amount, payer_responsible, status FROM financial_entries ORDER BY id DESC", conn)

        if df_all_entries.empty:
            st.info("Não há lançamentos cadastrados para edição.")
        else:
            # Lista de seleção descritiva
            df_all_entries["label"] = df_all_entries.apply(
                lambda r: f"Cód. {r['id']} | {r['due_date']} | {r['entry_type']} | R$ {r['amount']:.2f} | {r['history_desc']} ({r['payer_responsible']})", axis=1
            )
            opcoes_lanc = dict(zip(df_all_entries["label"], df_all_entries["id"]))
            sel_label = st.selectbox("Selecione o Lançamento para editar ou excluir:", list(opcoes_lanc.keys()))
            entry_id = opcoes_lanc[sel_label]

            # Carrega dados do registro selecionado
            cur = conn.cursor()
            cur.execute("SELECT * FROM financial_entries WHERE id = ?", (entry_id,))
            reg = cur.fetchone()

            # reg indices: 0:id, 1:entry_type, 2:chart_account, 3:contact_id, 4:contact_name, 5:history_id, 6:history_desc, 7:history_detail, 8:amount, 9:due_date, 10:payment_date, 11:payer_responsible, 12:status
            col_edit, col_del = st.columns([3, 1], gap="large")

            with col_edit:
                st.subheader(f"Editar Lançamento #{entry_id}")
                with st.form("form_editar_lancamento"):
                    ce1, ce2 = st.columns(2)
                    with ce1:
                        edit_type = st.selectbox("Tipo", ["Despesa", "Receita"], index=0 if reg[1] == "Despesa" else 1)
                        df_acc = pd.read_sql_query("SELECT code || ' - ' || name AS full_name FROM chart_of_accounts WHERE type = ? AND level = 3 ORDER BY code", conn, params=(edit_type,))
                        lista_contas = df_acc["full_name"].tolist() if not df_acc.empty else [reg[2]]
                        idx_conta = lista_contas.index(reg[2]) if reg[2] in lista_contas else 0
                        edit_acc = st.selectbox("Conta Contábil", lista_contas, index=idx_conta)

                        df_cont = pd.read_sql_query("SELECT id, name FROM contacts ORDER BY name", conn)
                        cont_map = {"Nenhum / Não informado": None}
                        for _, r in df_cont.iterrows():
                            cont_map[r["name"]] = r["id"]
                        lista_contatos = list(cont_map.keys())
                        idx_contato = lista_contatos.index(reg[4]) if reg[4] in lista_contatos else 0
                        edit_contact = st.selectbox("Cliente / Fornecedor", lista_contatos, index=idx_contato)

                        edit_amount = st.number_input("Valor (R$)", value=float(reg[8]), min_value=0.01, step=10.0, format="%.2f")

                    with ce2:
                        df_h = pd.read_sql_query("SELECT id, description FROM standard_history ORDER BY description", conn)
                        h_map = {r["description"]: r["id"] for _, r in df_h.iterrows()}
                        lista_h = list(h_map.keys()) if h_map else [reg[6]]
                        idx_h = lista_h.index(reg[6]) if reg[6] in lista_h else 0
                        edit_h = st.selectbox("Histórico Padrão", lista_h, index=idx_h)

                        edit_h_detail = st.text_input("Complemento do Histórico", value=reg[7] if reg[7] else "")
                        
                        dt_venc_atual = pd.to_datetime(reg[9]).date()
                        edit_due = st.date_input("Data de Vencimento", value=dt_venc_atual)

                        edit_resp = st.selectbox("Responsável", MEMBERS, index=MEMBERS.index(reg[11]) if reg[11] in MEMBERS else 0)
                        edit_status = st.selectbox("Status", ["Aberto", "Liquidado"], index=0 if reg[12] == "Aberto" else 1)

                    if st.form_submit_button("💾 Salvar Alterações", type="primary", use_container_width=True):
                        cid = cont_map.get(edit_contact)
                        hid = h_map.get(edit_h)
                        dt_pag = str(edit_due) if edit_status == "Liquidado" else None
                        cur.execute("""
                            UPDATE financial_entries 
                            SET entry_type = ?, chart_account = ?, contact_id = ?, contact_name = ?, history_id = ?, history_desc = ?, 
                                history_detail = ?, amount = ?, due_date = ?, payment_date = ?, payer_responsible = ?, status = ?
                            WHERE id = ?
                        """, (edit_type, edit_acc, cid, edit_contact if cid else None, hid, edit_h, edit_h_detail, edit_amount, str(edit_due), dt_pag, edit_resp, edit_status, entry_id))
                        conn.commit()
                        st.success(f"Lançamento #{entry_id} atualizado com sucesso!")
                        st.rerun()

            with col_del:
                st.subheader("Zona de Exclusão")
                st.write(f"Deseja remover permanentemente o lançamento **#{entry_id}**?")
                confirmar = st.checkbox("Confirmo que desejo excluir este lançamento.", key=f"conf_del_{entry_id}")
                if st.button("🗑️ Excluir Lançamento", type="secondary", use_container_width=True):
                    if confirmar:
                        cur.execute("DELETE FROM financial_entries WHERE id = ?", (entry_id,))
                        conn.commit()
                        st.success(f"Lançamento #{entry_id} excluído com sucesso!")
                        st.rerun()
                    else:
                        st.error("Marque a caixa de confirmação para poder excluir.")

    # --------------------------------------------------------------------------
    # 3. GERADOR DE CONTAS A PAGAR (FIXAS, PARCELADAS E RECORRENTES)
    # --------------------------------------------------------------------------
    elif menu_fin == "📅 Gerar Contas a Pagar":
        st.title("📅 Gerar Contas a Pagar & Provisões")
        st.caption("Cadastre despesas parceladas ou gere previsões mensais automáticas com status 'Aberto'")

        with st.form("form_gerar_contas_pagar"):
            g1, g2 = st.columns(2)
            with g1:
                df_desp = pd.read_sql_query("SELECT code || ' - ' || name AS full_name FROM chart_of_accounts WHERE type = 'Despesa' AND level = 3 ORDER BY code", conn)
                g_conta = st.selectbox("Conta de Despesa *", df_desp["full_name"].tolist() if not df_desp.empty else ["Despesas Gerais"])
                
                df_cont = pd.read_sql_query("SELECT id, name FROM contacts WHERE contact_type IN ('Fornecedor', 'Parceiro') ORDER BY name", conn)
                cont_map = {"Nenhum / Não informado": None}
                for _, r in df_cont.iterrows():
                    cont_map[r["name"]] = r["id"]
                g_fornec = st.selectbox("Fornecedor / Favorecido", list(cont_map.keys()))

                df_h = pd.read_sql_query("SELECT id, description FROM standard_history ORDER BY description", conn)
                h_map = {r["description"]: r["id"] for _, r in df_h.iterrows()}
                g_hist = st.selectbox("Histórico Padrão *", list(h_map.keys()) if h_map else ["Pagamento de Despesa"])
                g_detalhe = st.text_input("Complemento do Histórico", placeholder="Ex: Aluguel da Sala / Assinatura Sistema")

            with g2:
                g_valor = st.number_input("Valor de Cada Parcela (R$) *", min_value=0.01, step=50.0, format="%.2f")
                g_venc_ini = st.date_input("Vencimento da 1ª Parcela *", value=date.today())
                g_parcelas = st.number_input("Quantidade de Parcelas / Meses a gerar *", min_value=1, max_value=60, value=12)
                g_resp = st.selectbox("Responsável Previsto *", MEMBERS)

            st.write(f"**Resumo:** Serão geradas **{g_parcelas} contas a pagar** de **R$ {g_valor:,.2f}** (Total previsto: **R$ {(g_parcelas * g_valor):,.2f}**).")

            if st.form_submit_button("⚡ Gerar Contas a Pagar", type="primary", use_container_width=True):
                cur = conn.cursor()
                cid = cont_map.get(g_fornec)
                hid = h_map.get(g_hist)

                for i in range(int(g_parcelas)):
                    dt_parcela = somar_meses(g_venc_ini, i)
                    sufixo_parcela = f" ({i+1}/{int(g_parcelas)})" if g_parcelas > 1 else ""
                    detalhe_final = (g_detalhe + sufixo_parcela).strip()

                    cur.execute("""
                        INSERT INTO financial_entries (entry_type, chart_account, contact_id, contact_name, history_id, history_desc, history_detail, amount, due_date, payment_date, payer_responsible, status)
                        VALUES ('Despesa', ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 'Aberto')
                    """, (g_conta, cid, g_fornec if cid else None, hid, g_hist, detalhe_final, g_valor, str(dt_parcela), g_resp))

                conn.commit()
                st.success(f"{g_parcelas} contas a pagar foram geradas com sucesso com status 'Aberto'!")
                st.rerun()

    # --------------------------------------------------------------------------
    # 4. BAIXAS RÁPIDAS / EM LOTE
    # --------------------------------------------------------------------------
    elif menu_fin == "⚡ Baixas Rápidas / em Lote":
        st.title("⚡ Baixas e Liquidações em Lote")
        st.caption("Selecione os lançamentos para dar baixa de uma só vez")

        df_abertos = pd.read_sql_query(
            "SELECT id, entry_type, chart_account, contact_name, history_desc, amount, due_date, payer_responsible FROM financial_entries WHERE status = 'Aberto' ORDER BY due_date ASC",
            conn
        )

        if df_abertos.empty:
            st.success("Não há contas pendentes de liquidação no momento!")
        else:
            df_abertos["Selecionar"] = False
            editado = st.data_editor(
                df_abertos,
                column_config={
                    "Selecionar": st.column_config.CheckboxColumn("Liquidar?", default=False),
                    "amount": st.column_config.NumberColumn("Valor", format="R$ %.2f")
                },
                disabled=["id", "entry_type", "chart_account", "contact_name", "history_desc", "amount", "due_date", "payer_responsible"],
                hide_index=True,
                use_container_width=True
            )

            b1, b2 = st.columns([2, 2])
            with b1:
                dt_baixa = st.date_input("Data do Pagamento/Liquidação", value=date.today())
            with b2:
                st.write("")
                if st.button("Confirmar Baixa dos Selecionados", type="primary", use_container_width=True):
                    marcados = editado[editado["Selecionar"] == True]["id"].tolist()
                    if marcados:
                        cur = conn.cursor()
                        cur.execute(
                            f"UPDATE financial_entries SET status = 'Liquidado', payment_date = ? WHERE id IN ({','.join(['?']*len(marcados))})",
                            [str(dt_baixa)] + marcados
                        )
                        conn.commit()
                        st.success(f"{len(marcados)} lançamento(s) liquidado(s)!")
                        st.rerun()
                    else:
                        st.warning("Selecione pelo menos um lançamento marcando a caixa.")

    # --------------------------------------------------------------------------
    # 5. ACERTO DE CONTAS ENTRE SÓCIOS (50/50)
    # --------------------------------------------------------------------------
    elif menu_fin == "🤝 Acerto de Sócios (50/50)":
        st.title("🤝 Acerto de Contas entre Sócios")
        st.caption("Equalização das despesas operacionais pagas individualmente")

        df_pago = pd.read_sql_query(
            "SELECT payer_responsible, SUM(amount) as total FROM financial_entries WHERE entry_type = 'Despesa' AND status = 'Liquidado' GROUP BY payer_responsible",
            conn
        )

        totais = {"Fabrício": 0.0, "Dra. Fabíola": 0.0}
        for _, r in df_pago.iterrows():
            if r["payer_responsible"] in totais:
                totais[r["payer_responsible"]] = float(r["total"])

        p_fab = totais["Fabrício"]
        p_dra = totais["Dra. Fabíola"]
        tot_geral = p_fab + p_dra
        metade = tot_geral / 2.0

        c_a1, c_a2, c_a3 = st.columns(3)
        c_a1.metric("Pago por Fabrício", f"R$ {p_fab:,.2f}")
        c_a2.metric("Pago por Dra. Fabíola", f"R$ {p_dra:,.2f}")
        c_a3.metric("Total de Despesas (50% = R$ {:,.2f})".format(metade), f"R$ {tot_geral:,.2f}")

        st.markdown("---")
        if p_fab > p_dra:
            dif = p_fab - metade
            st.warning(f"**Resultado:** Dra. Fabíola deve transferir **R$ {dif:,.2f}** para Fabrício para equalizar as despesas da sociedade em 50/50.")
        elif p_dra > p_fab:
            dif = p_dra - metade
            st.warning(f"**Resultado:** Fabrício deve transferir **R$ {dif:,.2f}** para Dra. Fabíola para equalizar as despesas da sociedade em 50/50.")
        else:
            st.success("**Resultado:** As despesas pagas estão exatamente equilibradas! Nenhuma transferência necessária.")

    # --------------------------------------------------------------------------
    # 6. CADASTROS BÁSICOS DO FINANCEIRO
    # --------------------------------------------------------------------------
    elif menu_fin == "📁 Cadastros (Contas, Contatos, Históricos)":
        st.title("📁 Cadastros do Sistema Financeiro")
        t_plano, t_contatos, t_hist = st.tabs(["Plano de Contas", "Clientes & Fornecedores", "Históricos Padrão"])

        with t_plano:
            st.subheader("Plano de Contas Hierárquico")
            with st.expander("➕ Nova Conta Contábil"):
                with st.form("form_add_conta"):
                    c_cod = st.text_input("Código Estruturado (ex: 2.2.05)")
                    c_nome = st.text_input("Nome da Conta")
                    c_tipo = st.selectbox("Tipo", ["Despesa", "Receita"])
                    c_nivel = st.selectbox("Nível", [1, 2, 3], index=2)
                    if st.form_submit_button("Salvar Conta"):
                        if c_cod.strip() and c_nome.strip():
                            try:
                                cur = conn.cursor()
                                cur.execute("INSERT INTO chart_of_accounts (code, name, type, level) VALUES (?, ?, ?, ?)", (c_cod.strip(), c_nome.strip(), c_tipo, c_nivel))
                                conn.commit()
                                st.success("Conta cadastrada!")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Código já cadastrado.")
            df_pc = pd.read_sql_query("SELECT code, name, type, level FROM chart_of_accounts ORDER BY code ASC", conn)
            st.dataframe(df_pc, column_config={"code": "Código", "name": "Nome", "type": "Tipo", "level": "Nível"}, hide_index=True, use_container_width=True)

        with t_contatos:
            st.subheader("Clientes, Fornecedores e Parceiros")
            with st.expander("➕ Novo Contato"):
                with st.form("form_add_contato"):
                    ct_nome = st.text_input("Nome / Razão Social *")
                    ct_tipo = st.selectbox("Tipo de Contato", ["Cliente", "Fornecedor", "Parceiro"])
                    ct_doc = st.text_input("CPF ou CNPJ")
                    ct_tel = st.text_input("Telefone / WhatsApp")
                    ct_email = st.text_input("E-mail")
                    ct_obs = st.text_area("Observações")
                    if st.form_submit_button("Salvar Contato"):
                        if ct_nome.strip():
                            cur = conn.cursor()
                            cur.execute("INSERT INTO contacts (name, contact_type, doc, phone, email, notes) VALUES (?, ?, ?, ?, ?, ?)", (ct_nome.strip(), ct_tipo, ct_doc, ct_tel, ct_email, ct_obs))
                            conn.commit()
                            st.success("Contato salvo!")
                            st.rerun()
            df_contatos = pd.read_sql_query("SELECT id, name, contact_type, doc, phone, email FROM contacts ORDER BY name ASC", conn)
            st.dataframe(df_contatos, hide_index=True, use_container_width=True)

        with t_hist:
            st.subheader("Históricos Padrão")
            with st.expander("➕ Novo Histórico"):
                with st.form("form_add_hp"):
                    h_cod = st.text_input("Código (opcional)")
                    h_desc = st.text_input("Descrição *")
                    if st.form_submit_button("Salvar Histórico"):
                        if h_desc.strip():
                            try:
                                cur = conn.cursor()
                                cur.execute("INSERT INTO standard_history (code, description) VALUES (?, ?)", (h_cod.strip(), h_desc.strip()))
                                conn.commit()
                                st.success("Histórico cadastrado!")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Descrição já cadastrada.")
            df_hp = pd.read_sql_query("SELECT code, description FROM standard_history ORDER BY description ASC", conn)
            st.dataframe(df_hp, hide_index=True, use_container_width=True)

    # --------------------------------------------------------------------------
    # 7. RELATÓRIOS & DRE GERENCIAL
    # --------------------------------------------------------------------------
    elif menu_fin == "📑 Relatórios & DRE":
        st.title("📑 Relatórios Financeiros")
        st.caption("Demonstrativo de Resultado e Exportações")

        r1, r2 = st.columns(2)
        with r1:
            dt_ini = st.date_input("Data Inicial", value=date.today().replace(day=1))
        with r2:
            dt_fim = st.date_input("Data Final", value=date.today() + timedelta(days=30))

        df_rel = pd.read_sql_query(
            "SELECT * FROM financial_entries WHERE due_date BETWEEN ? AND ?",
            conn, params=(str(dt_ini), str(dt_fim))
        )

        st.subheader("DRE por Conta Contábil")
        if df_rel.empty:
            st.info("Sem movimentações no período selecionado.")
        else:
            dre_df = df_rel[df_rel["status"] == "Liquidado"].groupby(["entry_type", "chart_account"])["amount"].sum().reset_index()
            st.dataframe(
                dre_df,
                column_config={
                    "entry_type": "Tipo",
                    "chart_account": "Conta",
                    "amount": st.column_config.NumberColumn("Total Realizado", format="R$ %.2f")
                },
                hide_index=True,
                use_container_width=True
            )

            csv = df_rel.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Exportar Dados Completos do Período em CSV",
                data=csv,
                file_name=f"relatorio_financeiro_{dt_ini}_{dt_fim}.csv",
                mime="text/csv"
            )