import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, timedelta

DB_NAME = "tarefas_projetos.db"
MEMBERS = ["Fabrício", "Dra. Fabíola"]
STATUS_OPTIONS = ["A Fazer", "Em Andamento", "Revisão", "Concluído"]
FILTER_STATUS_OPTIONS = ["A Fazer", "Em Andamento", "Revisão", "Atrasadas", "Concluído"]
PRIORITIES = ["Alta", "Média", "Baixa"]

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mini_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            responsible TEXT NOT NULL,
            category TEXT,
            due_date DATE NOT NULL,
            status TEXT NOT NULL,
            priority TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES mini_projects (id) ON DELETE SET NULL
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM task_categories")
    if cursor.fetchone()[0] == 0:
        categorias_base = [
            ("Prazos Judiciais",), ("Audiências",), ("Contratos",),
            ("Consultivo",), ("Operacional",), ("TI / Sistemas",), ("Urgente",)
        ]
        cursor.executemany("INSERT INTO task_categories (name) VALUES (?)", categorias_base)
    conn.commit()

init_db()

def get_categories(conn):
    df_cat = pd.read_sql_query("SELECT name FROM task_categories ORDER BY name ASC", conn)
    if not df_cat.empty:
        return df_cat["name"].tolist()
    return ["Geral", "Operacional", "Urgente"]

