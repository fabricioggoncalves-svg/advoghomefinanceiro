import streamlit as st
import pandas as pd
import sqlite3
import io
import calendar
import hashlib
from datetime import date, datetime, timedelta, time

# ----------------------------------------------------
# CONFIGURAÇÃO GERAL
# ----------------------------------------------------
st.set_page_config(page_title="Fabíola Guimarães Advocacia", layout="wide", page_icon="⚖️")
DB_NAME = "financeiro.db"
SOCIOS = ["Fabrício", "Fabíola"]

# ----------------------------------------------------
# SEGURANÇA E CRIPTOGRAFIA DE SENHAS
# ----------------------------------------------------
def hash_senha(senha: str) -> str:
    return hashlib.sha256(str(senha).strip().encode("utf-8")).hexdigest()

# ----------------------------------------------------
# UTILITÁRIOS DE FORMATAÇÃO DE DATA E HORA
# ----------------------------------------------------
def formatar_data_br(val):
    if pd.isna(val) or not val:
        return ""
    str_val = str(val).strip()
    if "/" in str_val:
        return str_val
    try:
        dt = datetime.strptime(str_val[:10], "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str_val

def parse_data_iso(val):
    if not val:
        return date.today()
    if isinstance(val, date):
        return val
    str_val = str(val).strip()
    try:
        if "/" in str_val:
            return datetime.strptime(str_val, "%d/%m/%Y").date()
        return datetime.strptime(str_val[:10], "%Y-%m-%d").date()
    except Exception:
        return date.today()

def parse_hora_str(val):
    if not val:
        return time(9, 0)
    if isinstance(val, time):
        return val
    try:
        return datetime.strptime(str(val)[:5], "%H:%M").time()
    except Exception:
        return time(9, 0)

def calcular_proxima_data(data_base: date, frequencia: str, intervalo: int = 1) -> date:
    if frequencia == "Diária":
        return data_base + timedelta(days=intervalo)
    elif frequencia == "Semanal":
        return data_base + timedelta(weeks=intervalo)
    elif frequencia == "Mensal":
        ano = data_base.year + (data_base.month + intervalo - 1) // 12
        mes = (data_base.month + intervalo - 1) % 12 + 1
        dia = min(data_base.day, calendar.monthrange(ano, mes)[1])
        return date(ano, mes, dia)
    elif frequencia == "Anual":
        ano = data_base.year + intervalo
        dia = min(data_base.day, calendar.monthrange(ano, data_base.month)[1])
        return date(ano, data_base.month, dia)
    return data_base + timedelta(days=intervalo)

# ----------------------------------------------------
# BANCO DE DADOS (SQLite)
# ----------------------------------------------------
def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # 0. Usuários
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL,
            perfil TEXT CHECK(perfil IN ('Administrador', 'Advogado', 'Assistente')) DEFAULT 'Advogado',
            ativo INTEGER DEFAULT 1
        )
    """)
    
    c.execute("PRAGMA table_info(usuarios)")
    cols_u = [info[1] for info in c.fetchall()]
    if "senha_hash" not in cols_u:
        c.execute("ALTER TABLE usuarios ADD COLUMN senha_hash TEXT")

    senha_padrao_hash = hash_senha("123456")

    # Garante a existência dos usuários padrões e repara senhas vazias ou nulas
    usuarios_padrao = [
        ("Dra. Fabíola Guimarães", "fabiola@advocacia.com.br", senha_padrao_hash, "Administrador"),
        ("Fabrício Gonçalves", "fabricio@advocacia.com.br", senha_padrao_hash, "Administrador")
    ]

    for nome, email, shash, perfil in usuarios_padrao:
        c.execute("SELECT id, senha_hash FROM usuarios WHERE LOWER(email) = LOWER(?)", (email,))
        row = c.fetchone()
        if not row:
            c.execute("INSERT INTO usuarios (nome, email, senha_hash, perfil, ativo) VALUES (?, ?, ?, ?, 1)",
                      (nome, email.lower(), shash, perfil))
        else:
            # Se o usuário existe mas está sem senha ou nulo, corrige
            if not row[1]:
                c.execute("UPDATE usuarios SET senha_hash = ?, ativo = 1 WHERE id = ?", (shash, row[0]))

    # 1. Contatos
    c.execute("""
        CREATE TABLE IF NOT EXISTS contatos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            tipo TEXT CHECK(tipo IN ('Cliente', 'Fornecedor')) NOT NULL
        )
    """)
    
    # 2. Histórico Padrão
    c.execute("""
        CREATE TABLE IF NOT EXISTS historicos_padrao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            descricao TEXT NOT NULL,
            tipo_aplicavel TEXT CHECK(tipo_aplicavel IN ('Receita', 'Despesa', 'Ambos')) NOT NULL
        )
    """)

    # 3. Contas Sintéticas
    c.execute("""
        CREATE TABLE IF NOT EXISTS contas_sinteticas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT CHECK(tipo IN ('Receita', 'Despesa')) NOT NULL,
            nome TEXT NOT NULL,
            UNIQUE(tipo, nome)
        )
    """)

    # 4. Contas Analíticas
    c.execute("""
        CREATE TABLE IF NOT EXISTS contas_analiticas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sintetica_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            historico_padrao_id INTEGER,
            UNIQUE(sintetica_id, nome),
            FOREIGN KEY (sintetica_id) REFERENCES contas_sinteticas(id) ON DELETE CASCADE,
            FOREIGN KEY (historico_padrao_id) REFERENCES historicos_padrao(id)
        )
    """)

    # 5. Contas Recorrentes Financeiras
    c.execute("""
        CREATE TABLE IF NOT EXISTS contas_recorrentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            contato_id INTEGER,
            conta_analitica_id INTEGER NOT NULL,
            historico_id INTEGER,
            valor REAL DEFAULT 0.0,
            dia_vencimento INTEGER NOT NULL CHECK(dia_vencimento BETWEEN 1 AND 31),
            complemento_padrao TEXT,
            pago_por_padrao TEXT,
            FOREIGN KEY (contato_id) REFERENCES contatos(id),
            FOREIGN KEY (conta_analitica_id) REFERENCES contas_analiticas(id),
            FOREIGN KEY (historico_id) REFERENCES historicos_padrao(id)
        )
    """)

    # 6. Regras de Classificação
    c.execute("""
        CREATE TABLE IF NOT EXISTS regras_classificacao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            padrao_texto TEXT NOT NULL UNIQUE,
            tipo TEXT CHECK(tipo IN ('Receita', 'Despesa')) NOT NULL,
            sintetica_id INTEGER NOT NULL,
            analitica_id INTEGER NOT NULL,
            historico_id INTEGER,
            FOREIGN KEY (sintetica_id) REFERENCES contas_sinteticas(id),
            FOREIGN KEY (analitica_id) REFERENCES contas_analiticas(id),
            FOREIGN KEY (historico_id) REFERENCES historicos_padrao(id)
        )
    """)
    
    # 7. Lançamentos Financeiros
    c.execute("""
        CREATE TABLE IF NOT EXISTS lancamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT CHECK(tipo IN ('Receita', 'Despesa')) NOT NULL,
            data_vencimento TEXT NOT NULL,
            data_pagamento TEXT,
            valor REAL NOT NULL,
            contato_id INTEGER,
            historico_id INTEGER,
            conta_analitica_id INTEGER,
            complemento TEXT,
            status TEXT DEFAULT 'Pendente',
            pago_por TEXT,
            recorrente_id INTEGER,
            mes_referencia TEXT,
            FOREIGN KEY (contato_id) REFERENCES contatos(id),
            FOREIGN KEY (historico_id) REFERENCES historicos_padrao(id),
            FOREIGN KEY (conta_analitica_id) REFERENCES contas_analiticas(id),
            FOREIGN KEY (recorrente_id) REFERENCES contas_recorrentes(id)
        )
    """)

    # 8. Tipos de Tarefas
    c.execute("""
        CREATE TABLE IF NOT EXISTS tipos_tarefas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE
        )
    """)
    c.execute("SELECT COUNT(*) FROM tipos_tarefas")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO tipos_tarefas (nome) VALUES (?)", [("Trabalho",), ("Particular",), ("Audiência",), ("Prazo Processual",)])

    # 9. Grupo de Tarefas - Nível 1
    c.execute("""
        CREATE TABLE IF NOT EXISTS grupos_tarefas_n1 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE
        )
    """)
    c.execute("SELECT COUNT(*) FROM grupos_tarefas_n1")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO grupos_tarefas_n1 (nome) VALUES (?)", [("Contencioso Cível",), ("Consultoria",), ("Pessoal / Administrativo",)])

    # 10. Grupo de Tarefas - Nível 2
    c.execute("""
        CREATE TABLE IF NOT EXISTS grupos_tarefas_n2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo_n1_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            UNIQUE(grupo_n1_id, nome),
            FOREIGN KEY (grupo_n1_id) REFERENCES grupos_tarefas_n1(id) ON DELETE CASCADE
        )
    """)
    c.execute("SELECT COUNT(*) FROM grupos_tarefas_n2")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO grupos_tarefas_n2 (grupo_n1_id, nome) VALUES (1, 'Recursos e Apelações')")
        c.execute("INSERT INTO grupos_tarefas_n2 (grupo_n1_id, nome) VALUES (1, 'Petições Iniciais')")
        c.execute("INSERT INTO grupos_tarefas_n2 (grupo_n1_id, nome) VALUES (2, 'Pareceres e Contratos')")
        c.execute("INSERT INTO grupos_tarefas_n2 (grupo_n1_id, nome) VALUES (3, 'Rotinas do Escritório')")

    # 11. Tarefas Recorrentes
    c.execute("""
        CREATE TABLE IF NOT EXISTS tarefas_recorrentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            descricao TEXT,
            frequencia TEXT CHECK(frequencia IN ('Diária', 'Semanal', 'Mensal', 'Anual')) NOT NULL,
            intervalo INTEGER DEFAULT 1,
            data_inicio TEXT NOT NULL,
            proxima_execucao TEXT NOT NULL,
            prioridade TEXT CHECK(prioridade IN ('Baixa', 'Média', 'Alta', 'Urgente')) DEFAULT 'Média',
            responsavel_id INTEGER,
            cliente_id INTEGER,
            processo_ref TEXT,
            tipo_tarefa_id INTEGER,
            subgrupo_id INTEGER,
            criador_id INTEGER,
            visibilidade TEXT CHECK(visibilidade IN ('Privada', 'Compartilhada')) DEFAULT 'Compartilhada',
            ativo INTEGER DEFAULT 1,
            FOREIGN KEY (responsavel_id) REFERENCES usuarios(id),
            FOREIGN KEY (cliente_id) REFERENCES contatos(id),
            FOREIGN KEY (tipo_tarefa_id) REFERENCES tipos_tarefas(id),
            FOREIGN KEY (subgrupo_id) REFERENCES grupos_tarefas_n2(id),
            FOREIGN KEY (criador_id) REFERENCES usuarios(id)
        )
    """)

    # 12. Tarefas
    c.execute("""
        CREATE TABLE IF NOT EXISTS tarefas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            descricao TEXT,
            data_limite TEXT,
            prioridade TEXT CHECK(prioridade IN ('Baixa', 'Média', 'Alta', 'Urgente')) DEFAULT 'Média',
            status TEXT CHECK(status IN ('Não Iniciada', 'Em Andamento', 'Concluída', 'Cancelada')) DEFAULT 'Não Iniciada',
            responsavel_id INTEGER,
            cliente_id INTEGER,
            processo_ref TEXT,
            tipo_tarefa_id INTEGER,
            subgrupo_id INTEGER,
            criador_id INTEGER,
            visibilidade TEXT CHECK(visibilidade IN ('Privada', 'Compartilhada')) DEFAULT 'Compartilhada',
            recorrente_origem_id INTEGER,
            criado_em TEXT,
            FOREIGN KEY (responsavel_id) REFERENCES usuarios(id),
            FOREIGN KEY (cliente_id) REFERENCES contatos(id),
            FOREIGN KEY (tipo_tarefa_id) REFERENCES tipos_tarefas(id),
            FOREIGN KEY (subgrupo_id) REFERENCES grupos_tarefas_n2(id),
            FOREIGN KEY (criador_id) REFERENCES usuarios(id),
            FOREIGN KEY (recorrente_origem_id) REFERENCES tarefas_recorrentes(id) ON DELETE SET NULL
        )
    """)

    # 13. Compartilhamento Específico de Tarefas
    c.execute("""
        CREATE TABLE IF NOT EXISTS tarefas_compartilhadas (
            tarefa_id INTEGER NOT NULL,
            usuario_id INTEGER NOT NULL,
            PRIMARY KEY (tarefa_id, usuario_id),
            FOREIGN KEY (tarefa_id) REFERENCES tarefas(id) ON DELETE CASCADE,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )
    """)

    # 14. Compromissos na Agenda
    c.execute("""
        CREATE TABLE IF NOT EXISTS compromissos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            descricao TEXT,
            data_inicio TEXT NOT NULL,
            hora_inicio TEXT,
            data_fim TEXT NOT NULL,
            hora_fim TEXT,
            dia_inteiro INTEGER DEFAULT 0,
            local_link TEXT,
            cliente_id INTEGER,
            processo_ref TEXT,
            organizador_id INTEGER NOT NULL,
            visibilidade TEXT CHECK(visibilidade IN ('Privada', 'Compartilhada')) DEFAULT 'Compartilhada',
            criado_em TEXT,
            FOREIGN KEY (cliente_id) REFERENCES contatos(id),
            FOREIGN KEY (organizador_id) REFERENCES usuarios(id)
        )
    """)

    # 15. Participantes do Compromisso
    c.execute("""
        CREATE TABLE IF NOT EXISTS compromissos_participantes (
            compromisso_id INTEGER NOT NULL,
            usuario_id INTEGER NOT NULL,
            PRIMARY KEY (compromisso_id, usuario_id),
            FOREIGN KEY (compromisso_id) REFERENCES compromissos(id) ON DELETE CASCADE,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()

# --- Funções: Usuários e Autenticação ---
def autenticar_usuario(email, senha):
    conn = get_connection()
    c = conn.cursor()
    email_limpo = str(email).strip().lower()
    s_hash = hash_senha(senha)
    c.execute("SELECT id, nome, email, perfil, ativo FROM usuarios WHERE LOWER(TRIM(email)) = ? AND senha_hash = ?", (email_limpo, s_hash))
    user = c.fetchone()
    conn.close()
    if user and user[4] == 1:
        return {"id": user[0], "nome": user[1], "email": user[2], "perfil": user[3]}
    return None

def resetar_senha_padrao_admin(email):
    conn = get_connection()
    c = conn.cursor()
    s_hash = hash_senha("123456")
    c.execute("UPDATE usuarios SET senha_hash = ?, ativo = 1 WHERE LOWER(TRIM(email)) = LOWER(TRIM(?))", (s_hash, email))
    conn.commit()
    afetados = c.rowcount
    conn.close()
    return afetados > 0

def alterar_senha_usuario(usuario_id, nova_senha):
    conn = get_connection()
    c = conn.cursor()
    s_hash = hash_senha(nova_senha)
    c.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (s_hash, usuario_id))
    conn.commit()
    conn.close()
    return True

def get_usuarios(apenas_ativos=False):
    conn = get_connection()
    query = "SELECT id, nome, email, perfil, ativo FROM usuarios"
    if apenas_ativos:
        query += " WHERE ativo = 1"
    query += " ORDER BY nome ASC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def add_usuario(nome, email, senha, perfil):
    conn = get_connection()
    c = conn.cursor()
    s_hash = hash_senha(senha)
    try:
        c.execute("INSERT INTO usuarios (nome, email, senha_hash, perfil, ativo) VALUES (?, ?, ?, ?, 1)", 
                  (nome.strip(), email.strip().lower(), s_hash, perfil))
        conn.commit()
        sucesso = True
    except sqlite3.IntegrityError:
        sucesso = False
    finally:
        conn.close()
    return sucesso

def update_usuario(usuario_id, nome, email, perfil, ativo, nova_senha=None):
    conn = get_connection()
    c = conn.cursor()
    try:
        if nova_senha and str(nova_senha).strip():
            s_hash = hash_senha(nova_senha)
            c.execute("UPDATE usuarios SET nome = ?, email = ?, perfil = ?, ativo = ?, senha_hash = ? WHERE id = ?", 
                      (nome.strip(), email.strip().lower(), perfil, ativo, s_hash, usuario_id))
        else:
            c.execute("UPDATE usuarios SET nome = ?, email = ?, perfil = ?, ativo = ? WHERE id = ?", 
                      (nome.strip(), email.strip().lower(), perfil, ativo, usuario_id))
        conn.commit()
        sucesso = True
    except sqlite3.IntegrityError:
        sucesso = False
    finally:
        conn.close()
    return sucesso