def render():
    conn = get_connection()
    today = date.today()

    # =========================================================================
    # BARRA LATERAL: MENU HIERÁRQUICO COM SUBMENUS INDENTADOS
    # =========================================================================
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📋 Gestão de Tarefas")

    opcoes_menu = [
        "📊 Painel Geral de Tarefas",
        "── ✍️ Lançamentos ──",
        "    └─ ➕ Inclusão de Tarefa",
        "    └─ ✏️ Alteração de Tarefa",
        "    └─ 🗑️ Exclusão de Tarefa",
        "── ⚙️ Manutenção ──",
        "    └─ 📁 Mini Projetos",
        "    └─ 🏷️ Áreas / Categorias",
        "    └─ 📑 Histórico & Exportação"
    ]

    if "tarefas_menu_sel" not in st.session_state:
        st.session_state["tarefas_menu_sel"] = "📊 Painel Geral de Tarefas"

    idx_default = 0
    if st.session_state["tarefas_menu_sel"] in opcoes_menu:
        idx_default = opcoes_menu.index(st.session_state["tarefas_menu_sel"])

    selecao = st.sidebar.radio(
        "Navegação:",
        opcoes_menu,
        index=idx_default,
        label_visibility="collapsed"
    )

    if "──" in selecao:
        st.sidebar.caption("Selecione uma opção com '└─' acima.")
        tela_ativa = st.session_state.get("tarefas_ultima_tela", "📊 Painel Geral de Tarefas")
    else:
        tela_ativa = selecao
        st.session_state["tarefas_menu_sel"] = selecao
        st.session_state["tarefas_ultima_tela"] = selecao

    categories_list = get_categories(conn)
    df_projs = pd.read_sql_query("SELECT id, name FROM mini_projects ORDER BY name ASC", conn)
    p_options = {"Nenhum (Tarefa Avulsa)": None}
    for _, p in df_projs.iterrows():
        p_options[p["name"]] = p["id"]

    # =========================================================================
    # 1. PAINEL GERAL DE TAREFAS
    # =========================================================================
    if tela_ativa == "📊 Painel Geral de Tarefas":
        st.title("📊 Painel Geral de Tarefas & Obrigações")
        st.caption("Visão executiva diária, métricas e controle compartilhado")

        q_metrics = "SELECT due_date, status FROM tasks"
        df_all = pd.read_sql_query(q_metrics, conn)

        if not df_all.empty:
            df_all["due_date"] = pd.to_datetime(df_all["due_date"]).dt.date
            tot_aberto = len(df_all[df_all["status"] != "Concluído"])
            tot_atrasado = len(df_all[(df_all["due_date"] < today) & (df_all["status"] != "Concluído")])
            tot_hoje = len(df_all[(df_all["due_date"] == today) & (df_all["status"] != "Concluído")])
            tot_concluido = len(df_all[df_all["status"] == "Concluído"])
        else:
            tot_aberto, tot_atrasado, tot_hoje, tot_concluido = 0, 0, 0, 0

        c_m1, c_m2, c_m3, c_m4 = st.columns(4)
        c_m1.metric("Pendências Totais", tot_aberto)
        c_m2.metric("Vencem Hoje", tot_hoje)
        c_m3.metric("Atrasadas", tot_atrasado, delta_color="inverse")
        c_m4.metric("Concluídas", tot_concluido)

        st.markdown("---")

        with st.expander("🔍 Filtros de Visualização e Pesquisa", expanded=True):
            f_col1, f_col2, f_col3, f_col4 = st.columns(4)
            with f_col1:
                DATE_PRESETS = ["Todos", "Hoje", "Amanhã", "Essa semana", "Período Personalizado"]
                sel_preset = st.selectbox("Vencimento / Prazo", DATE_PRESETS)
            with f_col2:
                all_p_names = ["Todos"] + list(df_projs["name"]) + ["Sem Projeto"]
                sel_p_filter = st.selectbox("Mini Projeto", all_p_names)
            with f_col3:
                sel_u_filter = st.multiselect("Responsável", MEMBERS, default=MEMBERS)
            with f_col4:
                sel_s_filter = st.multiselect(
                    "Situação",
                    FILTER_STATUS_OPTIONS,
                    default=["A Fazer", "Em Andamento", "Revisão", "Atrasadas"]
                )

            custom_range = None
            if sel_preset == "Período Personalizado":
                custom_range = st.date_input("Selecione o Intervalo", value=(today, today + timedelta(days=7)))

        q_tasks = """
            SELECT t.id, t.title, t.description, t.responsible, t.category, t.due_date, t.status, t.priority,
                   COALESCE(p.name, 'Sem Projeto') AS project_name
            FROM tasks t
            LEFT JOIN mini_projects p ON t.project_id = p.id
            ORDER BY t.due_date ASC
        """
        df_tasks = pd.read_sql_query(q_tasks, conn)

        if not df_tasks.empty:
            df_tasks["due_date"] = pd.to_datetime(df_tasks["due_date"]).dt.date
            df_f = df_tasks[df_tasks["responsible"].isin(sel_u_filter)]

            if sel_p_filter != "Todos":
                df_f = df_f[df_f["project_name"] == sel_p_filter]

            if sel_s_filter:
                status_convencionais = [s for s in sel_s_filter if s != "Atrasadas"]
                inclui_atrasadas = "Atrasadas" in sel_s_filter

                condicoes = []
                if status_convencionais:
                    condicoes.append(df_f["status"].isin(status_convencionais))
                if inclui_atrasadas:
                    condicoes.append((df_f["due_date"] < today) & (df_f["status"] != "Concluído"))

                if condicoes:
                    condicao_final = condicoes[0]
                    for c in condicoes[1:]:
                        condicao_final = condicao_final | c
                    df_f = df_f[condicao_final]

            if sel_preset == "Hoje":
                df_f = df_f[df_f["due_date"] == today]
            elif sel_preset == "Amanhã":
                df_f = df_f[df_f["due_date"] == today + timedelta(days=1)]
            elif sel_preset == "Essa semana":
                end_week = today + timedelta(days=(6 - today.weekday()))
                df_f = df_f[(df_f["due_date"] >= today) & (df_f["due_date"] <= end_week)]
            elif sel_preset == "Período Personalizado":
                if isinstance(custom_range, tuple) and len(custom_range) == 2:
                    df_f = df_f[(df_f["due_date"] >= custom_range[0]) & (df_f["due_date"] <= custom_range[1])]

            if sel_p_filter != "Todos" and sel_p_filter != "Sem Projeto":
                p_tasks = df_tasks[df_tasks["project_name"] == sel_p_filter]
                tot_p = len(p_tasks)
                concl_p = len(p_tasks[p_tasks["status"] == "Concluído"])
                prog = concl_p / tot_p if tot_p > 0 else 0
                st.subheader(f"Progresso do Projeto: {sel_p_filter}")
                st.progress(prog, text=f"{concl_p} de {tot_p} tarefas concluídas ({int(prog * 100)}%)")
                st.write("")

            st.markdown("### Quadro Operacional")
            if df_f.empty:
                st.info("Nenhuma tarefa corresponde aos filtros aplicados.")
            else:
                for _, row in df_f.iterrows():
                    is_late = row["due_date"] < today and row["status"] != "Concluído"
                    with st.container():
                        c1, c2, c3, c4 = st.columns([4, 2, 2, 1])
                        with c1:
                            txt_tit = f"**{row['title']}**"
                            if is_late:
                                txt_tit += " :red[(Atrasada)]"
                            st.markdown(txt_tit)
                            if row["project_name"] != "Sem Projeto":
                                st.caption(f"📁 **Projeto:** {row['project_name']}")
                            if row["description"]:
                                st.caption(row["description"])
                        with c2:
                            st.text(f"👤 {row['responsible']}")
                            st.caption(f"🏷️ {row['category']} | ⚡ {row['priority']}")
                        with c3:
                            st.text(f"📅 {row['due_date'].strftime('%d/%m/%Y')}")
                            new_st = st.selectbox(
                                "Status",
                                STATUS_OPTIONS,
                                index=STATUS_OPTIONS.index(row["status"]),
                                key=f"tsk_st_main_{row['id']}",
                                label_visibility="collapsed"
                            )
                            if new_st != row["status"]:
                                cur = conn.cursor()
                                cur.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_st, row["id"]))
                                conn.commit()
                                st.rerun()
                        with c4:
                            if st.button("🗑️", key=f"btn_del_main_{row['id']}", help="Excluir Tarefa Rapidamente"):
                                cur = conn.cursor()
                                cur.execute("DELETE FROM tasks WHERE id = ?", (row["id"],))
                                conn.commit()
                                st.rerun()
                        st.divider()
        else:
            st.info("Nenhuma tarefa cadastrada no momento. Acesse a opção **➕ Inclusão de Tarefa** na barra lateral.")

    # =========================================================================
    # 2. LANÇAMENTOS (SUBORDINADOS)
    # =========================================================================
    elif tela_ativa == "    └─ ➕ Inclusão de Tarefa":
        st.title("➕ Lançamento de Nova Tarefa")
        st.caption("Cadastre uma obrigação com prazo, responsável e vínculo opcional a mini projetos")

        with st.form("form_inclusao_tarefa", clear_on_submit=True):
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                t_title = st.text_input("Título da Tarefa *", placeholder="Ex: Protocolar contestação")
                t_desc = st.text_area("Descrição / Detalhes", placeholder="Instruções, links ou anotações...")
                t_pname = st.selectbox("Mini Projeto Vinculado", list(p_options.keys()))

            with col_t2:
                t_resp = st.selectbox("Responsável *", MEMBERS)
                t_cat = st.selectbox("Área / Categoria", categories_list)
                t_due = st.date_input("Prazo Limite *", value=today)
                t_prio = st.selectbox("Prioridade", PRIORITIES, index=1)

            if st.form_submit_button("💾 Salvar Tarefa", type="primary", use_container_width=True):
                if t_title.strip():
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO tasks (title, description, project_id, responsible, category, due_date, status, priority)
                        VALUES (?, ?, ?, ?, ?, ?, 'A Fazer', ?)
                    """, (t_title.strip(), t_desc.strip(), p_options[t_pname], t_resp, t_cat, str(t_due), t_prio))
                    conn.commit()
                    st.success("Tarefa incluída com sucesso!")
                    st.rerun()
                else:
                    st.error("Informe pelo menos o título da tarefa.")

    elif tela_ativa == "    └─ ✏️ Alteração de Tarefa":
        st.title("✏️ Alteração de Tarefas")
        st.caption("Selecione um lançamento existente para editar qualquer campo")

        df_all_t = pd.read_sql_query("""
            SELECT t.id, t.title, t.description, t.project_id, t.responsible, t.category, t.due_date, t.status, t.priority,
                   COALESCE(p.name, 'Sem Projeto') AS project_name
            FROM tasks t
            LEFT JOIN mini_projects p ON t.project_id = p.id
            ORDER BY t.id DESC
        """, conn)

        if df_all_t.empty:
            st.info("Nenhuma tarefa disponível para alteração.")
        else:
            df_all_t["label"] = df_all_t.apply(
                lambda r: f"Cód. {r['id']} | {r['due_date']} | {r['title']} ({r['responsible']}) - [{r['status']}]", axis=1
            )
            opcoes_tarefas = dict(zip(df_all_t["label"], df_all_t["id"]))
            sel_label = st.selectbox("Selecione a tarefa que deseja alterar:", list(opcoes_tarefas.keys()))
            task_id = opcoes_tarefas[sel_label]
            task_row = df_all_t[df_all_t["id"] == task_id].iloc[0]

            st.markdown(f"#### Editando Dados da Tarefa #{task_id}")
            with st.form("form_edicao_lancamento"):
                ed1, ed2 = st.columns(2)
                with ed1:
                    novo_titulo = st.text_input("Título *", value=task_row["title"])
                    nova_desc = st.text_area("Descrição / Detalhes", value=task_row["description"] if task_row["description"] else "")
                    lista_projs = list(p_options.keys())
                    proj_atual_nome = task_row["project_name"] if task_row["project_name"] in lista_projs else "Nenhum (Tarefa Avulsa)"
                    novo_p_nome = st.selectbox("Mini Projeto Vinculado", lista_projs, index=lista_projs.index(proj_atual_nome))

                with ed2:
                    novo_resp = st.selectbox("Responsável *", MEMBERS, index=MEMBERS.index(task_row["responsible"]) if task_row["responsible"] in MEMBERS else 0)
                    idx_cat = categories_list.index(task_row["category"]) if task_row["category"] in categories_list else 0
                    nova_cat = st.selectbox("Área / Categoria", categories_list, index=idx_cat)
                    dt_atual_venc = pd.to_datetime(task_row["due_date"]).date()
                    novo_venc = st.date_input("Prazo Limite *", value=dt_atual_venc)
                    nova_prio = st.selectbox("Prioridade", PRIORITIES, index=PRIORITIES.index(task_row["priority"]) if task_row["priority"] in PRIORITIES else 1)
                    novo_st = st.selectbox("Status", STATUS_OPTIONS, index=STATUS_OPTIONS.index(task_row["status"]) if task_row["status"] in STATUS_OPTIONS else 0)

                if st.form_submit_button("💾 Salvar Alterações", type="primary", use_container_width=True):
                    if novo_titulo.strip():
                        cur = conn.cursor()
                        cur.execute("""
                            UPDATE tasks 
                            SET title = ?, description = ?, project_id = ?, responsible = ?, category = ?, due_date = ?, status = ?, priority = ?
                            WHERE id = ?
                        """, (novo_titulo.strip(), nova_desc.strip(), p_options[novo_p_nome], novo_resp, nova_cat, str(novo_venc), novo_st, nova_prio, task_id))
                        conn.commit()
                        st.success(f"Tarefa #{task_id} atualizada com sucesso!")
                        st.rerun()
                    else:
                        st.error("O título não pode ficar em branco.")

    elif tela_ativa == "    └─ 🗑️ Exclusão de Tarefa":
        st.title("🗑️ Exclusão de Tarefas")
        st.caption("Remova tarefas com confirmação de segurança")

        df_del_t = pd.read_sql_query("SELECT id, due_date, title, responsible, status FROM tasks ORDER BY id DESC", conn)

        if df_del_t.empty:
            st.info("Nenhuma tarefa disponível para exclusão.")
        else:
            df_del_t["label"] = df_del_t.apply(
                lambda r: f"Cód. {r['id']} | {r['due_date']} | {r['title']} ({r['responsible']})", axis=1
            )
            del_dict = dict(zip(df_del_t["label"], df_del_t["id"]))
            sel_del_label = st.selectbox("Selecione a tarefa para exclusão definitiva:", list(del_dict.keys()))
            del_id = del_dict[sel_del_label]

            st.warning(f"Atenção: A exclusão da tarefa **Cód. #{del_id}** é permanente.")
            check_confirma = st.checkbox("Confirmo que desejo apagar esta tarefa definitivamente.", key=f"chk_del_{del_id}")

            if st.button("🚨 Confirmar Exclusão", type="primary"):
                if check_confirma:
                    cur = conn.cursor()
                    cur.execute("DELETE FROM tasks WHERE id = ?", (del_id,))
                    conn.commit()
                    st.success(f"Tarefa #{del_id} excluída com sucesso!")
                    st.rerun()
                else:
                    st.error("Marque a caixa de confirmação para validar a exclusão.")

    # =========================================================================
    # 3. MANUTENÇÃO (SUBORDINADOS)
    # =========================================================================
    elif tela_ativa == "    └─ 📁 Mini Projetos":
        st.title("📁 Manutenção de Mini Projetos")
        st.caption("Cadastre agrupamentos de tarefas com metas pontuais do escritório")

        tab_novo_p, tab_lista_p = st.tabs(["➕ Novo Mini Projeto", "📋 Mini Projetos Cadastrados"])

        with tab_novo_p:
            with st.form("form_cad_mini_proj", clear_on_submit=True):
                p_name = st.text_input("Nome do Mini Projeto *", placeholder="Ex: Configurar o site")
                p_desc = st.text_area("Objetivo / Escopo do Projeto", placeholder="Metas e entregas...")
                if st.form_submit_button("Salvar Mini Projeto", type="primary"):
                    if p_name.strip():
                        try:
                            cur = conn.cursor()
                            cur.execute("INSERT INTO mini_projects (name, description) VALUES (?, ?)", (p_name.strip(), p_desc.strip()))
                            conn.commit()
                            st.success(f"Mini Projeto '{p_name}' criado!")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Já existe um mini projeto com este nome.")
                    else:
                        st.error("Informe o nome do projeto.")

        with tab_lista_p:
            df_p_list = pd.read_sql_query("SELECT id, name, description, created_at FROM mini_projects ORDER BY name ASC", conn)
            if df_p_list.empty:
                st.info("Nenhum mini projeto cadastrado.")
            else:
                st.dataframe(
                    df_p_list,
                    column_config={
                        "id": "Cód.",
                        "name": "Projeto",
                        "description": "Descrição",
                        "created_at": "Criação"
                    },
                    hide_index=True,
                    use_container_width=True
                )

    elif tela_ativa == "    └─ 🏷️ Áreas / Categorias":
        st.title("🏷️ Manutenção de Áreas / Categorias")
        st.caption("Gerencie as categorias de classificação utilizadas nas tarefas do escritório")

        tab_nova_cat, tab_lista_cat = st.tabs(["➕ Nova Área / Categoria", "📋 Categorias Cadastradas"])

        with tab_nova_cat:
            with st.form("form_cad_categoria", clear_on_submit=True):
                cat_name = st.text_input("Nome da Área / Categoria *", placeholder="Ex: Tributário, Direito Médico, Administrativo")
                if st.form_submit_button("Salvar Categoria", type="primary"):
                    if cat_name.strip():
                        try:
                            cur = conn.cursor()
                            cur.execute("INSERT INTO task_categories (name) VALUES (?)", (cat_name.strip(),))
                            conn.commit()
                            st.success(f"Categoria '{cat_name}' cadastrada com sucesso!")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Essa categoria já existe no sistema.")
                    else:
                        st.error("Informe o nome da categoria.")

        with tab_lista_cat:
            df_cat_list = pd.read_sql_query("SELECT id, name, created_at FROM task_categories ORDER BY name ASC", conn)
            if df_cat_list.empty:
                st.info("Nenhuma categoria cadastrada.")
            else:
                st.dataframe(
                    df_cat_list,
                    column_config={
                        "id": "Cód.",
                        "name": "Área / Categoria",
                        "created_at": "Data de Criação"
                    },
                    hide_index=True,
                    use_container_width=True
                )

    elif tela_ativa == "    └─ 📑 Histórico & Exportação":
        st.title("📑 Histórico Geral de Tarefas")
        st.caption("Relatório consolidado e auditoria de obrigações")

        q_rel = """
            SELECT t.id, t.title, t.responsible, t.category, t.due_date, t.status, t.priority,
                   COALESCE(p.name, 'Sem Projeto') AS project_name
            FROM tasks t
            LEFT JOIN mini_projects p ON t.project_id = p.id
            ORDER BY t.due_date DESC
        """
        df_rel = pd.read_sql_query(q_rel, conn)

        if df_rel.empty:
            st.info("Nenhum registro no histórico de tarefas.")
        else:
            st.dataframe(
                df_rel,
                column_config={
                    "id": "Cód.",
                    "title": "Título",
                    "responsible": "Responsável",
                    "category": "Área",
                    "due_date": "Prazo",
                    "status": "Situação",
                    "priority": "Prioridade",
                    "project_name": "Mini Projeto"
                },
                hide_index=True,
                use_container_width=True
            )
            csv_tarefas = df_rel.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Exportar Base Completa em CSV",
                data=csv_tarefas,
                file_name=f"tarefas_escritorio_{today}.csv",
                mime="text/csv"
            )