def delete_usuario(usuario_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE tarefas SET responsavel_id = NULL WHERE responsavel_id = ?", (usuario_id,))
    c.execute("DELETE FROM tarefas_compartilhadas WHERE usuario_id = ?", (usuario_id,))
    c.execute("DELETE FROM compromissos_participantes WHERE usuario_id = ?", (usuario_id,))
    c.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    conn.commit()
    conn.close()

# --- Funções: Tipos de Tarefas ---
def get_tipos_tarefas():
    conn = get_connection()
    df = pd.read_sql_query("SELECT id, nome FROM tipos_tarefas ORDER BY nome ASC", conn)
    conn.close()
    return df

def add_tipo_tarefa(nome):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO tipos_tarefas (nome) VALUES (?)", (nome.strip(),))
        conn.commit()
        sucesso = True
    except sqlite3.IntegrityError:
        sucesso = False
    finally:
        conn.close()
    return sucesso

def update_tipo_tarefa(tipo_id, nome):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("UPDATE tipos_tarefas SET nome = ? WHERE id = ?", (nome.strip(), tipo_id))
        conn.commit()
        sucesso = True
    except sqlite3.IntegrityError:
        sucesso = False
    finally:
        conn.close()
    return sucesso

def delete_tipo_tarefa(tipo_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE tarefas SET tipo_tarefa_id = NULL WHERE tipo_tarefa_id = ?", (tipo_id,))
    c.execute("DELETE FROM tipos_tarefas WHERE id = ?", (tipo_id,))
    conn.commit()
    conn.close()

# --- Funções: Grupos e Subgrupos de Tarefas ---
def get_grupos_tarefas_n1():
    conn = get_connection()
    df = pd.read_sql_query("SELECT id, nome FROM grupos_tarefas_n1 ORDER BY nome ASC", conn)
    conn.close()
    return df

def add_grupo_tarefas_n1(nome):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO grupos_tarefas_n1 (nome) VALUES (?)", (nome.strip(),))
        conn.commit()
        sucesso = True
    except sqlite3.IntegrityError:
        sucesso = False
    finally:
        conn.close()
    return sucesso

def update_grupo_tarefas_n1(n1_id, nome):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("UPDATE grupos_tarefas_n1 SET nome = ? WHERE id = ?", (nome.strip(), n1_id))
        conn.commit()
        sucesso = True
    except sqlite3.IntegrityError:
        sucesso = False
    finally:
        conn.close()
    return sucesso

def delete_grupo_tarefas_n1(n1_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE tarefas SET subgrupo_id = NULL WHERE subgrupo_id IN (SELECT id FROM grupos_tarefas_n2 WHERE grupo_n1_id = ?)", (n1_id,))
    c.execute("DELETE FROM grupos_tarefas_n2 WHERE grupo_n1_id = ?", (n1_id,))
    c.execute("DELETE FROM grupos_tarefas_n1 WHERE id = ?", (n1_id,))
    conn.commit()
    conn.close()

def get_grupos_tarefas_n2():
    conn = get_connection()
    query = """
        SELECT 
            n2.id,
            n1.id AS grupo_n1_id,
            n1.nome AS grupo_n1,
            n2.nome AS subgrupo_n2,
            n1.nome || ' ➔ ' || n2.nome AS caminho_completo
        FROM grupos_tarefas_n2 n2
        JOIN grupos_tarefas_n1 n1 ON n2.grupo_n1_id = n1.id
        ORDER BY n1.nome, n2.nome ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def add_grupo_tarefas_n2(grupo_n1_id, nome):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO grupos_tarefas_n2 (grupo_n1_id, nome) VALUES (?, ?)", (grupo_n1_id, nome.strip()))
        conn.commit()
        sucesso = True
    except sqlite3.IntegrityError:
        sucesso = False
    finally:
        conn.close()
    return sucesso

def update_grupo_tarefas_n2(n2_id, grupo_n1_id, nome):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("UPDATE grupos_tarefas_n2 SET grupo_n1_id = ?, nome = ? WHERE id = ?", (grupo_n1_id, nome.strip(), n2_id))
        conn.commit()
        sucesso = True
    except sqlite3.IntegrityError:
        sucesso = False
    finally:
        conn.close()
    return sucesso

def delete_grupo_tarefas_n2(n2_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE tarefas SET subgrupo_id = NULL WHERE subgrupo_id = ?", (n2_id,))
    c.execute("DELETE FROM grupos_tarefas_n2 WHERE id = ?", (n2_id,))
    conn.commit()
    conn.close()

# --- Funções: Tarefas & Compartilhamento ---
def get_tarefas_df(usuario_logado_id=None):
    conn = get_connection()
    query = """
        SELECT DISTINCT
            t.id,
            t.titulo,
            tt.nome AS tipo_tarefa,
            t.tipo_tarefa_id,
            gn1.nome AS grupo_tarefa,
            gn2.nome AS subgrupo_tarefa,
            t.subgrupo_id,
            t.data_limite,
            t.prioridade,
            t.status,
            u.nome AS responsavel,
            t.responsavel_id,
            c.nome AS cliente,
            t.cliente_id,
            t.processo_ref,
            t.descricao,
            t.visibilidade,
            t.recorrente_origem_id,
            criador.nome AS criador,
            t.criador_id,
            t.criado_em
        FROM tarefas t
        LEFT JOIN tipos_tarefas tt ON t.tipo_tarefa_id = tt.id
        LEFT JOIN grupos_tarefas_n2 gn2 ON t.subgrupo_id = gn2.id
        LEFT JOIN grupos_tarefas_n1 gn1 ON gn2.grupo_n1_id = gn1.id
        LEFT JOIN usuarios u ON t.responsavel_id = u.id
        LEFT JOIN usuarios criador ON t.criador_id = criador.id
        LEFT JOIN contatos c ON t.cliente_id = c.id
        LEFT JOIN tarefas_compartilhadas tc ON t.id = tc.tarefa_id
    """
    params = ()
    if usuario_logado_id:
        query += """
            WHERE (
                t.visibilidade = 'Compartilhada' 
                OR t.criador_id = ? 
                OR t.responsavel_id = ? 
                OR tc.usuario_id = ?
            )
        """
        params = (usuario_logado_id, usuario_logado_id, usuario_logado_id)
        
    query += """
        ORDER BY 
            CASE t.status 
                WHEN 'Não Iniciada' THEN 1 
                WHEN 'Em Andamento' THEN 2 
                WHEN 'Concluída' THEN 3 
                ELSE 4 
            END,
            t.data_limite ASC
    """
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def get_usuarios_compartilhados(tarefa_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT usuario_id FROM tarefas_compartilhadas WHERE tarefa_id = ?", (tarefa_id,))
    ids = [row[0] for row in c.fetchall()]
    conn.close()
    return ids

def set_usuarios_compartilhados(tarefa_id, usuario_ids):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM tarefas_compartilhadas WHERE tarefa_id = ?", (tarefa_id,))
    for u_id in usuario_ids:
        c.execute("INSERT OR IGNORE INTO tarefas_compartilhadas (tarefa_id, usuario_id) VALUES (?, ?)", (tarefa_id, u_id))
    conn.commit()
    conn.close()

def add_tarefa(titulo, descricao, data_limite, prioridade, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade, usuarios_compartilhados=None, recorrente_origem_id=None):
    conn = get_connection()
    c = conn.cursor()
    criado_em = date.today().strftime("%Y-%m-%d")
    c.execute("""
        INSERT INTO tarefas (titulo, descricao, data_limite, prioridade, status, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade, recorrente_origem_id, criado_em)
        VALUES (?, ?, ?, ?, 'Não Iniciada', ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (titulo, descricao, str(data_limite), prioridade, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade, recorrente_origem_id, criado_em))
    tarefa_id = c.lastrowid
    conn.commit()
    conn.close()
    
    if visibilidade == "Compartilhada" and usuarios_compartilhados:
        set_usuarios_compartilhados(tarefa_id, usuarios_compartilhados)
    return tarefa_id

def update_tarefa(tarefa_id, titulo, descricao, data_limite, prioridade, status, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, visibilidade, usuarios_compartilhados=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE tarefas 
        SET titulo = ?, descricao = ?, data_limite = ?, prioridade = ?, status = ?, responsavel_id = ?, cliente_id = ?, processo_ref = ?, tipo_tarefa_id = ?, subgrupo_id = ?, visibilidade = ?
        WHERE id = ?
    """, (titulo, descricao, str(data_limite), prioridade, status, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, visibilidade, tarefa_id))
    conn.commit()
    conn.close()
    
    if visibilidade == "Compartilhada" and usuarios_compartilhados is not None:
        set_usuarios_compartilhados(tarefa_id, usuarios_compartilhados)
    
    if status == "Concluído" or status == "Concluída":
        processar_conclusao_recorrente(tarefa_id)

def delete_tarefa(tarefa_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM tarefas_compartilhadas WHERE tarefa_id = ?", (tarefa_id,))
    c.execute("DELETE FROM tarefas WHERE id = ?", (tarefa_id,))
    conn.commit()
    conn.close()

# --- Funções: Tarefas Recorrentes ---
def get_tarefas_recorrentes():
    conn = get_connection()
    query = """
        SELECT 
            tr.id,
            tr.titulo,
            tr.frequencia,
            tr.intervalo,
            tr.data_inicio,
            tr.proxima_execucao,
            tr.prioridade,
            tr.visibilidade,
            tr.ativo,
            u.nome AS responsavel,
            tr.responsavel_id,
            c.nome AS cliente,
            tr.cliente_id,
            tt.nome AS tipo_tarefa,
            tr.tipo_tarefa_id,
            gn2.nome AS subgrupo_tarefa,
            tr.subgrupo_id,
            tr.descricao,
            tr.processo_ref
        FROM tarefas_recorrentes tr
        LEFT JOIN usuarios u ON tr.responsavel_id = u.id
        LEFT JOIN contatos c ON tr.cliente_id = c.id
        LEFT JOIN tipos_tarefas tt ON tr.tipo_tarefa_id = tt.id
        LEFT JOIN grupos_tarefas_n2 gn2 ON tr.subgrupo_id = gn2.id
        ORDER BY tr.proxima_execucao ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def add_tarefa_recorrente(titulo, descricao, frequencia, intervalo, data_inicio, prioridade, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO tarefas_recorrentes (
            titulo, descricao, frequencia, intervalo, data_inicio, proxima_execucao, prioridade,
            responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade, ativo
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (titulo, descricao, frequencia, intervalo, str(data_inicio), str(data_inicio), prioridade, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade))
    rec_id = c.lastrowid
    conn.commit()
    conn.close()
    
    add_tarefa(
        titulo=titulo,
        descricao=descricao,
        data_limite=data_inicio,
        prioridade=prioridade,
        responsavel_id=responsavel_id,
        cliente_id=cliente_id,
        processo_ref=processo_ref,
        tipo_tarefa_id=tipo_tarefa_id,
        subgrupo_id=subgrupo_id,
        criador_id=criador_id,
        visibilidade=visibilidade,
        recorrente_origem_id=rec_id
    )
    return rec_id

def update_tarefa_recorrente(rec_id, titulo, descricao, frequencia, intervalo, prioridade, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, visibilidade, ativo):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE tarefas_recorrentes
        SET titulo = ?, descricao = ?, frequencia = ?, intervalo = ?, prioridade = ?,
            responsavel_id = ?, cliente_id = ?, processo_ref = ?, tipo_tarefa_id = ?, subgrupo_id = ?, visibilidade = ?, ativo = ?
        WHERE id = ?
    """, (titulo, descricao, frequencia, intervalo, prioridade, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, visibilidade, ativo, rec_id))
    conn.commit()
    conn.close()

def delete_tarefa_recorrente(rec_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM tarefas_recorrentes WHERE id = ?", (rec_id,))
    conn.commit()
    conn.close()

def processar_conclusao_recorrente(tarefa_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT recorrente_origem_id, data_limite FROM tarefas WHERE id = ?", (tarefa_id,))
    row = c.fetchone()
    if not row or not row[0]:
        conn.close()
        return
    
    rec_id = row[0]
    data_limite_base = parse_data_iso(row[1])
    
    c.execute("SELECT frequencia, intervalo, ativo, titulo, descricao, prioridade, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade FROM tarefas_recorrentes WHERE id = ?", (rec_id,))
    regra = c.fetchone()
    if not regra or regra[2] != 1:
        conn.close()
        return
    
    freq, intervalo, ativo, tit, desc, prio, resp_id, cli_id, proc, tipo_t, subg, criador, vis = regra
    nova_data = calcular_proxima_data(data_limite_base, freq, intervalo)
    
    c.execute("UPDATE tarefas_recorrentes SET proxima_execucao = ? WHERE id = ?", (str(nova_data), rec_id))
    conn.commit()
    conn.close()
    
    add_tarefa(
        titulo=tit,
        descricao=desc,
        data_limite=nova_data,
        prioridade=prio,
        responsavel_id=resp_id,
        cliente_id=cli_id,
        processo_ref=proc,
        tipo_tarefa_id=tipo_t,
        subgrupo_id=subg,
        criador_id=criador,
        visibilidade=vis,
        recorrente_origem_id=rec_id
    )

def sincronizar_tarefas_recorrentes():
    conn = get_connection()
    hoje_iso = str(date.today())
    c = conn.cursor()
    c.execute("""
        SELECT id, titulo, descricao, frequencia, intervalo, proxima_execucao, prioridade,
               responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade
        FROM tarefas_recorrentes
        WHERE ativo = 1 AND proxima_execucao <= ?
    """, (hoje_iso,))
    recorrentes = c.fetchall()
    
    criados = 0
    for r in recorrentes:
        rec_id, tit, desc, freq, interv, prox_exec, prio, resp_id, cli_id, proc, tipo_t, subg, criador, vis = r
        c.execute("SELECT COUNT(*) FROM tarefas WHERE recorrente_origem_id = ? AND data_limite = ?", (rec_id, prox_exec))
        if c.fetchone()[0] == 0:
            c.execute("""
                INSERT INTO tarefas (titulo, descricao, data_limite, prioridade, status, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade, recorrente_origem_id, criado_em)
                VALUES (?, ?, ?, ?, 'Não Iniciada', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (tit, desc, prox_exec, prio, resp_id, cli_id, proc, tipo_t, subg, criador, vis, rec_id, hoje_iso))
            criados += 1
    conn.commit()
    conn.close()
    return criados

# --- Funções: Compromissos na Agenda ---
def get_compromissos_df(usuario_logado_id=None):
    conn = get_connection()
    query = """
        SELECT DISTINCT
            cp.id,
            cp.titulo,
            cp.data_inicio,
            cp.hora_inicio,
            cp.data_fim,
            cp.hora_fim,
            cp.dia_inteiro,
            cp.local_link,
            cp.descricao,
            u.nome AS organizador,
            cp.organizador_id,
            c.nome AS cliente,
            cp.cliente_id,
            cp.processo_ref,
            cp.visibilidade
        FROM compromissos cp
        LEFT JOIN usuarios u ON cp.organizador_id = u.id
        LEFT JOIN contatos c ON cp.cliente_id = c.id
        LEFT JOIN compromissos_participantes cpp ON cp.id = cpp.compromisso_id
    """
    params = ()
    if usuario_logado_id:
        query += """
            WHERE (
                cp.visibilidade = 'Compartilhada' 
                OR cp.organizador_id = ? 
                OR cpp.usuario_id = ?
            )
        """
        params = (usuario_logado_id, usuario_logado_id)
        
    query += " ORDER BY cp.data_inicio ASC, cp.hora_inicio ASC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def get_participantes_compromisso(compromisso_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT usuario_id FROM compromissos_participantes WHERE compromisso_id = ?", (compromisso_id,))
    ids = [row[0] for row in c.fetchall()]
    conn.close()
    return ids

def set_participantes_compromisso(compromisso_id, usuario_ids):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM compromissos_participantes WHERE compromisso_id = ?", (compromisso_id,))
    for u_id in usuario_ids:
        c.execute("INSERT OR IGNORE INTO compromissos_participantes (compromisso_id, usuario_id) VALUES (?, ?)", (compromisso_id, u_id))
    conn.commit()
    conn.close()

def add_compromisso(titulo, descricao, data_inicio, hora_inicio, data_fim, hora_fim, dia_inteiro, local_link, cliente_id, processo_ref, organizador_id, visibilidade, participantes_ids=None):
    conn = get_connection()
    c = conn.cursor()
    criado_em = date.today().strftime("%Y-%m-%d")
    c.execute("""
        INSERT INTO compromissos (titulo, descricao, data_inicio, hora_inicio, data_fim, hora_fim, dia_inteiro, local_link, cliente_id, processo_ref, organizador_id, visibilidade, criado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (titulo, descricao, str(data_inicio), str(hora_inicio) if not dia_inteiro else None, str(data_fim), str(hora_fim) if not dia_inteiro else None, 1 if dia_inteiro else 0, local_link, cliente_id, processo_ref, organizador_id, visibilidade, criado_em))
    comp_id = c.lastrowid
    conn.commit()
    conn.close()
    
    if participantes_ids:
        set_participantes_compromisso(comp_id, participantes_ids)
    return comp_id

def update_compromisso(comp_id, titulo, descricao, data_inicio, hora_inicio, data_fim, hora_fim, dia_inteiro, local_link, cliente_id, processo_ref, visibilidade, participantes_ids=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE compromissos
        SET titulo = ?, descricao = ?, data_inicio = ?, hora_inicio = ?, data_fim = ?, hora_fim = ?, dia_inteiro = ?, local_link = ?, cliente_id = ?, processo_ref = ?, visibilidade = ?
        WHERE id = ?
    """, (titulo, descricao, str(data_inicio), str(hora_inicio) if not dia_inteiro else None, str(data_fim), str(hora_fim) if not dia_inteiro else None, 1 if dia_inteiro else 0, local_link, cliente_id, processo_ref, visibilidade, comp_id))
    conn.commit()
    conn.close()
    
    if participantes_ids is not None:
        set_participantes_compromisso(comp_id, participantes_ids)

def delete_compromisso(comp_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM compromissos_participantes WHERE compromisso_id = ?", (comp_id,))
    c.execute("DELETE FROM compromissos WHERE id = ?", (comp_id,))
    conn.commit()
    conn.close()

# --- Funções: Plano de Contas Financeiro ---
def get_contas_sinteticas(tipo=None):
    conn = get_connection()
    query = "SELECT id, tipo, nome FROM contas_sinteticas"
    params = ()
    if tipo:
        query += " WHERE tipo = ?"
        params = (tipo,)
    query += " ORDER BY tipo, nome ASC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def add_conta_sintetica(tipo, nome):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO contas_sinteticas (tipo, nome) VALUES (?, ?)", (tipo, nome.strip()))
        conn.commit()
        sucesso = True
    except sqlite3.IntegrityError:
        sucesso = False
    finally:
        conn.close()
    return sucesso

def update_conta_sintetica(sintetica_id, tipo, nome):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("UPDATE contas_sinteticas SET tipo = ?, nome = ? WHERE id = ?", (tipo, nome.strip(), sintetica_id))
        conn.commit()
        sucesso = True
    except sqlite3.IntegrityError:
        sucesso = False
    finally:
        conn.close()
    return sucesso

def delete_conta_sintetica(sintetica_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE lancamentos SET conta_analitica_id = NULL WHERE conta_analitica_id IN (SELECT id FROM contas_analiticas WHERE sintetica_id = ?)", (sintetica_id,))
    c.execute("DELETE FROM regras_classificacao WHERE sintetica_id = ?", (sintetica_id,))
    c.execute("DELETE FROM contas_analiticas WHERE sintetica_id = ?", (sintetica_id,))
    c.execute("DELETE FROM contas_sinteticas WHERE id = ?", (sintetica_id,))
    conn.commit()
    conn.close()

def get_contas_analiticas(tipo=None):
    conn = get_connection()
    query = """
        SELECT 
            a.id,
            s.tipo,
            s.id AS sintetica_id,
            s.nome AS conta_sintetica,
            a.nome AS conta_analitica,
            a.historico_padrao_id,
            h.codigo || ' - ' || h.descricao AS historico_padrao_nome,
            s.tipo || ' ➔ ' || s.nome || ' ➔ ' || a.nome AS caminho_completo
        FROM contas_analiticas a
        JOIN contas_sinteticas s ON a.sintetica_id = s.id
        LEFT JOIN historicos_padrao h ON a.historico_padrao_id = h.id
    """
    params = ()
    if tipo:
        query += " WHERE s.tipo = ?"
        params = (tipo,)
    query += " ORDER BY s.tipo, s.nome, a.nome ASC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def add_conta_analitica(sintetica_id, nome, historico_padrao_id=None):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO contas_analiticas (sintetica_id, nome, historico_padrao_id) VALUES (?, ?, ?)", 
                  (sintetica_id, nome.strip(), historico_padrao_id))
        conn.commit()
        sucesso = True
    except sqlite3.IntegrityError:
        sucesso = False
    finally:
        conn.close()
    return sucesso

def update_conta_analitica(analitica_id, sintetica_id, nome, historico_padrao_id=None):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            UPDATE contas_analiticas 
            SET sintetica_id = ?, nome = ?, historico_padrao_id = ? 
            WHERE id = ?
        """, (sintetica_id, nome.strip(), historico_padrao_id, analitica_id))
        conn.commit()
        sucesso = True
    except sqlite3.IntegrityError:
        sucesso = False
    finally:
        conn.close()
    return sucesso

def delete_conta_analitica(analitica_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE lancamentos SET conta_analitica_id = NULL WHERE conta_analitica_id = ?", (analitica_id,))
    c.execute("DELETE FROM contas_recorrentes WHERE conta_analitica_id = ?", (analitica_id,))
    c.execute("DELETE FROM regras_classificacao WHERE analitica_id = ?", (analitica_id,))
    c.execute("DELETE FROM contas_analiticas WHERE id = ?", (analitica_id,))
    conn.commit()
    conn.close()

# --- Funções: Contatos ---
def get_contatos(tipo=None):
    conn = get_connection()
    query = "SELECT id, nome, tipo FROM contatos"
    params = ()
    if tipo:
        query += " WHERE tipo = ?"
        params = (tipo,)
    query += " ORDER BY nome ASC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def add_contato(nome, tipo):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO contatos (nome, tipo) VALUES (?, ?)", (nome.strip(), tipo))
    conn.commit()
    conn.close()

def update_contato(contato_id, nome):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE contatos SET nome = ? WHERE id = ?", (nome.strip(), contato_id))
    conn.commit()
    conn.close()

def delete_contato(contato_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM lancamentos WHERE contato_id = ?", (contato_id,))
    c.execute("UPDATE contas_recorrentes SET contato_id = NULL WHERE contato_id = ?", (contato_id,))
    c.execute("UPDATE tarefas SET cliente_id = NULL WHERE cliente_id = ?", (contato_id,))
    c.execute("UPDATE tarefas_recorrentes SET cliente_id = NULL WHERE cliente_id = ?", (contato_id,))
    c.execute("UPDATE compromissos SET cliente_id = NULL WHERE cliente_id = ?", (contato_id,))
    c.execute("DELETE FROM contatos WHERE id = ?", (contato_id,))
    conn.commit()
    conn.close()

# --- Funções: Histórico Padrão ---
def get_historicos(tipo=None):
    conn = get_connection()
    query = "SELECT id, codigo, descricao, tipo_aplicavel FROM historicos_padrao"
    params = ()
    if tipo:
        query += " WHERE tipo_aplicavel = ? OR tipo_aplicavel = 'Ambos'"
        params = (tipo,)
    query += " ORDER BY codigo ASC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def add_historico(codigo, descricao, tipo_aplicavel):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO historicos_padrao (codigo, descricao, tipo_aplicavel) VALUES (?, ?, ?)", 
                  (codigo.strip().upper(), descricao.strip(), tipo_aplicavel))
        conn.commit()
        sucesso = True
    except sqlite3.IntegrityError:
        sucesso = False
    finally:
        conn.close()
    return sucesso

def update_historico(hist_id, codigo, descricao, tipo_aplicavel):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            UPDATE historicos_padrao 
            SET codigo = ?, descricao = ?, tipo_aplicavel = ? 
            WHERE id = ?
        """, (codigo.strip().upper(), descricao.strip(), tipo_aplicavel, hist_id))
        conn.commit()
        sucesso = True
    except sqlite3.IntegrityError:
        sucesso = False
    finally:
        conn.close()
    return sucesso

def delete_historico(hist_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE lancamentos SET historico_id = NULL WHERE historico_id = ?", (hist_id,))
    c.execute("UPDATE contas_recorrentes SET historico_id = NULL WHERE historico_id = ?", (hist_id,))
    c.execute("UPDATE contas_analiticas SET historico_padrao_id = NULL WHERE historico_padrao_id = ?", (hist_id,))
    c.execute("UPDATE regras_classificacao SET historico_id = NULL WHERE historico_id = ?", (hist_id,))
    c.execute("DELETE FROM historicos_padrao WHERE id = ?", (hist_id,))
    conn.commit()
    conn.close()

# --- Funções: Contas Recorrentes Financeiras ---
def get_contas_recorrentes():
    conn = get_connection()
    query = """
        SELECT 
            r.id,
            r.titulo,
            c.nome AS fornecedor,
            r.contato_id,
            s.nome AS conta_sintetica,
            a.nome AS conta_analitica,
            r.conta_analitica_id,
            h.codigo || ' - ' || h.descricao AS historico_padrao,
            r.historico_id,
            r.valor,
            r.dia_vencimento,
            r.complemento_padrao,
            r.pago_por_padrao
        FROM contas_recorrentes r
        LEFT JOIN contatos c ON r.contato_id = c.id
        LEFT JOIN contas_analiticas a ON r.conta_analitica_id = a.id
        LEFT JOIN contas_sinteticas s ON a.sintetica_id = s.id
        LEFT JOIN historicos_padrao h ON r.historico_id = h.id
        ORDER BY r.dia_vencimento ASC, r.titulo ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def add_conta_recorrente(titulo, contato_id, conta_analitica_id, historico_id, valor, dia_vencimento, complemento_padrao, pago_por_padrao):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO contas_recorrentes (titulo, contato_id, conta_analitica_id, historico_id, valor, dia_vencimento, complemento_padrao, pago_por_padrao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (titulo.strip(), contato_id, conta_analitica_id, historico_id, valor, dia_vencimento, complemento_padrao, pago_por_padrao))
    conn.commit()
    conn.close()

def update_conta_recorrente(rec_id, titulo, contato_id, conta_analitica_id, historico_id, valor, dia_vencimento, complemento_padrao, pago_por_padrao):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE contas_recorrentes 
        SET titulo = ?, contato_id = ?, conta_analitica_id = ?, historico_id = ?, valor = ?, dia_vencimento = ?, complemento_padrao = ?, pago_por_padrao = ?
        WHERE id = ?
    """, (titulo.strip(), contato_id, conta_analitica_id, historico_id, valor, dia_vencimento, complemento_padrao, pago_por_padrao, rec_id))
    conn.commit()
    conn.close()

def delete_conta_recorrente(rec_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE lancamentos SET recorrente_id = NULL WHERE recorrente_id = ?", (rec_id,))
    c.execute("DELETE FROM contas_recorrentes WHERE id = ?", (rec_id,))
    conn.commit()
    conn.close()

# --- Funções: Regras de Classificação ---
def get_regras_classificacao():
    conn = get_connection()
    query = """
        SELECT 
            r.id,
            r.padrao_texto,
            r.tipo,
            r.sintetica_id,
            s.nome AS categoria,
            r.analitica_id,
            a.nome AS subcategoria,
            r.historico_id,
            h.codigo || ' - ' || h.descricao AS historico_padrao
        FROM regras_classificacao r
        JOIN contas_sinteticas s ON r.sintetica_id = s.id
        JOIN contas_analiticas a ON r.analitica_id = a.id
        LEFT JOIN historicos_padrao h ON r.historico_id = h.id
        ORDER BY r.tipo, s.nome, a.nome ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def add_regra_classificacao(padrao_texto, tipo, sintetica_id, analitica_id, historico_id=None):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO regras_classificacao (padrao_texto, tipo, sintetica_id, analitica_id, historico_id)
            VALUES (?, ?, ?, ?, ?)
        """, (padrao_texto.strip().lower(), tipo, sintetica_id, analitica_id, historico_id))
        conn.commit()
        sucesso = True
    except sqlite3.IntegrityError:
        sucesso = False
    finally:
        conn.close()
    return sucesso

def update_regra_classificacao(regra_id, padrao_texto, tipo, sintetica_id, analitica_id, historico_id=None):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            UPDATE regras_classificacao 
            SET padrao_texto = ?, tipo = ?, sintetica_id = ?, analitica_id = ?, historico_id = ?
            WHERE id = ?
        """, (padrao_texto.strip().lower(), tipo, sintetica_id, analitica_id, historico_id, regra_id))
        conn.commit()
        sucesso = True
    except sqlite3.IntegrityError:
        sucesso = False
    finally:
        conn.close()
    return sucesso

def delete_regra_classificacao(regra_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM regras_classificacao WHERE id = ?", (regra_id,))
    conn.commit()
    conn.close()

# --- Funções: Lançamentos & Baixas Financeiras ---
def add_lancamento(tipo, data_vencimento, valor, contato_id, historico_id, conta_analitica_id, complemento, status, data_pagamento=None, pago_por=None, recorrente_id=None, mes_referencia=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO lancamentos (tipo, data_vencimento, data_pagamento, valor, contato_id, historico_id, conta_analitica_id, complemento, status, pago_por, recorrente_id, mes_referencia)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (tipo, str(data_vencimento), str(data_pagamento) if data_pagamento else None, valor, contato_id, historico_id, conta_analitica_id, complemento, status, pago_por, recorrente_id, mes_referencia))
    conn.commit()
    conn.close()

def update_lancamento(lanc_id, tipo, data_vencimento, data_pagamento, valor, contato_id, historico_id, conta_analitica_id, complemento, status, pago_por=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE lancamentos 
        SET tipo = ?, data_vencimento = ?, data_pagamento = ?, valor = ?, contato_id = ?, historico_id = ?, conta_analitica_id = ?, complemento = ?, status = ?, pago_por = ?
        WHERE id = ?
    """, (tipo, str(data_vencimento), str(data_pagamento) if data_pagamento else None, valor, contato_id, historico_id, conta_analitica_id, complemento, status, pago_por, lanc_id))
    conn.commit()
    conn.close()

def delete_lancamento(lanc_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM lancamentos WHERE id = ?", (lanc_id,))
    conn.commit()
    conn.close()

def baixar_lancamentos_em_lote(lancamentos_ids, data_baixa, pago_por=None):
    conn = get_connection()
    c = conn.cursor()
    for l_id in lancamentos_ids:
        if pago_por:
            c.execute("""
                UPDATE lancamentos 
                SET status = 'Concluído', data_pagamento = ?, pago_por = ? 
                WHERE id = ?
            """, (str(data_baixa), pago_por, l_id))
        else:
            c.execute("""
                UPDATE lancamentos 
                SET status = 'Concluído', data_pagamento = ? 
                WHERE id = ?
            """, (str(data_baixa), l_id))
    conn.commit()
    conn.close()

def get_lancamentos_df(tipo_filtro=None):
    conn = get_connection()
    query = """
        SELECT 
            l.id,
            l.data_vencimento,
            l.data_pagamento,
            l.tipo,
            c.nome AS contato,
            c.id AS contato_id,
            s.nome AS conta_sintetica,
            a.nome AS conta_analitica,
            a.id AS conta_analitica_id,
            h.codigo || ' - ' || h.descricao AS historico_padrao,
            h.id AS historico_id,
            l.complemento,
            l.valor,
            l.status,
            l.pago_por,
            l.mes_referencia,
            l.recorrente_id
        FROM lancamentos l
        LEFT JOIN contatos c ON l.contato_id = c.id
        LEFT JOIN historicos_padrao h ON l.historico_id = h.id
        LEFT JOIN contas_analiticas a ON l.conta_analitica_id = a.id
        LEFT JOIN contas_sinteticas s ON a.sintetica_id = s.id
    """
    params = ()
    if tipo_filtro:
        query += " WHERE l.tipo = ?"
        params = (tipo_filtro,)
    query += " ORDER BY l.data_vencimento DESC, l.id DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def gerar_contas_do_mes(ano, mes):
    conn = get_connection()
    mes_ref = f"{ano:04d}-{mes:02d}"
    df_rec = pd.read_sql_query("SELECT * FROM contas_recorrentes", conn)
    if df_rec.empty:
        conn.close()
        return 0, 0, "Nenhuma conta recorrente pré-cadastrada no sistema."
    
    df_existentes = pd.read_sql_query("SELECT recorrente_id FROM lancamentos WHERE mes_referencia = ?", conn, params=(mes_ref,))
    existentes_ids = set(df_existentes["recorrente_id"].dropna().astype(int).tolist())
    
    gerados_count = 0
    ignorados_count = 0
    c = conn.cursor()
    ultimo_dia_mes = calendar.monthrange(ano, mes)[1]
    
    for _, item in df_rec.iterrows():
        rec_id = int(item["id"])
        if rec_id in existentes_ids:
            ignorados_count += 1
            continue
        dia = min(int(item["dia_vencimento"]), ultimo_dia_mes)
        data_venc = f"{ano:04d}-{mes:02d}-{dia:02d}"
        c.execute("""
            INSERT INTO lancamentos (
                tipo, data_vencimento, data_pagamento, valor, contato_id, historico_id, conta_analitica_id, 
                complemento, status, pago_por, recorrente_id, mes_referencia
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, 'Pendente', ?, ?, ?)
        """, (
            "Despesa", data_venc, float(item["valor"] or 0.0),
            item["contato_id"] if pd.notna(item["contato_id"]) else None,
            item["historico_id"] if pd.notna(item["historico_id"]) else None,
            int(item["conta_analitica_id"]), item["complemento_padrao"],
            item["pago_por_padrao"] if pd.notna(item["pago_por_padrao"]) else None,
            rec_id, mes_ref
        ))
        gerados_count += 1
        
    conn.commit()
    conn.close()
    return gerados_count, ignorados_count, "Processamento concluído com sucesso."

def to_excel_bytes(df, sheet_name="Relatorio"):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()

# Inicializa banco
init_db()

# ----------------------------------------------------
# GERENCIAMENTO DE SESSÃO & TELA DE LOGIN
# ----------------------------------------------------
if "usuario_autenticado" not in st.session_state:
    st.session_state["usuario_autenticado"] = None

if not st.session_state["usuario_autenticado"]:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col_l1, col_l2, col_l3 = st.columns([1, 1.2, 1])
    with col_l2:
        st.markdown("## ⚖️ Fabíola Guimarães Advocacia")
        st.markdown("#### Acesso Restrito ao Sistema")
        
        with st.form("form_login"):
            login_email = st.text_input("E-mail Profissional", placeholder="fabiola@advocacia.com.br")
            login_senha = st.text_input("Senha", type="password")
            btn_login = st.form_submit_button("Entrar no Sistema", type="primary", use_container_width=True)
            
            if btn_login:
                user_logado = autenticar_usuario(login_email, login_senha)
                if user_logado:
                    st.session_state["usuario_autenticado"] = user_logado
                    st.success(f"Bem-vindo(a), {user_logado['nome']}!")
                    st.rerun()
                else:
                    st.error("E-mail ou senha inválidos, ou usuário inativo.")
        
        st.info("💡 Primeiro acesso? As credenciais padrão são o e-mail cadastrado e senha **123456**.")
        
        with st.expander("🔑 Redefinir senha padrão inicial (Contingência)"):
            st.caption("Caso esteja acessando de uma nova instalação na nuvem e precise restaurar a senha inicial para '123456'.")
            reset_email = st.text_input("Confirmar e-mail para reset", value="fabiola@advocacia.com.br", key="reset_email_box")
            if st.button("Restaurar senha deste e-mail para 123456"):
                if resetar_senha_padrao_admin(reset_email):
                    st.success("Senha restaurada para 123456 com sucesso! Faça login acima.")
                else:
                    st.error("E-mail não encontrado no banco de dados.")
    st.stop()

# ----------------------------------------------------
# USUÁRIO LOGADO / SESSÃO ATIVA
# ----------------------------------------------------
usuario_logado = st.session_state["usuario_autenticado"]
operador_atual_id = usuario_logado["id"]
operador_atual_nome = usuario_logado["nome"]

# ----------------------------------------------------
# BARRA LATERAL (SESSÃO E ROTEAMENTO)
# ----------------------------------------------------
st.sidebar.markdown("## ⚖️ Fabíola Guimarães")
st.sidebar.caption("ADVOCACIA & CONSULTORIA")

st.sidebar.markdown(f"👤 **{operador_atual_nome}**")
st.sidebar.caption(f"Perfil: {usuario_logado['perfil']}")

if st.sidebar.button("🚪 Sair / Logout", use_container_width=True):
    st.session_state["usuario_autenticado"] = None
    st.rerun()

st.sidebar.divider()

sistema_ativo = st.sidebar.selectbox(
    "Selecione o Módulo:",
    [
        "💼 Gestão Financeira", 
        "✅ Gestão de Tarefas", 
        "📅 Agenda de Compromissos", 
        "🛠️ Manutenção de Tabelas (CRUDs)", 
        "👥 Usuários"
    ],
    key="sistema_principal"
)

st.sidebar.divider()

# ====================================================
# SISTEMA 1: GESTÃO FINANCEIRA
# ====================================================
if sistema_ativo == "💼 Gestão Financeira":
    st.title("💼 Gestão Financeira - Dra. Fabíola & Fabrício")
    
    menu = st.sidebar.radio(
        "Menu Financeiro",
        ["Painel Geral", "🔴 Contas a Pagar", "🟢 Contas a Receber", "⚡ Gerar Contas a Pagar", "📊 Relatórios", "Cadastros"],
        key="nav_financeiro"
    )

    # 1. PAINEL GERAL
    if menu == "Painel Geral":
        st.subheader("Resumo Financeiro & Balanço")
        df = get_lancamentos_df()

        if df.empty:
            st.info("Nenhum lançamento registrado até o momento.")
        else:
            df["valor"] = pd.to_numeric(df["valor"])
            col_f1, col_f2 = st.columns(2)
            tipo_filtro = col_f1.multiselect("Filtrar por Tipo", ["Receita", "Despesa"], default=["Receita", "Despesa"])
            status_filtro = col_f2.multiselect("Filtrar por Status", ["Concluído", "Pendente"], default=["Concluído", "Pendente"])

            df_filtrado = df[(df["tipo"].isin(tipo_filtro)) & (df["status"].isin(status_filtro))].copy()

            receitas = df_filtrado[df_filtrado["tipo"] == "Receita"]["valor"].sum()
            despesas = df_filtrado[df_filtrado["tipo"] == "Despesa"]["valor"].sum()
            saldo = receitas - despesas

            m1, m2, m3 = st.columns(3)
            m1.metric("Total Receitas", f"R$ {receitas:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            m2.metric("Total Despesas", f"R$ {despesas:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            m3.metric("Resultado do Escritório", f"R$ {saldo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

            st.divider()

            st.subheader("⚖️ Acerto de Contas entre Sócios (50/50)")
            despesas_pagas = df[(df["tipo"] == "Despesa") & (df["status"] == "Concluído")]
            total_fabricio = despesas_pagas[despesas_pagas["pago_por"] == "Fabrício"]["valor"].sum()
            total_fabiola = despesas_pagas[despesas_pagas["pago_por"] == "Fabíola"]["valor"].sum()
            
            col_s1, col_s2, col_s3 = st.columns(3)
            col_s1.metric("Pago por Fabrício", f"R$ {total_fabricio:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            col_s2.metric("Pago por Fabíola", f"R$ {total_fabiola:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            
            diferenca = (total_fabricio - total_fabiola) / 2
            with col_s3:
                if diferenca > 0:
                    st.success(f"**Fabíola deve a Fabrício:**  \n### R$ {diferenca:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                elif diferenca < 0:
                    st.info(f"**Fabrício deve a Fabíola:**  \n### R$ {abs(diferenca):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                else:
                    st.success("**Contas equilibradas!**")

            st.divider()
            st.subheader("📋 Lançamentos do Período")
            colunas_exibir = ["id", "data_vencimento", "data_pagamento", "tipo", "contato", "conta_sintetica", "conta_analitica", "historico_padrao", "complemento", "valor", "status", "pago_por"]
            df_view = df_filtrado[colunas_exibir].copy()
            df_view["data_vencimento"] = df_view["data_vencimento"].apply(formatar_data_br)
            df_view["data_pagamento"] = df_view["data_pagamento"].apply(formatar_data_br)
            st.dataframe(df_view, use_container_width=True)

    # 2. CONTAS A PAGAR
    elif menu == "🔴 Contas a Pagar":
        st.subheader("🔴 Gestão de Contas a Pagar (Despesas)")
        cp_tab_inc, cp_tab_baixa, cp_tab_alt, cp_tab_exc = st.tabs(["➕ Incluir Despesa", "✅ Baixa / Pagamentos", "✏️ Alterar", "🗑️ Excluir"])
        
        fornecedores_df = get_contatos(tipo="Fornecedor")
        analiticas_desp_df = get_contas_analiticas(tipo="Despesa")
        historicos_desp_df = get_historicos(tipo="Despesa")
        
        with cp_tab_inc:
            if analiticas_desp_df.empty:
                st.warning("Nenhuma Conta Analítica de Despesa cadastrada. Acesse 'Plano de Contas'.")
            else:
                forn_opcoes = {"(Opcional / Não informado)": None}
                if not fornecedores_df.empty:
                    for _, row in fornecedores_df.iterrows():
                        forn_opcoes[row["nome"]] = row["id"]
                        
                analitica_desp_opcoes = {f"{row['conta_sintetica']} ➔ {row['conta_analitica']}": row["id"] for _, row in analiticas_desp_df.iterrows()}
                analitica_desp_map_hist = dict(zip(analiticas_desp_df["id"], analiticas_desp_df["historico_padrao_id"]))
                
                hist_desp_opcoes = {"(Sem histórico padrão)": None}
                if not historicos_desp_df.empty:
                    for _, row in historicos_desp_df.iterrows():
                        hist_desp_opcoes[f"{row['codigo']} - {row['descricao']}"] = row["id"]

                anal_sel_desp = st.selectbox("Conta de Despesa (Classificação)", list(analitica_desp_opcoes.keys()), key="inc_cp_anal")
                anal_id_sel_desp = analitica_desp_opcoes[anal_sel_desp]
                hist_padrao_vinc = analitica_desp_map_hist.get(anal_id_sel_desp)
                
                hist_keys_desp = list(hist_desp_opcoes.keys())
                hist_def_idx = 0
                if pd.notna(hist_padrao_vinc) and hist_padrao_vinc in list(hist_desp_opcoes.values()):
                    hist_def_idx = list(hist_desp_opcoes.values()).index(hist_padrao_vinc)

                with st.form("form_inc_conta_pagar", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    data_venc = col1.date_input("Data de Vencimento", value=date.today(), format="DD/MM/YYYY")
                    valor = col2.number_input("Valor da Despesa (R$)", min_value=0.01, step=50.0, format="%.2f")
                    
                    forn_sel = col1.selectbox("Fornecedor", list(forn_opcoes.keys()))
                    hist_sel = col2.selectbox("Histórico Padrão", hist_keys_desp, index=hist_def_idx)
                    
                    complemento = st.text_input("Complemento do Histórico (Ex: Fatura Internet Março/2026)")
                    
                    col_s1, col_s2, col_s3 = st.columns(3)
                    status = col_s1.selectbox("Status", ["Pendente", "Concluído (Já Efetivado)"], key="status_cp_inc")
                    
                    data_pgto = None
                    pago_por = None
                    if status == "Concluído (Já Efetivado)":
                        data_pgto = col_s2.date_input("Data de Pagamento", value=date.today(), format="DD/MM/YYYY", key="data_pgto_cp_inc")
                        pago_por = col_s3.selectbox("Pago por (Sócio)", SOCIOS, key="pago_por_cp_inc")
                    
                    if st.form_submit_button("Salvar Conta a Pagar", type="primary"):
                        db_status = "Concluído" if "Concluído" in status else "Pendente"
                        add_lancamento(
                            tipo="Despesa",
                            data_vencimento=data_venc,
                            valor=valor,
                            contato_id=forn_opcoes[forn_sel],
                            historico_id=hist_desp_opcoes[hist_sel],
                            conta_analitica_id=anal_id_sel_desp,
                            complemento=complemento.strip(),
                            status=db_status,
                            data_pagamento=data_pgto,
                            pago_por=pago_por
                        )
                        st.success("Conta a pagar registrada com sucesso!")
                        st.rerun()

        with cp_tab_baixa:
            st.markdown("#### ⚡ Baixa e Confirmação de Pagamentos")
            b_col1, b_col2 = st.columns(2)
            data_ini_venc = b_col1.date_input("Vencimento Inicial", value=date.today().replace(day=1), format="DD/MM/YYYY", key="cp_baixa_ini")
            data_fim_venc = b_col2.date_input("Vencimento Final", value=date.today(), format="DD/MM/YYYY", key="cp_baixa_fim")
            
            df_desp = get_lancamentos_df(tipo_filtro="Despesa")
            if not df_desp.empty:
                df_desp_pend = df_desp[
                    (df_desp["status"] == "Pendente") &
                    (df_desp["data_vencimento"] >= str(data_ini_venc)) &
                    (df_desp["data_vencimento"] <= str(data_fim_venc))
                ].copy()
            else:
                df_desp_pend = pd.DataFrame()
                
            if df_desp_pend.empty:
                st.info("Nenhuma conta a pagar pendente encontrada no período.")
            else:
                df_desp_pend["Baixar?"] = False
                df_desp_pend["data_vencimento"] = df_desp_pend["data_vencimento"].apply(formatar_data_br)
                col_ordem = ["Baixar?", "id", "data_vencimento", "contato", "conta_analitica", "historico_padrao", "complemento", "valor", "pago_por"]
                
                tabela_edit = st.data_editor(
                    df_desp_pend[col_ordem],
                    disabled=["id", "data_vencimento", "contato", "conta_analitica", "historico_padrao", "complemento", "valor", "pago_por"],
                    hide_index=True,
                    use_container_width=True,
                    key="editor_cp_baixas"
                )
                
                ids_sel = tabela_edit[tabela_edit["Baixar?"] == True]["id"].tolist()
                valor_tot = tabela_edit[tabela_edit["Baixar?"] == True]["valor"].sum()
                
                st.divider()
                st.markdown(f"**Títulos selecionados:** {len(ids_sel)} | **Valor Total:** R$ {valor_tot:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                if len(ids_sel) > 0:
                    with st.form("form_confirmar_cp_baixa"):
                        f_col1, f_col2 = st.columns(2)
                        data_efetiva = f_col1.date_input("Data Efetiva do Pagamento", value=date.today(), format="DD/MM/YYYY")
                        socio_baixa = f_col2.selectbox("Pago por (Sócio)", SOCIOS, key="socio_cp_baixa")
                        
                        if st.form_submit_button(f"✅ Confirmar Pagamento de {len(ids_sel)} Título(s)", type="primary"):
                            baixar_lancamentos_em_lote(ids_sel, data_efetiva, socio_baixa)
                            st.success("Pagamento baixado com sucesso!")
                            st.rerun()

        with cp_tab_alt:
            df_desp_all = get_lancamentos_df(tipo_filtro="Despesa")
            if df_desp_all.empty:
                st.info("Nenhuma conta a pagar registrada para alteração.")
            else:
                opcoes_cp = {
                    f"ID {row['id']} | Venc: {formatar_data_br(row['data_vencimento'])} | {row['contato'] or 'S/ Fornecedor'} | R$ {row['valor']:.2f} ({row['status']})": row['id'] 
                    for _, row in df_desp_all.iterrows()
                }
                cp_sel = st.selectbox("Selecione a Conta a Pagar para Alterar", list(opcoes_cp.keys()), key="sel_cp_alt")
                cp_id = opcoes_cp[cp_sel]
                item_cp = df_desp_all[df_desp_all["id"] == cp_id].iloc[0]
                
                forn_edit_map = {"(Opcional / Não informado)": None}
                if not fornecedores_df.empty:
                    for _, row in fornecedores_df.iterrows():
                        forn_edit_map[row["nome"]] = row["id"]
                        
                anal_edit_map = {f"{row['conta_sintetica']} ➔ {row['conta_analitica']}": row["id"] for _, row in analiticas_desp_df.iterrows()}
                hist_edit_map = {"(Sem histórico padrão)": None}
                if not historicos_desp_df.empty:
                    for _, row in historicos_desp_df.iterrows():
                        hist_edit_map[f"{row['codigo']} - {row['descricao']}"] = row["id"]

                anal_keys = list(anal_edit_map.keys())
                anal_idx = list(anal_edit_map.values()).index(item_cp["conta_analitica_id"]) if item_cp["conta_analitica_id"] in list(anal_edit_map.values()) else 0
                anal_sel = st.selectbox("Conta de Despesa", anal_keys, index=anal_idx, key="edit_cp_anal_sel")
                anal_id = anal_edit_map[anal_sel]
                
                hist_keys = list(hist_edit_map.keys())
                hist_idx = list(hist_edit_map.values()).index(item_cp["historico_id"]) if item_cp["historico_id"] in list(hist_edit_map.values()) else 0
                hist_sel = st.selectbox("Histórico Padrão", hist_keys, index=hist_idx, key="edit_cp_hist_sel")

                with st.form("form_edit_conta_pagar"):
                    col1, col2 = st.columns(2)
                    data_venc = col1.date_input("Data de Vencimento", value=parse_data_iso(item_cp["data_vencimento"]), format="DD/MM/YYYY")
                    valor = col2.number_input("Valor (R$)", min_value=0.01, step=50.0, value=float(item_cp["valor"]), format="%.2f")
                    
                    forn_keys = list(forn_edit_map.keys())
                    forn_idx = list(forn_edit_map.values()).index(item_cp["contato_id"]) if item_cp["contato_id"] in list(forn_edit_map.values()) else 0
                    forn_sel = col1.selectbox("Fornecedor", forn_keys, index=forn_idx)
                    
                    complemento = st.text_input("Complemento do Histórico", value=item_cp["complemento"] if pd.notna(item_cp["complemento"]) else "")
                    
                    col_e1, col_e2, col_e3 = st.columns(3)
                    status_idx = 0 if item_cp["status"] == "Concluído" else 1
                    status_edit = col_e1.selectbox("Status", ["Concluído", "Pendente"], index=status_idx, key="cp_edit_status")
                    
                    data_pgto_val = parse_data_iso(item_cp["data_pagamento"]) if pd.notna(item_cp["data_pagamento"]) and item_cp["data_pagamento"] else date.today()
                    data_pgto_edit = None
                    if status_edit == "Concluído":
                        data_pgto_edit = col_e2.date_input("Data de Pagamento", value=data_pgto_val, format="DD/MM/YYYY", key="cp_edit_dtpg")
                    
                    pago_idx = SOCIOS.index(item_cp["pago_por"]) if item_cp["pago_por"] in SOCIOS else 0
                    pago_por_edit = col_e3.selectbox("Pago por (Sócio)", SOCIOS, index=pago_idx, key="cp_edit_pago_por")
                    
                    if st.form_submit_button("Atualizar Conta a Pagar", type="primary"):
                        update_lancamento(
                            lanc_id=cp_id,
                            tipo="Despesa",
                            data_vencimento=data_venc,
                            data_pagamento=data_pgto_edit,
                            valor=valor,
                            contato_id=forn_edit_map[forn_sel],
                            historico_id=hist_edit_map[hist_sel],
                            conta_analitica_id=anal_id,
                            complemento=complemento.strip(),
                            status=status_edit,
                            pago_por=pago_por_edit
                        )
                        st.success("Conta a pagar atualizada com sucesso!")
                        st.rerun()

        with cp_tab_exc:
            df_desp_del = get_lancamentos_df(tipo_filtro="Despesa")
            if df_desp_del.empty:
                st.info("Nenhuma conta a pagar para exclusão.")
            else:
                opcoes_del_cp = {
                    f"ID {row['id']} | Venc: {formatar_data_br(row['data_vencimento'])} | {row['contato'] or 'S/ Fornecedor'} | R$ {row['valor']:.2f} ({row['status']})": row['id'] 
                    for _, row in df_desp_del.iterrows()
                }
                cp_del_sel = st.selectbox("Selecione a Conta a Pagar para Excluir", list(opcoes_del_cp.keys()), key="del_cp_box")
                if st.button("🗑️ Confirmar Exclusão da Conta a Pagar", type="primary"):
                    delete_lancamento(opcoes_del_cp[cp_del_sel])
                    st.success("Conta a pagar excluída com sucesso!")
                    st.rerun()

    # 3. CONTAS A RECEBER
    elif menu == "🟢 Contas a Receber":
        st.subheader("🟢 Gestão de Contas a Receber (Receitas / Honorários)")
        cr_tab_inc, cr_tab_baixa, cr_tab_alt, cr_tab_exc = st.tabs(["➕ Incluir Receita", "✅ Baixa / Recebimentos", "✏️ Alterar", "🗑️️ Excluir"])
        
        clientes_df = get_contatos(tipo="Cliente")
        analiticas_rec_df = get_contas_analiticas(tipo="Receita")
        historicos_rec_df = get_historicos(tipo="Receita")
        
        with cr_tab_inc:
            if analiticas_rec_df.empty:
                st.warning("Nenhuma Conta Analítica de Receita cadastrada. Acesse 'Plano de Contas'.")
            else:
                cli_opcoes = {"(Opcional / Não informado)": None}
                if not clientes_df.empty:
                    for _, row in clientes_df.iterrows():
                        cli_opcoes[row["nome"]] = row["id"]
                        
                analitica_rec_opcoes = {f"{row['conta_sintetica']} ➔ {row['conta_analitica']}": row["id"] for _, row in analiticas_rec_df.iterrows()}
                analitica_rec_map_hist = dict(zip(analiticas_rec_df["id"], analiticas_rec_df["historico_padrao_id"]))
                
                hist_rec_opcoes = {"(Sem histórico padrão)": None}
                if not historicos_rec_df.empty:
                    for _, row in historicos_rec_df.iterrows():
                        hist_rec_opcoes[f"{row['codigo']} - {row['descricao']}"] = row["id"]

                anal_sel_rec = st.selectbox("Conta de Receita (Classificação)", list(analitica_rec_opcoes.keys()), key="inc_cr_anal")
                anal_id_sel_rec = analitica_rec_opcoes[anal_sel_rec]
                hist_padrao_vinc = analitica_rec_map_hist.get(anal_id_sel_rec)
                
                hist_keys_rec = list(hist_rec_opcoes.keys())
                hist_def_idx = 0
                if pd.notna(hist_padrao_vinc) and hist_padrao_vinc in list(hist_rec_opcoes.values()):
                    hist_def_idx = list(hist_rec_opcoes.values()).index(hist_padrao_vinc)

                with st.form("form_inc_conta_receber", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    data_venc = col1.date_input("Data de Vencimento / Previsão", value=date.today(), format="DD/MM/YYYY")
                    valor = col2.number_input("Valor da Receita (R$)", min_value=0.01, step=50.0, format="%.2f")
                    
                    cli_sel = col1.selectbox("Cliente", list(cli_opcoes.keys()))
                    hist_sel = col2.selectbox("Histórico Padrão", hist_keys_rec, index=hist_def_idx)
                    
                    complemento = st.text_input("Complemento do Histórico (Ex: Honorários Sucumbenciais Processo 1234/2026)")
                    
                    col_s1, col_s2 = st.columns(2)
                    status = col_s1.selectbox("Status", ["Pendente", "Concluído (Já Recebido)"], key="status_cr_inc")
                    
                    data_pgto = None
                    if status == "Concluído (Já Recebido)":
                        data_pgto = col_s2.date_input("Data de Recebimento", value=date.today(), format="DD/MM/YYYY", key="data_rec_cr_inc")
                    
                    if st.form_submit_button("Salvar Conta a Receber", type="primary"):
                        db_status = "Concluído" if "Concluído" in status else "Pendente"
                        add_lancamento(
                            tipo="Receita",
                            data_vencimento=data_venc,
                            valor=valor,
                            contato_id=cli_opcoes[cli_sel],
                            historico_id=hist_rec_opcoes[hist_sel],
                            conta_analitica_id=anal_id_sel_rec,
                            complemento=complemento.strip(),
                            status=db_status,
                            data_pagamento=data_pgto,
                            pago_por=None
                        )
                        st.success("Conta a receber registrada com sucesso!")
                        st.rerun()

        with cr_tab_baixa:
            st.markdown("#### ⚡ Baixa e Confirmação de Recebimentos")
            b_col1, b_col2 = st.columns(2)
            data_ini_venc = b_col1.date_input("Vencimento Inicial", value=date.today().replace(day=1), format="DD/MM/YYYY", key="cr_baixa_ini")
            data_fim_venc = b_col2.date_input("Vencimento Final", value=date.today(), format="DD/MM/YYYY", key="cr_baixa_fim")
            
            df_rec = get_lancamentos_df(tipo_filtro="Receita")
            if not df_rec.empty:
                df_rec_pend = df_rec[
                    (df_rec["status"] == "Pendente") &
                    (df_rec["data_vencimento"] >= str(data_ini_venc)) &
                    (df_rec["data_vencimento"] <= str(data_fim_venc))
                ].copy()
            else:
                df_rec_pend = pd.DataFrame()
                
            if df_rec_pend.empty:
                st.info("Nenhuma conta a receber pendente encontrada no período.")
            else:
                df_rec_pend["Baixar?"] = False
                df_rec_pend["data_vencimento"] = df_rec_pend["data_vencimento"].apply(formatar_data_br)
                col_ordem = ["Baixar?", "id", "data_vencimento", "contato", "conta_analitica", "historico_padrao", "complemento", "valor"]
                
                tabela_edit = st.data_editor(
                    df_rec_pend[col_ordem],
                    disabled=["id", "data_vencimento", "contato", "conta_analitica", "historico_padrao", "complemento", "valor"],
                    hide_index=True,
                    use_container_width=True,
                    key="editor_cr_baixas"
                )
                
                ids_sel = tabela_edit[tabela_edit["Baixar?"] == True]["id"].tolist()
                valor_tot = tabela_edit[tabela_edit["Baixar?"] == True]["valor"].sum()
                
                st.divider()
                st.markdown(f"**Títulos selecionados:** {len(ids_sel)} | **Valor Total:** R$ {valor_tot:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                if len(ids_sel) > 0:
                    with st.form("form_confirmar_cr_baixa"):
                        data_efetiva = st.date_input("Data Efetiva do Recebimento", value=date.today(), format="DD/MM/YYYY")
                        if st.form_submit_button(f"✅ Confirmar Recebimento de {len(ids_sel)} Título(s)", type="primary"):
                            baixar_lancamentos_em_lote(ids_sel, data_efetiva, pago_por=None)
                            st.success("Recebimento baixado com sucesso!")
                            st.rerun()

        with cr_tab_alt:
            df_rec_all = get_lancamentos_df(tipo_filtro="Receita")
            if df_rec_all.empty:
                st.info("Nenhuma conta a receber registrada para alteração.")
            else:
                opcoes_cr = {
                    f"ID {row['id']} | Venc: {formatar_data_br(row['data_vencimento'])} | {row['contato'] or 'S/ Cliente'} | R$ {row['valor']:.2f} ({row['status']})": row['id'] 
                    for _, row in df_rec_all.iterrows()
                }
                cr_sel = st.selectbox("Selecione a Conta a Receber para Alterar", list(opcoes_cr.keys()), key="sel_cr_alt")
                cr_id = opcoes_cr[cr_sel]
                item_cr = df_rec_all[df_rec_all["id"] == cr_id].iloc[0]
                
                cli_edit_map = {"(Opcional / Não informado)": None}
                if not clientes_df.empty:
                    for _, row in clientes_df.iterrows():
                        cli_edit_map[row["nome"]] = row["id"]
                        
                anal_rec_edit_map = {f"{row['conta_sintetica']} ➔ {row['conta_analitica']}": row["id"] for _, row in analiticas_rec_df.iterrows()}
                hist_rec_edit_map = {"(Sem histórico padrão)": None}
                if not historicos_rec_df.empty:
                    for _, row in historicos_rec_df.iterrows():
                        hist_rec_edit_map[f"{row['codigo']} - {row['descricao']}"] = row["id"]

                anal_keys = list(anal_rec_edit_map.keys())
                anal_idx = list(anal_rec_edit_map.values()).index(item_cr["conta_analitica_id"]) if item_cr["conta_analitica_id"] in list(anal_rec_edit_map.values()) else 0
                anal_sel = st.selectbox("Conta de Receita", anal_keys, index=anal_idx, key="edit_cr_anal_sel")
                anal_id = anal_rec_edit_map[anal_sel]
                
                hist_keys = list(hist_rec_edit_map.keys())
                hist_idx = list(hist_rec_edit_map.values()).index(item_cr["historico_id"]) if item_cr["historico_id"] in list(hist_rec_edit_map.values()) else 0
                hist_sel = st.selectbox("Histórico Padrão", hist_keys, index=hist_idx, key="edit_cr_hist_sel")

                with st.form("form_edit_conta_receber"):
                    col1, col2 = st.columns(2)
                    data_venc = col1.date_input("Data de Vencimento", value=parse_data_iso(item_cr["data_vencimento"]), format="DD/MM/YYYY")
                    valor = col2.number_input("Valor (R$)", min_value=0.01, step=50.0, value=float(item_cr["valor"]), format="%.2f")
                    
                    cli_keys = list(cli_edit_map.keys())
                    cli_idx = list(cli_edit_map.values()).index(item_cr["contato_id"]) if item_cr["contato_id"] in list(cli_edit_map.values()) else 0
                    cli_sel = col1.selectbox("Cliente", cli_keys, index=cli_idx)
                    
                    complemento = st.text_input("Complemento do Histórico", value=item_cr["complemento"] if pd.notna(item_cr["complemento"]) else "")
                    
                    col_e1, col_e2 = st.columns(2)
                    status_idx = 0 if item_cr["status"] == "Concluído" else 1
                    status_edit = col_e1.selectbox("Status", ["Concluído", "Pendente"], index=status_idx, key="cr_edit_status")
                    
                    data_pgto_val = parse_data_iso(item_cr["data_pagamento"]) if pd.notna(item_cr["data_pagamento"]) and item_cr["data_pagamento"] else date.today()
                    data_pgto_edit = None
                    if status_edit == "Concluído":
                        data_pgto_edit = col_e2.date_input("Data de Recebimento", value=data_pgto_val, format="DD/MM/YYYY", key="cr_edit_dtpg")
                    
                    if st.form_submit_button("Atualizar Conta a Receber", type="primary"):
                        update_lancamento(
                            lanc_id=cr_id,
                            tipo="Receita",
                            data_vencimento=data_venc,
                            data_pagamento=data_pgto_edit,
                            valor=valor,
                            contato_id=cli_edit_map[cli_sel],
                            historico_id=hist_rec_edit_map[hist_sel],
                            conta_analitica_id=anal_id,
                            complemento=complemento.strip(),
                            status=status_edit,
                            pago_por=None
                        )
                        st.success("Conta a receber atualizada com sucesso!")
                        st.rerun()

        with cr_tab_exc:
            df_rec_del = get_lancamentos_df(tipo_filtro="Receita")
            if df_rec_del.empty:
                st.info("Nenhuma conta a receber para exclusão.")
            else:
                opcoes_del_cr = {
                    f"ID {row['id']} | Venc: {formatar_data_br(row['data_vencimento'])} | {row['contato'] or 'S/ Cliente'} | R$ {row['valor']:.2f} ({row['status']})": row['id'] 
                    for _, row in df_rec_del.iterrows()
                }
                cr_del_sel = st.selectbox("Selecione a Conta a Receber para Excluir", list(opcoes_del_cr.keys()), key="del_cr_box")
                if st.button("🗑️ Confirmar Exclusão da Conta a Receber", type="primary"):
                    delete_lancamento(opcoes_del_cr[cr_del_sel])
                    st.success("Conta a receber excluída com sucesso!")
                    st.rerun()

    # 4. GERAR CONTAS A PAGAR
    elif menu == "⚡ Gerar Contas a Pagar":
        st.subheader("⚡ Geração Automática Mensal de Contas a Pagar")
        col_m1, col_m2 = st.columns(2)
        mes_atual = date.today().month
        ano_atual = date.today().year
        
        mes_selecionado = col_m1.selectbox("Mês de Referência", list(range(1, 13)), index=mes_atual - 1, format_func=lambda m: f"{m:02d} - {calendar.month_name[m]}")
        ano_selecionado = col_m2.number_input("Ano de Referência", min_value=2020, max_value=2040, value=ano_atual, step=1)
        mes_ref_str = f"{ano_selecionado:04d}-{mes_selecionado:02d}"
        
        df_recorrentes = get_contas_recorrentes()
        if df_recorrentes.empty:
            st.warning("Nenhuma conta recorrente configurada em Cadastros > Contas Recorrentes.")
        else:
            st.markdown(f"#### Contas pré-cadastradas ({len(df_recorrentes)} itens)")
            st.dataframe(df_recorrentes[["titulo", "fornecedor", "conta_analitica", "dia_vencimento", "valor", "pago_por_padrao"]], use_container_width=True)
            
            df_lanc_ex = get_lancamentos_df()
            gerados_no_mes = df_lanc_ex[df_lanc_ex["mes_referencia"] == mes_ref_str]
            if not gerados_no_mes.empty:
                st.info(f"Já existem **{len(gerados_no_mes)}** lançamento(s) gerados para {mes_ref_str}.")
                
            if st.button("🚀 Executar Geração de Contas", type="primary"):
                gerados, ignorados, msg = gerar_contas_do_mes(ano_selecionado, mes_selecionado)
                if gerados > 0:
                    st.success(f"✅ **{gerados}** contas foram geradas para {mes_ref_str}!")
                if ignorados > 0:
                    st.warning(f"⚠️ **{ignorados}** contas já existiam nessa competência.")
                if gerados == 0 and ignorados == 0:
                    st.error(msg)
                st.rerun()

    # 5. RELATÓRIOS
    elif menu == "📊 Relatórios":
        st.subheader("📊 Relatórios Financeiros e Gerenciais")
        tab_rel_pagar, tab_rel_receber, tab_rel_diario, tab_rel_analitico, tab_rel_plano, tab_rel_acerto = st.tabs([
            "🔴 Contas a Pagar (Pagamento)",
            "🟢 Contas a Receber (Recebimento)",
            "📅 Livro Diário de Lançamentos", 
            "📑 Demonstrativo Analítico / DRE", 
            "🌳 Plano de Contas em 3 Níveis", 
            "⚖️ Extrato de Acerto entre Sócios"
        ])
        
        df_base = get_lancamentos_df()
        if not df_base.empty:
            df_base["valor"] = pd.to_numeric(df_base["valor"])

        with tab_rel_pagar:
            st.markdown("#### 🔴 Relatório de Contas a Pagar (Base: Data de Pagamento)")
            p1_c1, p1_c2, p1_c3, p1_c4 = st.columns(4)
            p_ini = p1_c1.date_input("Data de Pagamento Inicial", value=date.today().replace(day=1), format="DD/MM/YYYY", key="rp_ini")
            p_fim = p1_c2.date_input("Data de Pagamento Final", value=date.today(), format="DD/MM/YYYY", key="rp_fim")
            p_status = p1_c3.selectbox("Status", ["Concluído (Pagos)", "Todos (Incluir Pendentes)", "Pendente (Sem Pagamento)"], key="rp_stat")
            
            fornecedores_lista = ["Todos"]
            df_forn = get_contatos("Fornecedor")
            if not df_forn.empty:
                fornecedores_lista += df_forn["nome"].tolist()
            p_forn = p1_c4.selectbox("Fornecedor", fornecedores_lista, key="rp_forn")
            
            if df_base.empty:
                st.info("Nenhum lançamento no sistema.")
            else:
                df_pagar = df_base[df_base["tipo"] == "Despesa"].copy()
                if p_status == "Concluído (Pagos)":
                    df_pagar = df_pagar[(df_pagar["status"] == "Concluído") & (df_pagar["data_pagamento"].notna()) & (df_pagar["data_pagamento"] >= str(p_ini)) & (df_pagar["data_pagamento"] <= str(p_fim))]
                elif p_status == "Pendente (Sem Pagamento)":
                    df_pagar = df_pagar[df_pagar["status"] == "Pendente"]
                else:
                    df_pagar = df_pagar[((df_pagar["data_pagamento"].notna()) & (df_pagar["data_pagamento"] >= str(p_ini)) & (df_pagar["data_pagamento"] <= str(p_fim))) | (df_pagar["status"] == "Pendente")]
                    
                if p_forn != "Todos":
                    df_pagar = df_pagar[df_pagar["contato"] == p_forn]
                    
                total_pend = df_pagar[df_pagar["status"] == "Pendente"]["valor"].sum()
                total_pago = df_pagar[df_pagar["status"] == "Concluído"]["valor"].sum()
                total_geral = df_pagar["valor"].sum()
                
                k1, k2, k3 = st.columns(3)
                k1.metric("Total Pago no Período", f"R$ {total_pago:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                k2.metric("Total Pendente", f"R$ {total_pend:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                k3.metric("Total Geral Filtrado", f"R$ {total_geral:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                colunas_p = ["id", "data_pagamento", "data_vencimento", "contato", "conta_analitica", "historico_padrao", "complemento", "valor", "status", "pago_por"]
                df_view_p = df_pagar[colunas_p].copy()
                df_view_p["data_vencimento"] = df_view_p["data_vencimento"].apply(formatar_data_br)
                df_view_p["data_pagamento"] = df_view_p["data_pagamento"].apply(formatar_data_br)
                st.dataframe(df_view_p.rename(columns={"contato": "Fornecedor", "data_pagamento": "Data Pagamento", "data_vencimento": "Data Vencimento"}), use_container_width=True)

        with tab_rel_receber:
            st.markdown("#### 🟢 Relatório de Contas a Receber (Base: Data de Recebimento)")
            r1_c1, r1_c2, r1_c3, r1_c4 = st.columns(4)
            r_ini = r1_c1.date_input("Data de Recebimento Inicial", value=date.today().replace(day=1), format="DD/MM/YYYY", key="rr_ini")
            r_fim = r1_c2.date_input("Data de Recebimento Final", value=date.today(), format="DD/MM/YYYY", key="rr_fim")
            r_status = r1_c3.selectbox("Status", ["Concluído (Recebidos)", "Todos (Incluir Pendentes)", "Pendente (Sem Recebimento)"], key="rr_stat")
            
            clientes_lista = ["Todos"]
            df_cli = get_contatos("Cliente")
            if not df_cli.empty:
                clientes_lista += df_cli["nome"].tolist()
            r_cli = r1_c4.selectbox("Cliente", clientes_lista, key="rr_cli")
            
            if df_base.empty:
                st.info("Nenhum lançamento no sistema.")
            else:
                df_receber = df_base[df_base["tipo"] == "Receita"].copy()
                if r_status == "Concluído (Recebidos)":
                    df_receber = df_receber[(df_receber["status"] == "Concluído") & (df_receber["data_pagamento"].notna()) & (df_receber["data_pagamento"] >= str(r_ini)) & (df_receber["data_pagamento"] <= str(r_fim))]
                elif r_status == "Pendente (Sem Recebimento)":
                    df_receber = df_receber[df_receber["status"] == "Pendente"]
                else:
                    df_receber = df_receber[((df_receber["data_pagamento"].notna()) & (df_receber["data_pagamento"] >= str(r_ini)) & (df_receber["data_pagamento"] <= str(r_fim))) | (df_receber["status"] == "Pendente")]
                    
                if r_cli != "Todos":
                    df_receber = df_receber[df_receber["contato"] == r_cli]
                    
                total_rec_pend = df_receber[df_receber["status"] == "Pendente"]["valor"].sum()
                total_recebido = df_receber[df_receber["status"] == "Concluído"]["valor"].sum()
                total_rec_geral = df_receber["valor"].sum()
                
                rk1, rk2, rk3 = st.columns(3)
                rk1.metric("Total Recebido no Período", f"R$ {total_recebido:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                rk2.metric("Total a Receber (Pendente)", f"R$ {total_rec_pend:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                rk3.metric("Total Geral Filtrado", f"R$ {total_rec_geral:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                colunas_r = ["id", "data_pagamento", "data_vencimento", "contato", "conta_analitica", "historico_padrao", "complemento", "valor", "status"]
                df_view_r = df_receber[colunas_r].copy()
                df_view_r["data_vencimento"] = df_view_r["data_vencimento"].apply(formatar_data_br)
                df_view_r["data_pagamento"] = df_view_r["data_pagamento"].apply(formatar_data_br)
                st.dataframe(df_view_r.rename(columns={"contato": "Cliente", "data_pagamento": "Data Recebimento", "data_vencimento": "Data Vencimento"}), use_container_width=True)

        with tab_rel_diario:
            st.markdown("#### 📅 Livro Diário de Lançamentos")
            r1_c1, r1_c2, r1_c3, r1_c4 = st.columns(4)
            criterio_data = r1_c1.selectbox("Filtrar por qual Data?", ["Data de Pagamento/Efetivação", "Data de Vencimento"])
            col_data_filtro = "data_pagamento" if criterio_data == "Data de Pagamento/Efetivação" else "data_vencimento"
            data_ini = r1_c2.date_input("Data Inicial", value=date.today().replace(day=1), format="DD/MM/YYYY", key="r1_ini")
            data_fim = r1_c3.date_input("Data Final", value=date.today(), format="DD/MM/YYYY", key="r1_fim")
            status_r1 = r1_c4.multiselect("Status", ["Concluído", "Pendente"], default=["Concluído", "Pendente"], key="r1_stat")
            
            if not df_base.empty:
                df_diario = df_base.dropna(subset=[col_data_filtro]).copy() if col_data_filtro == "data_pagamento" else df_base.copy()
                df_diario = df_diario[(df_diario[col_data_filtro] >= str(data_ini)) & (df_diario[col_data_filtro] <= str(data_fim)) & (df_diario["status"].isin(status_r1))].sort_values(by=col_data_filtro, ascending=True)
                
                rec_d = df_diario[df_diario["tipo"] == "Receita"]["valor"].sum()
                desp_d = df_diario[df_diario["tipo"] == "Despesa"]["valor"].sum()
                saldo_d = rec_d - desp_d
                
                k1, k2, k3 = st.columns(3)
                k1.metric("Total Entradas", f"R$ {rec_d:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                k2.metric("Total Saídas", f"R$ {desp_d:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                k3.metric("Saldo Líquido", f"R$ {saldo_d:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                colunas_d = ["id", "data_pagamento", "data_vencimento", "tipo", "contato", "conta_analitica", "historico_padrao", "complemento", "valor", "status", "pago_por"]
                df_view_d = df_diario[colunas_d].copy()
                df_view_d["data_vencimento"] = df_view_d["data_vencimento"].apply(formatar_data_br)
                df_view_d["data_pagamento"] = df_view_d["data_pagamento"].apply(formatar_data_br)
                st.dataframe(df_view_d, use_container_width=True)

        with tab_rel_analitico:
            st.markdown("#### 📑 Demonstrativo Analítico por Plano de Contas")
            r2_c1, r2_c2 = st.columns(2)
            r2_ini = r2_c1.date_input("Período Inicial (Vencimento)", value=date.today().replace(day=1), format="DD/MM/YYYY", key="r2_ini")
            r2_fim = r2_c2.date_input("Período Final (Vencimento)", value=date.today(), format="DD/MM/YYYY", key="r2_fim")
            
            if not df_base.empty:
                df_dre = df_base[(df_base["data_vencimento"] >= str(r2_ini)) & (df_base["data_vencimento"] <= str(r2_fim))].copy()
                if not df_dre.empty:
                    df_dre["Valor Realizado"] = df_dre.apply(lambda r: r["valor"] if r["status"] == "Concluído" else 0.0, axis=1)
                    df_dre["Valor Pendente"] = df_dre.apply(lambda r: r["valor"] if r["status"] == "Pendente" else 0.0, axis=1)
                    agrupado = df_dre.groupby(["tipo", "conta_sintetica", "conta_analitica"]).agg(
                        Total_Previsto=("valor", "sum"),
                        Total_Realizado=("Valor Realizado", "sum"),
                        Total_Pendente=("Valor Pendente", "sum"),
                        Qtd_Lancamentos=("id", "count")
                    ).reset_index()
                    st.dataframe(agrupado, use_container_width=True)

        with tab_rel_plano:
            st.markdown("#### 🌳 Estrutura do Plano de Contas em 3 Níveis")
            df_plano_analiticas = get_contas_analiticas()
            df_plano_sinteticas = get_contas_sinteticas()

            if not df_plano_sinteticas.empty:
                linhas_plano = []
                for tipo in ["Receita", "Despesa"]:
                    cod_raiz = "1" if tipo == "Receita" else "2"
                    linhas_plano.append({
                        "Nível": "Nível 1 (Raiz)", "Classificação / Código": cod_raiz, "Descrição da Conta": f"{cod_raiz} - {tipo.upper()}S", "Tipo de Conta": "Sintética", "Histórico Padrão": "-"
                    })
                    sint_tipo = df_plano_sinteticas[df_plano_sinteticas["tipo"] == tipo].reset_index(drop=True)
                    for idx_s, sint in sint_tipo.iterrows():
                        cod_sint = f"{cod_raiz}.{idx_s + 1}"
                        linhas_plano.append({
                            "Nível": "  ├── Nível 2 (Sintética)", "Classificação / Código": cod_sint, "Descrição da Conta": f"  📁 {sint['nome']}", "Tipo de Conta": "Sintética", "Histórico Padrão": "-"
                        })
                        if not df_plano_analiticas.empty:
                            anal_sint = df_plano_analiticas[df_plano_analiticas["sintetica_id"] == sint["id"]].reset_index(drop=True)
                            for idx_a, anal in anal_sint.iterrows():
                                cod_anal = f"{cod_sint}.{idx_a + 1:02d}"
                                hist_vinc = anal["historico_padrao_nome"] if pd.notna(anal["historico_padrao_nome"]) else "Nenhum"
                                lines_3 = {
                                    "Nível": "  │   └── Nível 3 (Analítica)", "Classificação / Código": cod_anal, "Descrição da Conta": f"      📄 {anal['conta_analitica']}", "Tipo de Conta": "Analítica", "Histórico Padrão": hist_vinc
                                }
                                linhas_plano.append(lines_3)
                st.dataframe(pd.DataFrame(linhas_plano), use_container_width=True, hide_index=True)

        with tab_rel_acerto:
            st.markdown("#### ⚖️ Extrato de Acerto entre Sócios (50/50)")
            r4_c1, r4_c2 = st.columns(2)
            r4_ini = r4_c1.date_input("Data de Pagamento Inicial", value=date.today().replace(day=1), format="DD/MM/YYYY", key="r4_ini")
            r4_fim = r4_c2.date_input("Data de Pagamento Final", value=date.today(), format="DD/MM/YYYY", key="r4_fim")
            
            if not df_base.empty:
                df_acerto = df_base[(df_base["tipo"] == "Despesa") & (df_base["status"] == "Concluído") & (df_base["data_pagamento"].notna()) & (df_base["data_pagamento"] >= str(r4_ini)) & (df_base["data_pagamento"] <= str(r4_fim))].copy()
                if not df_acerto.empty:
                    pago_fab = df_acerto[df_acerto["pago_por"] == "Fabrício"]["valor"].sum()
                    pago_fabi = df_acerto[df_acerto["pago_por"] == "Fabíola"]["valor"].sum()
                    dif_per = (pago_fab - pago_fabi) / 2
                    
                    ac1, ac2, ac3 = st.columns(3)
                    ac1.metric("Pago por Fabrício", f"R$ {pago_fab:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    ac2.metric("Pago por Fabíola", f"R$ {pago_fabi:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    with ac3:
                        if dif_per > 0:
                            st.success(f"**Fabíola deve a Fabrício:**  \n### R$ {dif_per:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                        elif dif_per < 0:
                            st.info(f"**Fabrício deve a Fabíola:**  \n### R$ {abs(dif_per):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                        else:
                            st.success("**Contas equilibradas!**")
                    
                    df_acerto_view = df_acerto[["data_pagamento", "contato", "conta_analitica", "historico_padrao", "complemento", "valor", "pago_por"]].copy()
                    df_acerto_view["data_pagamento"] = df_acerto_view["data_pagamento"].apply(formatar_data_br)
                    st.dataframe(df_acerto_view, use_container_width=True)

    # 6. CADASTROS FINANCEIROS
    elif menu == "Cadastros":
        st.subheader("Cadastros do Sistema Financeiro")
        st.info("Para manutenções de apoio completas, utilize também o módulo **'🛠️ Manutenção de Tabelas (CRUDs)'** no menu lateral.")
        tab_rec, tab_regras = st.tabs(["⚡ Contas Recorrentes", "⚙️ Regras de Classificação"])
        
        with tab_rec:
            st.dataframe(get_contas_recorrentes(), use_container_width=True)
        with tab_regras:
            st.dataframe(get_regras_classificacao(), use_container_width=True)

# ====================================================
# SISTEMA 3: AGENDA DE COMPROMISSOS (ESTILO GOOGLE CALENDAR)
# ====================================================
elif sistema_ativo == "📅 Agenda de Compromissos":
    st.title("📅 Fabíola Guimarães Advocacia — Agenda de Compromissos")
    
    ag_tab_visao, ag_tab_novo, ag_tab_gerenciar = st.tabs([
        "📆 Visualizar Agenda", 
        "➕ Novo Compromisso", 
        "⚙️ Gerenciar / Alterar"
    ])
    
    with ag_tab_visao:
        df_comp = get_compromissos_df(usuario_logado_id=operador_atual_id)
        
        c_v1, c_v2, c_v3 = st.columns([1, 1, 1])
        modo_visao = c_v1.radio("Modo de Visualização", ["Próximos", "Dia Específico", "Semana"], horizontal=True)
        data_base_visao = c_v2.date_input("Data de Referência", value=date.today(), format="DD/MM/YYYY")
        
        if df_comp.empty:
            st.info("Nenhum compromisso cadastrado ou visível para seu usuário.")
        else:
            df_comp_filtrado = df_comp.copy()
            data_base_str = str(data_base_visao)
            
            if modo_visao == "Dia Específico":
                df_comp_filtrado = df_comp_filtrado[
                    (df_comp_filtrado["data_inicio"] <= data_base_str) & 
                    (df_comp_filtrado["data_fim"] >= data_base_str)
                ]
            elif modo_visao == "Semana":
                ini_semana = data_base_visao - timedelta(days=data_base_visao.weekday())
                fim_semana = ini_semana + timedelta(days=6)
                df_comp_filtrado = df_comp_filtrado[
                    (df_comp_filtrado["data_fim"] >= str(ini_semana)) & 
                    (df_comp_filtrado["data_inicio"] <= str(fim_semana))
                ]
            else:
                df_comp_filtrado = df_comp_filtrado[df_comp_filtrado["data_fim"] >= str(date.today())]
                
            c_v3.metric("Total de Compromissos", len(df_comp_filtrado))
            st.divider()
            
            if df_comp_filtrado.empty:
                st.info("Nenhum compromisso encontrado para o período selecionado.")
            else:
                cols_comp_exib = ["id", "titulo", "data_inicio", "hora_inicio", "data_fim", "hora_fim", "dia_inteiro", "local_link", "organizador", "cliente", "processo_ref", "descricao"]
                df_view_c = df_comp_filtrado[cols_comp_exib].copy()
                df_view_c["data_inicio"] = df_view_c["data_inicio"].apply(formatar_data_br)
                df_view_c["data_fim"] = df_view_c["data_fim"].apply(formatar_data_br)
                df_view_c["dia_inteiro"] = df_view_c["dia_inteiro"].apply(lambda x: "Sim" if x == 1 else "Não")
                st.dataframe(df_view_c, use_container_width=True)

    with ag_tab_novo:
        st.markdown("#### Agendar Novo Compromisso / Audiência / Reunião")
        
        df_u_ativos = get_usuarios(apenas_ativos=True)
        df_cli_comp = get_contatos("Cliente")
        
        u_map_comp = dict(zip(df_u_ativos["nome"], df_u_ativos["id"])) if not df_u_ativos.empty else {}
        c_map_comp = {"(Nenhum / Administrativo)": None}
        if not df_cli_comp.empty:
            for _, rc in df_cli_comp.iterrows():
                c_map_comp[rc["nome"]] = rc["id"]
                
        col_cv1, col_cv2 = st.columns(2)
        vis_comp = col_cv1.radio("Visibilidade", ["Compartilhado com Participantes", "Privado (Apenas Eu)"], key="rad_vis_comp_novo")
        vis_comp_db = "Privada" if "Privado" in vis_comp else "Compartilhada"
        
        participantes_selecionados = []
        if vis_comp_db == "Compartilhada":
            outros_u = {nome: uid for nome, uid in u_map_comp.items() if uid != operador_atual_id}
            if outros_u:
                convidados = col_cv2.multiselect("Convidados / Participantes:", list(outros_u.keys()))
                participantes_selecionados = [outros_u[nome] for nome in convidados]
            else:
                col_cv2.info("Apenas você está cadastrado no sistema.")
                
        dia_inteiro_chk = st.checkbox("Evento de dia inteiro", value=False)
        
        with st.form("form_novo_compromisso", clear_on_submit=True):
            col_cn1, col_cn2 = st.columns(2)
            titulo_c = col_cn1.text_input("Título do Compromisso (Ex: Audiência de Instrução, Reunião com Cliente)")
            local_c = col_cn2.text_input("Local ou Link da Reunião (Ex: Sala 02, Fórum BH, Link Google Meet)")
            
            col_cd1, col_cd2, col_cd3, col_cd4 = st.columns(4)
            dt_ini_c = col_cd1.date_input("Data de Início", value=date.today(), format="DD/MM/YYYY")
            hora_ini_c = col_cd2.time_input("Horário de Início", value=time(9, 0), disabled=dia_inteiro_chk)
            
            dt_fim_c = col_cd3.date_input("Data de Término", value=date.today(), format="DD/MM/YYYY")
            hora_fim_c = col_cd4.time_input("Horário de Término", value=time(10, 0), disabled=dia_inteiro_chk)
            
            col_cc1, col_cc2 = st.columns(2)
            cli_c = col_cc1.selectbox("Cliente Vinculado", list(c_map_comp.keys()))
            proc_c = col_cc2.text_input("Nº do Processo (Opcional)")
            
            desc_c = st.text_area("Anotações e Pauta do Compromisso")
            
            if st.form_submit_button("Salvar Compromisso", type="primary"):
                if titulo_c.strip():
                    add_compromisso(
                        titulo=titulo_c.strip(),
                        descricao=desc_c.strip(),
                        data_inicio=dt_ini_c,
                        hora_inicio=hora_ini_c.strftime("%H:%M") if not dia_inteiro_chk else None,
                        data_fim=dt_fim_c,
                        hora_fim=hora_fim_c.strftime("%H:%M") if not dia_inteiro_chk else None,
                        dia_inteiro=dia_inteiro_chk,
                        local_link=local_c.strip(),
                        cliente_id=c_map_comp[cli_c],
                        processo_ref=proc_c.strip(),
                        organizador_id=operador_atual_id,
                        visibilidade=vis_comp_db,
                        participantes_ids=participantes_selecionados
                    )
                    st.success("Compromisso agendado com sucesso!")
                    st.rerun()
                else:
                    st.warning("Informe o título do compromisso.")

    with ag_tab_gerenciar:
        st.markdown("#### Editar ou Cancelar Compromissos")
        df_comp_all = get_compromissos_df(usuario_logado_id=operador_atual_id)
        if df_comp_all.empty:
            st.info("Nenhum compromisso disponível para alteração.")
        else:
            opcoes_comp = {f"ID {r['id']} | {r['titulo']} ({formatar_data_br(r['data_inicio'])} às {r['hora_inicio'] or 'Dia todo'})": r["id"] for _, r in df_comp_all.iterrows()}
            comp_sel = st.selectbox("Selecione o Compromisso", list(opcoes_comp.keys()))
            comp_id = opcoes_comp[comp_sel]
            item_c = df_comp_all[df_comp_all["id"] == comp_id].iloc[0]
            
            df_u_ativos = get_usuarios(apenas_ativos=True)
            df_cli_comp = get_contatos("Cliente")
            u_map_c = dict(zip(df_u_ativos["nome"], df_u_ativos["id"])) if not df_u_ativos.empty else {}
            c_map_c = {"(Nenhum / Administrativo)": None}
            if not df_cli_comp.empty:
                for _, rc in df_cli_comp.iterrows():
                    c_map_c[rc["nome"]] = rc["id"]
                    
            col_cve1, col_cve2 = st.columns(2)
            vis_c_idx = 0 if item_c["visibilidade"] == "Privada" else 1
            vis_c_rad = col_cve1.radio("Visibilidade", ["Privado (Apenas Eu)", "Compartilhado com Participantes"], index=vis_c_idx, key="rad_c_edit")
            vis_c_db = "Privada" if "Privado" in vis_c_rad else "Compartilhada"
            
            participantes_c_edit = []
            if vis_c_db == "Compartilhada":
                outros_uc = {nome: uid for nome, uid in u_map_c.items() if uid != operador_atual_id}
                ja_part_ids = get_participantes_compromisso(comp_id)
                nomes_ja_part = [nome for nome, uid in outros_uc.items() if uid in ja_part_ids]
                
                convidados_edit = col_cve2.multiselect("Participantes:", list(outros_uc.keys()), default=nomes_ja_part)
                participantes_c_edit = [outros_uc[nome] for nome in convidados_edit]
                
            dia_int_edit = st.checkbox("Evento de dia inteiro", value=bool(item_c["dia_inteiro"]), key="chk_dia_int_edit")

            with st.form("form_edit_compromisso"):
                col_ce1, col_ce2 = st.columns(2)
                tit_ce = col_ce1.text_input("Título", value=item_c["titulo"])
                local_ce = col_ce2.text_input("Local ou Link", value=item_c["local_link"] if pd.notna(item_c["local_link"]) else "")
                
                col_cd1, col_cd2, col_cd3, col_cd4 = st.columns(4)
                dt_ini_ce = col_cd1.date_input("Início", value=parse_data_iso(item_c["data_inicio"]), format="DD/MM/YYYY", key="ce_dt_ini")
                hora_ini_ce = col_cd2.time_input("Horário Início", value=parse_hora_str(item_c["hora_inicio"]), disabled=dia_int_edit, key="ce_hr_ini")
                
                dt_fim_ce = col_cd3.date_input("Término", value=parse_data_iso(item_c["data_fim"]), format="DD/MM/YYYY", key="ce_dt_fim")
                hora_fim_ce = col_cd4.time_input("Horário Término", value=parse_hora_str(item_c["hora_fim"]), disabled=dia_int_edit, key="ce_hr_fim")
                
                col_cc1, col_cc2 = st.columns(2)
                cli_keys_c = list(c_map_c.keys())
                cli_idx_c = list(c_map_c.values()).index(item_c["cliente_id"]) if item_c["cliente_id"] in list(c_map_c.values()) else 0
                cli_ce = col_cc1.selectbox("Cliente", cli_keys_c, index=cli_idx_c, key="ce_cli")
                proc_ce = col_cc2.text_input("Processo", value=item_c["processo_ref"] if pd.notna(item_c["processo_ref"]) else "", key="ce_proc")
                
                desc_ce = st.text_area("Anotações", value=item_c["descricao"] if pd.notna(item_c["descricao"]) else "")
                
                if st.form_submit_button("Atualizar Compromisso", type="primary"):
                    update_compromisso(
                        comp_id=comp_id,
                        titulo=tit_ce.strip(),
                        descricao=desc_ce.strip(),
                        data_inicio=dt_ini_ce,
                        hora_inicio=hora_ini_ce.strftime("%H:%M") if not dia_int_edit else None,
                        data_fim=dt_fim_ce,
                        hora_fim=hora_fim_ce.strftime("%H:%M") if not dia_int_edit else None,
                        dia_inteiro=dia_int_edit,
                        local_link=local_ce.strip(),
                        cliente_id=c_map_c[cli_ce],
                        processo_ref=proc_ce.strip(),
                        visibilidade=vis_c_db,
                        participantes_ids=participantes_c_edit
                    )
                    st.success("Compromisso atualizado com sucesso!")
                    st.rerun()
                    
            if st.button("🗑️ Excluir este Compromisso", type="secondary"):
                delete_compromisso(comp_id)
                st.success("Compromisso excluído com sucesso!")
                st.rerun()

# ====================================================
# SISTEMA 4: MANUTENÇÃO DE TABELAS (CRUDs COMPLETOS)
# ====================================================
elif sistema_ativo == "🛠️ Manutenção de Tabelas (CRUDs)":
    st.title("🛠️ Manutenção de Tabelas e Cadastros")
    st.markdown("Gerencie centralizadamente todas as tabelas de apoio do escritório.")
    
    tab_crud_tipos, tab_crud_grupos_t, tab_crud_plano, tab_crud_hist, tab_crud_contatos, tab_crud_regras = st.tabs([
        "🏷️ Tipos de Tarefas", 
        "📂 Grupos de Tarefas (2 Níveis)", 
        "🌳 Plano de Contas", 
        "📑 Históricos Padrão", 
        "👥 Clientes e Fornecedores",
        "⚙️ Regras de Classificação"
    ])
    
    # 1. CRUD TIPOS DE TAREFAS
    with tab_crud_tipos:
        st.subheader("Tipos de Tarefas (Particular, Trabalho, etc.)")
        c1, c2, c3 = st.tabs(["➕ Incluir", "✏️ Alterar", "🗑️ Excluir"])
        
        with c1:
            with st.form("form_inc_tipo_t", clear_on_submit=True):
                nome_tt = st.text_input("Nome do Tipo de Tarefa")
                if st.form_submit_button("Salvar Tipo"):
                    if nome_tt.strip() and add_tipo_tarefa(nome_tt):
                        st.success("Tipo cadastrado!")
                        st.rerun()
                    else:
                        st.error("Erro ao cadastrar (verifique se já existe).")
                        
        with c2:
            df_tt = get_tipos_tarefas()
            if not df_tt.empty:
                map_tt = dict(zip(df_tt["nome"], df_tt["id"]))
                sel_tt = st.selectbox("Selecione para Alterar", list(map_tt.keys()), key="alt_tt_box")
                with st.form("form_alt_tipo_t"):
                    novo_nome_tt = st.text_input("Novo Nome", value=sel_tt)
                    if st.form_submit_button("Atualizar Tipo"):
                        if novo_nome_tt.strip() and update_tipo_tarefa(map_tt[sel_tt], novo_nome_tt):
                            st.success("Tipo atualizado!")
                            st.rerun()
            else:
                st.info("Nenhum tipo cadastrado.")
                
        with c3:
            df_tt = get_tipos_tarefas()
            if not df_tt.empty:
                map_tt = dict(zip(df_tt["nome"], df_tt["id"]))
                del_tt = st.selectbox("Selecione para Excluir", list(map_tt.keys()), key="del_tt_box")
                if st.button("Excluir Tipo de Tarefa", type="primary"):
                    delete_tipo_tarefa(map_tt[del_tt])
                    st.success("Tipo excluído!")
                    st.rerun()
            else:
                st.info("Nenhum tipo cadastrado.")
                
        st.dataframe(get_tipos_tarefas(), use_container_width=True)

    # 2. CRUD GRUPOS DE TAREFAS (2 NÍVEIS)
    with tab_crud_grupos_t:
        st.subheader("Grupos e Subgrupos de Tarefas (Estrutura em 2 Níveis)")
        sub_gt1, sub_gt2 = st.tabs(["Nível 1: Grupos", "Nível 2: Subgrupos"])
        
        with sub_gt1:
            g1_inc, g1_alt, g1_exc = st.tabs(["➕ Incluir", "✏️ Alterar", "🗑️️ Excluir"])
            with g1_inc:
                with st.form("form_inc_g1", clear_on_submit=True):
                    nome_g1 = st.text_input("Nome do Grupo (Nível 1)")
                    if st.form_submit_button("Salvar Grupo N1"):
                        if nome_g1.strip() and add_grupo_tarefas_n1(nome_g1):
                            st.success("Grupo N1 salvo!")
                            st.rerun()
            with g1_alt:
                df_g1 = get_grupos_tarefas_n1()
                if not df_g1.empty:
                    map_g1 = dict(zip(df_g1["nome"], df_g1["id"]))
                    sel_g1 = st.selectbox("Selecione Grupo para Alterar", list(map_g1.keys()))
                    with st.form("form_alt_g1"):
                        n_g1 = st.text_input("Novo Nome", value=sel_g1)
                        if st.form_submit_button("Atualizar"):
                            update_grupo_tarefas_n1(map_g1[sel_g1], n_g1)
                            st.success("Atualizado!")
                            st.rerun()
            with g1_exc:
                df_g1 = get_grupos_tarefas_n1()
                if not df_g1.empty:
                    map_g1 = dict(zip(df_g1["nome"], df_g1["id"]))
                    del_g1 = st.selectbox("Selecione Grupo para Excluir", list(map_g1.keys()))
                    st.warning("⚠️ Ao excluir o Grupo N1, todos os subgrupos vinculados serão removidos.")
                    if st.button("Excluir Grupo N1", type="primary"):
                        delete_grupo_tarefas_n1(map_g1[del_g1])
                        st.success("Excluído!")
                        st.rerun()
            st.dataframe(get_grupos_tarefas_n1(), use_container_width=True)

        with sub_gt2:
            g2_inc, g2_alt, g2_exc = st.tabs(["➕ Incluir", "✏️ Alterar", "🗑️ Excluir"])
            df_g1_disp = get_grupos_tarefas_n1()
            
            with g2_inc:
                if df_g1_disp.empty:
                    st.warning("Cadastre primeiro um Grupo de Nível 1.")
                else:
                    map_g1 = dict(zip(df_g1_disp["nome"], df_g1_disp["id"]))
                    with st.form("form_inc_g2", clear_on_submit=True):
                        pai_g1 = st.selectbox("Grupo Superior (Nível 1)", list(map_g1.keys()))
                        nome_g2 = st.text_input("Nome do Subgrupo (Nível 2)")
                        if st.form_submit_button("Salvar Subgrupo N2"):
                            if nome_g2.strip() and add_grupo_tarefas_n2(map_g1[pai_g1], nome_g2):
                                st.success("Subgrupo N2 salvo!")
                                st.rerun()
            with g2_alt:
                df_g2 = get_grupos_tarefas_n2()
                if not df_g2.empty and not df_g1_disp.empty:
                    map_g2 = dict(zip(df_g2["caminho_completo"], df_g2["id"]))
                    sel_g2 = st.selectbox("Selecione Subgrupo para Alterar", list(map_g2.keys()))
                    item_g2 = df_g2[df_g2["id"] == map_g2[sel_g2]].iloc[0]
                    map_g1 = dict(zip(df_g1_disp["nome"], df_g1_disp["id"]))
                    with st.form("form_alt_g2"):
                        idx_p = list(map_g1.values()).index(item_g2["grupo_n1_id"]) if item_g2["grupo_n1_id"] in list(map_g1.values()) else 0
                        novo_p = st.selectbox("Grupo Superior (Nível 1)", list(map_g1.keys()), index=idx_p)
                        novo_n2 = st.text_input("Nome do Subgrupo", value=item_g2["subgrupo_n2"])
                        if st.form_submit_button("Atualizar"):
                            update_grupo_tarefas_n2(item_g2["id"], map_g1[novo_p], novo_n2)
                            st.success("Atualizado!")
                            st.rerun()
            with g2_exc:
                df_g2 = get_grupos_tarefas_n2()
                if not df_g2.empty:
                    map_g2 = dict(zip(df_g2["caminho_completo"], df_g2["id"]))
                    del_g2 = st.selectbox("Selecione Subgrupo para Excluir", list(map_g2.keys()))
                    if st.button("Excluir Subgrupo N2", type="primary"):
                        delete_grupo_tarefas_n2(map_g2[del_g2])
                        st.success("Excluído!")
                        st.rerun()
            st.dataframe(get_grupos_tarefas_n2()[["id", "grupo_n1", "subgrupo_n2"]], use_container_width=True)

    # 3. CRUD PLANO DE CONTAS
    with tab_crud_plano:
        st.subheader("Plano de Contas Financeiro")
        sub_pc_sint, sub_pc_anal = st.tabs(["Contas Sintéticas (Grupos)", "Contas Analíticas (Subgrupos)"])
        
        with sub_pc_sint:
            s_inc, s_alt, s_exc = st.tabs(["➕ Incluir", "✏️ Alterar", "🗑️ Excluir"])
            with s_inc:
                with st.form("form_inc_sint_m", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    tipo_sint = c1.selectbox("Tipo da Conta Raiz", ["Receita", "Despesa"], key="sint_m_tipo")
                    nome_sint = c2.text_input("Nome da Conta Sintética (Ex: Operacionais, Administrativas)")
                    if st.form_submit_button("Salvar Conta Sintética"):
                        if nome_sint.strip() and add_conta_sintetica(tipo_sint, nome_sint.strip()):
                            st.success("Conta Sintética cadastrada!")
                            st.rerun()
                        else:
                            st.error("Erro: Verifique se o nome foi preenchido ou se já existe.")
            with s_alt:
                df_sint_m = get_contas_sinteticas()
                if not df_sint_m.empty:
                    sint_map_m = {f"[{r['tipo']}] {r['nome']}": r["id"] for _, r in df_sint_m.iterrows()}
                    sel_sint_m = st.selectbox("Selecione para Alterar", list(sint_map_m.keys()), key="alt_sint_m_box")
                    item_sm = df_sint_m[df_sint_m["id"] == sint_map_m[sel_sint_m]].iloc[0]
                    with st.form("form_alt_sint_m"):
                        col1, col2 = st.columns(2)
                        t_idx = 0 if item_sm["tipo"] == "Receita" else 1
                        novo_t_sint = col1.selectbox("Tipo", ["Receita", "Despesa"], index=t_idx, key="alt_t_sint_m")
                        novo_n_sint = col2.text_input("Nome da Conta Sintética", value=item_sm["nome"])
                        if st.form_submit_button("Atualizar Conta Sintética"):
                            if novo_n_sint.strip() and update_conta_sintetica(item_sm["id"], novo_t_sint, novo_n_sint.strip()):
                                st.success("Conta Sintética atualizada!")
                                st.rerun()
                else:
                    st.info("Nenhuma conta sintética cadastrada.")
            with s_exc:
                df_sint_m = get_contas_sinteticas()
                if not df_sint_m.empty:
                    sint_map_m = {f"[{r['tipo']}] {r['nome']}": r["id"] for _, r in df_sint_m.iterrows()}
                    sel_sint_del = st.selectbox("Selecione para Excluir", list(sint_map_m.keys()), key="del_sint_m_box")
                    st.warning("⚠️ Ao excluir uma conta sintética, as contas analíticas subordinadas a ela também serão excluídas.")
                    if st.button("Excluir Conta Sintética", type="primary"):
                        delete_conta_sintetica(sint_map_m[sel_sint_del])
                        st.success("Conta Sintética excluída!")
                        st.rerun()
                else:
                    st.info("Nenhuma conta sintética cadastrada.")
            st.dataframe(get_contas_sinteticas(), use_container_width=True)

        with sub_pc_anal:
            a_inc, a_alt, a_exc = st.tabs(["➕ Incluir", "✏️ Alterar", "🗑️ Excluir"])
            df_sint_disp_m = get_contas_sinteticas()
            df_hist_todos_m = get_historicos()
            
            hist_anal_opcoes_m = {"(Nenhum / Não associar)": None}
            if not df_hist_todos_m.empty:
                for _, r in df_hist_todos_m.iterrows():
                    hist_anal_opcoes_m[f"{r['codigo']} - {r['descricao']} ({r['tipo_aplicavel']})"] = r["id"]

            with a_inc:
                if df_sint_disp_m.empty:
                    st.warning("Cadastre primeiro uma Conta Sintética.")
                else:
                    sint_opcoes_m = {f"[{r['tipo']}] {r['nome']}": r["id"] for _, r in df_sint_disp_m.iterrows()}
                    with st.form("form_inc_anal_m", clear_on_submit=True):
                        s_pai_m = st.selectbox("Conta Sintética Superior", list(sint_opcoes_m.keys()))
                        n_anal_m = st.text_input("Nome da Conta Analítica (Ex: Aluguel, Software, Honorários Iniciais)")
                        h_anal_sel_m = st.selectbox("Histórico Padrão Vinculado (Opcional)", list(hist_anal_opcoes_m.keys()))
                        if st.form_submit_button("Salvar Conta Analítica"):
                            if n_anal_m.strip() and add_conta_analitica(sint_opcoes_m[s_pai_m], n_anal_m.strip(), hist_anal_opcoes_m[h_anal_sel_m]):
                                st.success("Conta Analítica cadastrada!")
                                st.rerun()
                            else:
                                st.error("Erro: Preencha o nome ou verifique se já existe.")
            with a_alt:
                df_anal_m = get_contas_analiticas()
                if not df_anal_m.empty and not df_sint_disp_m.empty:
                    anal_map_m = {r["caminho_completo"]: r["id"] for _, r in df_anal_m.iterrows()}
                    sel_anal_m = st.selectbox("Selecione para Alterar", list(anal_map_m.keys()), key="alt_anal_m_box")
                    item_am = df_anal_m[df_anal_m["id"] == anal_map_m[sel_anal_m]].iloc[0]
                    sint_opcoes_edit_m = {f"[{r['tipo']}] {r['nome']}": r["id"] for _, r in df_sint_disp_m.iterrows()}
                    with st.form("form_alt_anal_m"):
                        s_keys_m = list(sint_opcoes_edit_m.keys())
                        s_idx_m = list(sint_opcoes_edit_m.values()).index(item_am["sintetica_id"]) if item_am["sintetica_id"] in list(sint_opcoes_edit_m.values()) else 0
                        nova_s_pai_m = st.selectbox("Conta Sintética Superior", s_keys_m, index=s_idx_m)
                        novo_n_anal_m = st.text_input("Nome da Conta Analítica", value=item_am["conta_analitica"])
                        h_keys_m = list(hist_anal_opcoes_m.keys())
                        h_idx_m = list(hist_anal_opcoes_m.values()).index(item_am["historico_padrao_id"]) if item_am["historico_padrao_id"] in list(hist_anal_opcoes_m.values()) else 0
                        novo_h_m = st.selectbox("Histórico Padrão Vinculado", h_keys_m, index=h_idx_m)
                        if st.form_submit_button("Atualizar Conta Analítica"):
                            if novo_n_anal_m.strip() and update_conta_analitica(item_am["id"], sint_opcoes_edit_m[nova_s_pai_m], novo_n_anal_m.strip(), hist_anal_opcoes_m[novo_h_m]):
                                st.success("Conta Analítica atualizada!")
                                st.rerun()
                else:
                    st.info("Nenhuma conta analítica cadastrada.")
            with a_exc:
                df_anal_m = get_contas_analiticas()
                if not df_anal_m.empty:
                    anal_map_m = {r["caminho_completo"]: r["id"] for _, r in df_anal_m.iterrows()}
                    sel_anal_del_m = st.selectbox("Selecione para Excluir", list(anal_map_m.keys()), key="del_anal_m_box")
                    if st.button("Excluir Conta Analítica", type="primary"):
                        delete_conta_analitica(anal_map_m[sel_anal_del_m])
                        st.success("Conta Analítica excluída!")
                        st.rerun()
                else:
                    st.info("Nenhuma conta analítica cadastrada.")
            st.dataframe(get_contas_analiticas()[["id", "tipo", "conta_sintetica", "conta_analitica", "historico_padrao_nome"]], use_container_width=True)

    # 4. CRUD HISTÓRICOS PADRÃO
    with tab_crud_hist:
        st.subheader("Históricos Padrão")
        h_inc, h_alt, h_exc = st.tabs(["➕ Incluir", "✏️ Alterar", "🗑️ Excluir"])
        
        with h_inc:
            with st.form("form_inc_hist_m", clear_on_submit=True):
                col1, col2 = st.columns(2)
                cod_h = col1.text_input("Código (Ex: 101, REC-01, DESP-01)")
                tipo_ap_h = col2.selectbox("Aplica-se a", ["Receita", "Despesa", "Ambos"])
                desc_h = st.text_input("Descrição do Histórico")
                if st.form_submit_button("Salvar Histórico Padrão"):
                    if cod_h.strip() and desc_h.strip() and add_historico(cod_h, desc_h, tipo_ap_h):
                        st.success("Histórico padrão cadastrado!")
                        st.rerun()
                    else:
                        st.error("Erro: Preencha todos os campos ou verifique se o código já existe.")
        with h_alt:
            df_hm = get_historicos()
            if not df_hm.empty:
                h_map_m = {f"{r['codigo']} - {r['descricao']} ({r['tipo_aplicavel']})": r["id"] for _, r in df_hm.iterrows()}
                sel_h_m = st.selectbox("Selecione para Alterar", list(h_map_m.keys()), key="alt_h_m_box")
                item_hm = df_hm[df_hm["id"] == h_map_m[sel_h_m]].iloc[0]
                with st.form("form_alt_hist_m"):
                    col1, col2 = st.columns(2)
                    n_cod_h = col1.text_input("Código", value=item_hm["codigo"])
                    t_idx_h = ["Receita", "Despesa", "Ambos"].index(item_hm["tipo_aplicavel"])
                    n_tipo_h = col2.selectbox("Aplica-se a", ["Receita", "Despesa", "Ambos"], index=t_idx_h)
                    n_desc_h = st.text_input("Descrição", value=item_hm["descricao"])
                    if st.form_submit_button("Atualizar Histórico"):
                        if n_cod_h.strip() and n_desc_h.strip() and update_historico(item_hm["id"], n_cod_h, n_desc_h, n_tipo_h):
                            st.success("Histórico atualizado!")
                            st.rerun()
            else:
                st.info("Nenhum histórico padrão cadastrado.")
        with h_exc:
            df_hm = get_historicos()
            if not df_hm.empty:
                h_map_m = {f"{r['codigo']} - {r['descricao']} ({r['tipo_aplicavel']})": r["id"] for _, r in df_hm.iterrows()}
                del_h_m = st.selectbox("Selecione para Excluir", list(h_map_m.keys()), key="del_h_m_box")
                if st.button("Excluir Histórico Padrão", type="primary"):
                    delete_historico(h_map_m[del_h_m])
                    st.success("Histórico padrão excluído!")
                    st.rerun()
            else:
                st.info("Nenhum histórico padrão cadastrado.")
        st.dataframe(get_historicos(), use_container_width=True)

    # 5. CRUD CLIENTES E FORNECEDORES
    with tab_crud_contatos:
        st.subheader("Clientes e Fornecedores")
        sub_cli_m, sub_forn_m = st.tabs(["👥 Clientes", "🏢 Fornecedores"])
        
        with sub_cli_m:
            cli_inc, cli_alt, cli_exc = st.tabs(["➕ Incluir", "✏️ Alterar", "🗑️ Excluir"])
            with cli_inc:
                with st.form("form_inc_cli_m", clear_on_submit=True):
                    nome_c = st.text_input("Nome do Cliente")
                    if st.form_submit_button("Salvar Cliente"):
                        if nome_c.strip():
                            add_contato(nome_c.strip(), "Cliente")
                            st.success("Cliente cadastrado!")
                            st.rerun()
                        else:
                            st.warning("Preencha o nome do cliente.")
            with cli_alt:
                df_cli_m = get_contatos("Cliente")
                if not df_cli_m.empty:
                    cli_map = dict(zip(df_cli_m["nome"], df_cli_m["id"]))
                    sel_cli_m = st.selectbox("Selecione o Cliente para Alterar", list(cli_map.keys()), key="alt_cli_box_m")
                    with st.form("form_alt_cli_m"):
                        novo_n_cli = st.text_input("Novo Nome", value=sel_cli_m)
                        if st.form_submit_button("Atualizar Cliente"):
                            if novo_n_cli.strip():
                                update_contato(cli_map[sel_cli_m], novo_n_cli.strip())
                                st.success("Cliente atualizado!")
                                st.rerun()
                else:
                    st.info("Nenhum cliente cadastrado.")
            with cli_exc:
                df_cli_m = get_contatos("Cliente")
                if not df_cli_m.empty:
                    cli_map = dict(zip(df_cli_m["nome"], df_cli_m["id"]))
                    del_cli_m = st.selectbox("Selecione o Cliente para Excluir", list(cli_map.keys()), key="del_cli_box_m")
                    st.warning("⚠️ Ao excluir o cliente, os lançamentos e referências a ele serão removidos.")
                    if st.button("Excluir Cliente", type="primary"):
                        delete_contato(cli_map[del_cli_m])
                        st.success("Cliente excluído!")
                        st.rerun()
                else:
                    st.info("Nenhum cliente cadastrado.")
            st.dataframe(get_contatos("Cliente")[["id", "nome"]], use_container_width=True)

        with sub_forn_m:
            forn_inc, forn_alt, forn_exc = st.tabs(["➕ Incluir", "✏️ Alterar", "🗑️ Excluir"])
            with forn_inc:
                with st.form("form_inc_forn_m", clear_on_submit=True):
                    nome_f = st.text_input("Nome do Fornecedor")
                    if st.form_submit_button("Salvar Fornecedor"):
                        if nome_f.strip():
                            add_contato(nome_f.strip(), "Fornecedor")
                            st.success("Fornecedor cadastrado!")
                            st.rerun()
                        else:
                            st.warning("Preencha o nome do fornecedor.")
            with forn_alt:
                df_forn_m = get_contatos("Fornecedor")
                if not df_forn_m.empty:
                    forn_map = dict(zip(df_forn_m["nome"], df_forn_m["id"]))
                    sel_forn_m = st.selectbox("Selecione o Fornecedor para Alterar", list(forn_map.keys()), key="alt_forn_box_m")
                    with st.form("form_alt_forn_m"):
                        novo_n_forn = st.text_input("Novo Nome", value=sel_forn_m)
                        if st.form_submit_button("Atualizar Fornecedor"):
                            if novo_n_forn.strip():
                                update_contato(forn_map[sel_forn_m], novo_n_forn.strip())
                                st.success("Fornecedor atualizado!")
                                st.rerun()
                else:
                    st.info("Nenhum fornecedor cadastrado.")
            with forn_exc:
                df_forn_m = get_contatos("Fornecedor")
                if not df_forn_m.empty:
                    forn_map = dict(zip(df_forn_m["nome"], df_forn_m["id"]))
                    del_forn_m = st.selectbox("Selecione o Fornecedor para Excluir", list(forn_map.keys()), key="del_forn_box_m")
                    st.warning("⚠️ Ao excluir o fornecedor, os lançamentos vinculados serão removidos.")
                    if st.button("Excluir Fornecedor", type="primary"):
                        delete_contato(forn_map[del_forn_m])
                        st.success("Fornecedor excluído!")
                        st.rerun()
                else:
                    st.info("Nenhum fornecedor cadastrado.")
            st.dataframe(get_contatos("Fornecedor")[["id", "nome"]], use_container_width=True)

    # 6. CRUD REGRAS DE CLASSIFICAÇÃO AUTOMÁTICA
    with tab_crud_regras:
        st.subheader("Regras de Classificação Automática")
        r_inc, r_alt, r_exc = st.tabs(["➕ Incluir", "✏️ Alterar", "🗑️ Excluir"])
        
        with r_inc:
            col_rt1, col_rt2 = st.columns(2)
            tipo_regra_m = col_rt1.radio("Tipo da Operação", ["Despesa", "Receita"], horizontal=True, key="regra_inc_tipo_m")
            df_sint_regra_m = get_contas_sinteticas(tipo=tipo_regra_m)
            
            if df_sint_regra_m.empty:
                st.warning(f"Cadastre primeiro uma Categoria (Conta Sintética) de {tipo_regra_m}.")
            else:
                map_sint_regra_m = dict(zip(df_sint_regra_m["nome"], df_sint_regra_m["id"]))
                cat_sel_m = col_rt2.selectbox("Categoria (Conta Sintética)", list(map_sint_regra_m.keys()), key="regra_cat_inc_m")
                sint_id_sel_m = map_sint_regra_m[cat_sel_m]
                
                df_anal_regra_m = get_contas_analiticas(tipo=tipo_regra_m)
                df_anal_filt_m = df_anal_regra_m[df_anal_regra_m["sintetica_id"] == sint_id_sel_m]
                
                if df_anal_filt_m.empty:
                    st.warning(f"Não há Subcategorias na categoria '{cat_sel_m}'.")
                else:
                    map_anal_regra_m = dict(zip(df_anal_filt_m["conta_analitica"], df_anal_filt_m["id"]))
                    map_hist_anal_regra_m = dict(zip(df_anal_filt_m["id"], df_anal_filt_m["historico_padrao_id"]))
                    
                    col_sub1, col_sub2 = st.columns(2)
                    subcat_sel_m = col_sub1.selectbox("Subcategoria (Conta Analítica)", list(map_anal_regra_m.keys()), key="regra_subcat_inc_m")
                    anal_id_sel_m = map_anal_regra_m[subcat_sel_m]
                    
                    df_hist_regra_m = get_historicos(tipo=tipo_regra_m)
                    map_hist_regra_m = {"(Padrão da Subcategoria / Automático)": None}
                    if not df_hist_regra_m.empty:
                        for _, rh in df_hist_regra_m.iterrows():
                            map_hist_regra_m[f"{rh['codigo']} - {rh['descricao']}"] = rh["id"]
                            
                    hist_sel_regra_m = col_sub2.selectbox("Histórico Padrão (Opcional)", list(map_hist_regra_m.keys()), key="regra_hist_inc_m")
                    
                    with st.form("form_inc_regra_m", clear_on_submit=True):
                        padrao_txt_m = st.text_input("Padrão de Texto / Palavra-chave (Ex: copasa, cemig, uber, oab)")
                        if st.form_submit_button("Salvar Regra de Classificação", type="primary"):
                            if padrao_txt_m.strip():
                                h_final_id = map_hist_regra_m[hist_sel_regra_m]
                                if h_final_id is None:
                                    h_final_id = map_hist_anal_regra_m.get(anal_id_sel_m)
                                if add_regra_classificacao(padrao_txt_m.strip(), tipo_regra_m, sint_id_sel_m, anal_id_sel_m, h_final_id):
                                    st.success("Regra de classificação cadastrada!")
                                    st.rerun()
                                else:
                                    st.error("Erro: Já existe uma regra com este padrão.")
                            else:
                                st.warning("Informe o padrão de texto.")

        with r_alt:
            df_regras_m = get_regras_classificacao()
            if not df_regras_m.empty:
                map_regras_edit_m = {f"[{r['tipo']}] '{r['padrao_texto']}' ➔ {r['categoria']} / {r['subcategoria']}": r["id"] for _, r in df_regras_m.iterrows()}
                regra_sel_m = st.selectbox("Selecione a Regra para Alterar", list(map_regras_edit_m.keys()), key="sel_regra_alt_m")
                item_regra_m = df_regras_m[df_regras_m["id"] == map_regras_edit_m[regra_sel_m]].iloc[0]
                
                tipo_regra_alt_m = st.radio("Tipo", ["Despesa", "Receita"], index=0 if item_regra_m["tipo"] == "Despesa" else 1, horizontal=True, key="regra_alt_tipo_m")
                df_sint_alt_m = get_contas_sinteticas(tipo=tipo_regra_alt_m)
                
                if not df_sint_alt_m.empty:
                    map_sint_alt_m = dict(zip(df_sint_alt_m["nome"], df_sint_alt_m["id"]))
                    s_keys_alt = list(map_sint_alt_m.keys())
                    s_idx_alt = list(map_sint_alt_m.values()).index(item_regra_m["sintetica_id"]) if item_regra_m["sintetica_id"] in list(map_sint_alt_m.values()) else 0
                    cat_sel_alt_m = st.selectbox("Categoria (Conta Sintética)", s_keys_alt, index=s_idx_alt, key="regra_cat_alt_m")
                    sint_id_alt_m = map_sint_alt_m[cat_sel_alt_m]
                    
                    df_anal_alt_m = get_contas_analiticas(tipo=tipo_regra_alt_m)
                    df_anal_filt_alt_m = df_anal_alt_m[df_anal_alt_m["sintetica_id"] == sint_id_alt_m]
                    
                    if not df_anal_filt_alt_m.empty:
                        map_anal_alt_m = dict(zip(df_anal_filt_alt_m["conta_analitica"], df_anal_filt_alt_m["id"]))
                        a_keys_alt = list(map_anal_alt_m.keys())
                        a_idx_alt = list(map_anal_alt_m.values()).index(item_regra_m["analitica_id"]) if item_regra_m["analitica_id"] in list(map_anal_alt_m.values()) else 0
                        subcat_sel_alt_m = st.selectbox("Subcategoria (Conta Analítica)", a_keys_alt, index=a_idx_alt, key="regra_subcat_alt_m")
                        anal_id_alt_m = map_anal_alt_m[subcat_sel_alt_m]
                        
                        df_hist_alt_m = get_historicos(tipo=tipo_regra_alt_m)
                        map_hist_alt_m = {"(Padrão da Subcategoria / Automático)": None}
                        if not df_hist_alt_m.empty:
                            for _, rh in df_hist_alt_m.iterrows():
                                map_hist_alt_m[f"{rh['codigo']} - {rh['descricao']}"] = rh["id"]
                                
                        h_keys_alt = list(map_hist_alt_m.keys())
                        h_idx_alt = list(map_hist_alt_m.values()).index(item_regra_m["historico_id"]) if item_regra_m["historico_id"] in list(map_hist_alt_m.values()) else 0
                        hist_sel_alt_m = st.selectbox("Histórico Padrão", h_keys_alt, index=h_idx_alt, key="regra_hist_alt_m")
                        
                        with st.form("form_alt_regra_exec_m"):
                            novo_padrao_txt_m = st.text_input("Padrão de Texto", value=item_regra_m["padrao_texto"])
                            if st.form_submit_button("Atualizar Regra"):
                                if novo_padrao_txt_m.strip():
                                    if update_regra_classificacao(item_regra_m["id"], novo_padrao_txt_m.strip(), tipo_regra_alt_m, sint_id_alt_m, anal_id_alt_m, map_hist_alt_m[hist_sel_alt_m]):
                                        st.success("Regra atualizada com sucesso!")
                                        st.rerun()
                                    else:
                                        st.error("Erro ao atualizar regra.")
            else:
                st.info("Nenhuma regra de classificação cadastrada.")

        with r_exc:
            df_regras_m = get_regras_classificacao()
            if not df_regras_m.empty:
                map_regras_del_m = {f"[{r['tipo']}] '{r['padrao_texto']}' ➔ {r['categoria']} / {r['subcategoria']}": r["id"] for _, r in df_regras_m.iterrows()}
                sel_regra_del_m = st.selectbox("Selecione para Excluir", list(map_regras_del_m.keys()), key="sel_regra_del_m")
                if st.button("Excluir Regra", type="primary"):
                    delete_regra_classificacao(map_regras_del_m[sel_regra_del_m])
                    st.success("Regra excluída com sucesso!")
                    st.rerun()
            else:
                st.info("Nenhuma regra cadastrada.")

        st.dataframe(get_regras_classificacao()[["id", "padrao_texto", "tipo", "categoria", "subcategoria", "historico_padrao"]], use_container_width=True)

# ====================================================
# SISTEMA 5: USUÁRIOS
# ====================================================
elif sistema_ativo == "👥 Usuários":
    st.title("👥 Gestão de Usuários")
    st.markdown("Cadastre e gerencie os usuários autorizados do escritório e senhas de acesso.")
    
    u_tab_listar, u_tab_novo, u_tab_editar, u_tab_senha = st.tabs([
        "📋 Usuários Cadastrados", "➕ Novo Usuário", "✏️ Alterar / Excluir", "🔑 Minha Senha"
    ])
    
    with u_tab_listar:
        df_usuarios = get_usuarios()
        st.dataframe(df_usuarios.rename(columns={
            "id": "ID", "nome": "Nome", "email": "E-mail", "perfil": "Perfil", "ativo": "Ativo (1=Sim, 0=Não)"
        }), use_container_width=True)

    with u_tab_novo:
        with st.form("form_novo_usuario", clear_on_submit=True):
            col_u1, col_u2 = st.columns(2)
            u_nome = col_u1.text_input("Nome Completo")
            u_email = col_u2.text_input("E-mail Profissional")
            u_senha = col_u1.text_input("Senha Inicial de Acesso", type="password")
            u_perfil = col_u2.selectbox("Perfil de Acesso", ["Administrador", "Advogado", "Assistente"])
            
            if st.form_submit_button("Cadastrar Usuário", type="primary"):
                if u_nome.strip() and u_email.strip() and u_senha.strip():
                    if add_usuario(u_nome.strip(), u_email.strip().lower(), u_senha.strip(), u_perfil):
                        st.success("Usuário cadastrado com sucesso!")
                        st.rerun()
                    else:
                        st.error("Erro: Já existe um usuário cadastrado com este e-mail.")
                else:
                    st.warning("Preencha nome, e-mail e senha.")

    with u_tab_editar:
        df_usuarios = get_usuarios()
        if not df_usuarios.empty:
            u_dict = {f"{r['nome']} ({r['email']})": r["id"] for _, r in df_usuarios.iterrows()}
            u_sel = st.selectbox("Selecione o Usuário para Alterar", list(u_dict.keys()))
            u_id = u_dict[u_sel]
            item_u = df_usuarios[df_usuarios["id"] == u_id].iloc[0]
            
            with st.form("form_edit_usuario"):
                col_ue1, col_ue2 = st.columns(2)
                nome_ue = col_ue1.text_input("Nome Completo", value=item_u["nome"])
                email_ue = col_ue2.text_input("E-mail", value=item_u["email"])
                
                perfis = ["Administrador", "Advogado", "Assistente"]
                p_idx = perfis.index(item_u["perfil"]) if item_u["perfil"] in perfis else 1
                perfil_ue = col_ue1.selectbox("Perfil", perfis, index=p_idx)
                
                nova_senha_admin = col_ue2.text_input("Redefinir Senha (opcional)", type="password", placeholder="Deixe em branco para não alterar")
                ativo_ue = col_ue1.checkbox("Usuário Ativo", value=bool(item_u["ativo"]))
                
                if st.form_submit_button("Salvar Alterações"):
                    if update_usuario(u_id, nome_ue.strip(), email_ue.strip().lower(), perfil_ue, 1 if ativo_ue else 0, nova_senha_admin):
                        st.success("Dados do usuário atualizados com sucesso!")
                        st.rerun()
                    else:
                        st.error("Erro ao atualizar usuário.")
                        
            if st.button("🗑️ Excluir Usuário", type="secondary"):
                if u_id == operador_atual_id:
                    st.error("Você não pode excluir o seu próprio usuário logado.")
                else:
                    delete_usuario(u_id)
                    st.success("Usuário excluído com sucesso!")
                    st.rerun()

    with u_tab_senha:
        st.subheader("Alterar Minha Senha de Acesso")
        with st.form("form_minha_senha"):
            s_atual = st.text_input("Senha Atual", type="password")
            s_nova = st.text_input("Nova Senha", type="password")
            s_confirma = st.text_input("Confirmar Nova Senha", type="password")
            
            if st.form_submit_button("Atualizar Minha Senha", type="primary"):
                user_check = autenticar_usuario(usuario_logado["email"], s_atual)
                if not user_check:
                    st.error("Senha atual incorreta.")
                elif len(s_nova.strip()) < 4:
                    st.warning("A nova senha deve ter no mínimo 4 caracteres.")
                elif s_nova.strip() != s_confirma.strip():
                    st.error("A nova senha e a confirmação não coincidem.")
                else:
                    alterar_senha_usuario(operador_atual_id, s_nova.strip())
                    st.success("Sua senha foi alterada com sucesso!")
