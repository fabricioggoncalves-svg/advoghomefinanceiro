import streamlit as st
import pandas as pd
import sqlite3
import io
import calendar
import hashlib
from datetime import date, datetime, timedelta, time

# ----------------------------------------------------
# CONFIGURAÇÃO GERAL & SEGURANÇA
# ----------------------------------------------------
st.set_page_config(page_title="Fabíola Guimarães Advocacia", layout="wide", page_icon="⚖️")
DB_NAME = "financeiro.db"
SOCIOS = ["Fabrício", "Fabíola"]

def hash_senha(senha: str) -> str:
    return hashlib.sha256(str(senha).strip().encode("utf-8")).hexdigest()

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
    intervalo = max(1, int(intervalo or 1))
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

def to_excel_bytes(df, sheet_name="Relatorio"):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()

# ----------------------------------------------------
# BANCO DE DADOS (SQLite)
# ----------------------------------------------------
def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
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
    
    senha_padrao_hash = hash_senha("111111")
    usuarios_padrao = [
        ("Fabrício Gonçalves", "fabricioggoncalves@gmail.com", senha_padrao_hash, "Administrador"),
        ("Dra. Fabíola Guimarães", "fabiolaguimagoncalves@gmail.com", senha_padrao_hash, "Administrador")
    ]
    for nome, email, shash, perfil in usuarios_padrao:
        c.execute("SELECT id, senha_hash FROM usuarios WHERE LOWER(TRIM(email)) = LOWER(TRIM(?))", (email,))
        row = c.fetchone()
        if not row:
            c.execute("INSERT INTO usuarios (nome, email, senha_hash, perfil, ativo) VALUES (?, ?, ?, ?, 1)",
                      (nome, email.strip().lower(), shash, perfil))
        elif not row[1]:
            c.execute("UPDATE usuarios SET senha_hash = ?, ativo = 1 WHERE id = ?", (shash, row[0]))

    c.execute("CREATE TABLE IF NOT EXISTS contatos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, tipo TEXT CHECK(tipo IN ('Cliente', 'Fornecedor')) NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS historicos_padrao (id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT UNIQUE NOT NULL, descricao TEXT NOT NULL, tipo_aplicavel TEXT CHECK(tipo_aplicavel IN ('Receita', 'Despesa', 'Ambos')) NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS contas_sinteticas (id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT CHECK(tipo IN ('Receita', 'Despesa')) NOT NULL, nome TEXT NOT NULL, UNIQUE(tipo, nome))")
    c.execute("""
        CREATE TABLE IF NOT EXISTS contas_analiticas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, sintetica_id INTEGER NOT NULL, nome TEXT NOT NULL, historico_padrao_id INTEGER,
            UNIQUE(sintetica_id, nome), FOREIGN KEY (sintetica_id) REFERENCES contas_sinteticas(id) ON DELETE CASCADE, FOREIGN KEY (historico_padrao_id) REFERENCES historicos_padrao(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS contas_recorrentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, contato_id INTEGER, conta_analitica_id INTEGER NOT NULL,
            historico_id INTEGER, valor REAL DEFAULT 0.0, dia_vencimento INTEGER NOT NULL, complemento_padrao TEXT, pago_por_padrao TEXT,
            FOREIGN KEY (contato_id) REFERENCES contatos(id), FOREIGN KEY (conta_analitica_id) REFERENCES contas_analiticas(id), FOREIGN KEY (historico_id) REFERENCES historicos_padrao(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS regras_classificacao (
            id INTEGER PRIMARY KEY AUTOINCREMENT, padrao_texto TEXT NOT NULL UNIQUE, tipo TEXT CHECK(tipo IN ('Receita', 'Despesa')) NOT NULL,
            sintetica_id INTEGER NOT NULL, analitica_id INTEGER NOT NULL, historico_id INTEGER,
            FOREIGN KEY (sintetica_id) REFERENCES contas_sinteticas(id), FOREIGN KEY (analitica_id) REFERENCES contas_analiticas(id), FOREIGN KEY (historico_id) REFERENCES historicos_padrao(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS lancamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT CHECK(tipo IN ('Receita', 'Despesa')) NOT NULL, data_vencimento TEXT NOT NULL,
            data_pagamento TEXT, valor REAL NOT NULL, contato_id INTEGER, historico_id INTEGER, conta_analitica_id INTEGER, complemento TEXT,
            status TEXT DEFAULT 'Pendente', pago_por TEXT, recorrente_id INTEGER, mes_referencia TEXT,
            FOREIGN KEY (contato_id) REFERENCES contatos(id), FOREIGN KEY (historico_id) REFERENCES historicos_padrao(id),
            FOREIGN KEY (conta_analitica_id) REFERENCES contas_analiticas(id), FOREIGN KEY (recorrente_id) REFERENCES contas_recorrentes(id)
        )
    """)
    c.execute("CREATE TABLE IF NOT EXISTS tipos_tarefas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL UNIQUE)")
    c.execute("CREATE TABLE IF NOT EXISTS grupos_tarefas_n1 (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL UNIQUE)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS grupos_tarefas_n2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT, grupo_n1_id INTEGER NOT NULL, nome TEXT NOT NULL,
            UNIQUE(grupo_n1_id, nome), FOREIGN KEY (grupo_n1_id) REFERENCES grupos_tarefas_n1(id) ON DELETE CASCADE
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tarefas_recorrentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, descricao TEXT, frequencia TEXT NOT NULL, intervalo INTEGER DEFAULT 1,
            data_inicio TEXT NOT NULL, proxima_execucao TEXT NOT NULL, prioridade TEXT DEFAULT 'Média', responsavel_id INTEGER, cliente_id INTEGER,
            processo_ref TEXT, tipo_tarefa_id INTEGER, subgrupo_id INTEGER, criador_id INTEGER, visibilidade TEXT DEFAULT 'Compartilhada', ativo INTEGER DEFAULT 1,
            FOREIGN KEY (responsavel_id) REFERENCES usuarios(id), FOREIGN KEY (cliente_id) REFERENCES contatos(id),
            FOREIGN KEY (tipo_tarefa_id) REFERENCES tipos_tarefas(id), FOREIGN KEY (subgrupo_id) REFERENCES grupos_tarefas_n2(id), FOREIGN KEY (criador_id) REFERENCES usuarios(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tarefas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, descricao TEXT, data_limite TEXT, prioridade TEXT DEFAULT 'Média',
            status TEXT DEFAULT 'Não Iniciada', responsavel_id INTEGER, cliente_id INTEGER, processo_ref TEXT, tipo_tarefa_id INTEGER,
            subgrupo_id INTEGER, criador_id INTEGER, visibilidade TEXT DEFAULT 'Compartilhada', recorrente_origem_id INTEGER, criado_em TEXT,
            FOREIGN KEY (responsavel_id) REFERENCES usuarios(id), FOREIGN KEY (cliente_id) REFERENCES contatos(id),
            FOREIGN KEY (tipo_tarefa_id) REFERENCES tipos_tarefas(id), FOREIGN KEY (subgrupo_id) REFERENCES grupos_tarefas_n2(id),
            FOREIGN KEY (criador_id) REFERENCES usuarios(id), FOREIGN KEY (recorrente_origem_id) REFERENCES tarefas_recorrentes(id) ON DELETE SET NULL
        )
    """)
    c.execute("CREATE TABLE IF NOT EXISTS tarefas_compartilhadas (tarefa_id INTEGER, usuario_id INTEGER, PRIMARY KEY (tarefa_id, usuario_id))")
    c.execute("""
        CREATE TABLE IF NOT EXISTS compromissos_recorrentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, descricao TEXT, frequencia TEXT NOT NULL, intervalo INTEGER DEFAULT 1,
            data_inicio TEXT NOT NULL, hora_inicio TEXT, duracao_minutos INTEGER DEFAULT 60, dia_inteiro INTEGER DEFAULT 0, local_link TEXT,
            cliente_id INTEGER, processo_ref TEXT, organizador_id INTEGER NOT NULL, visibilidade TEXT DEFAULT 'Compartilhada', ativo INTEGER DEFAULT 1,
            FOREIGN KEY (cliente_id) REFERENCES contatos(id), FOREIGN KEY (organizador_id) REFERENCES usuarios(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS compromissos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, descricao TEXT, data_inicio TEXT NOT NULL, hora_inicio TEXT,
            data_fim TEXT NOT NULL, hora_fim TEXT, dia_inteiro INTEGER DEFAULT 0, local_link TEXT, cliente_id INTEGER, processo_ref TEXT,
            organizador_id INTEGER NOT NULL, visibilidade TEXT DEFAULT 'Compartilhada', recorrente_origem_id INTEGER, criado_em TEXT,
            FOREIGN KEY (cliente_id) REFERENCES contatos(id), FOREIGN KEY (organizador_id) REFERENCES usuarios(id),
            FOREIGN KEY (recorrente_origem_id) REFERENCES compromissos_recorrentes(id) ON DELETE SET NULL
        )
    """)
    c.execute("CREATE TABLE IF NOT EXISTS compromissos_participantes (compromisso_id INTEGER, usuario_id INTEGER, PRIMARY KEY (compromisso_id, usuario_id))")

    conn.commit()
    conn.close()

# --- Funções: Usuários ---
def autenticar_usuario(email, senha):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, nome, email, perfil, ativo FROM usuarios WHERE LOWER(TRIM(email)) = ? AND senha_hash = ?", (str(email).strip().lower(), hash_senha(senha)))
    user = c.fetchone()
    conn.close()
    if user and user[4] == 1:
        return {"id": user[0], "nome": user[1], "email": user[2], "perfil": user[3]}
    return None

def resetar_senha_padrao_admin(email):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE usuarios SET senha_hash = ?, ativo = 1 WHERE LOWER(TRIM(email)) = LOWER(TRIM(?))", (hash_senha("111111"), email))
    conn.commit()
    afetados = c.rowcount
    conn.close()
    return afetados > 0

def alterar_senha_usuario(usuario_id, nova_senha):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (hash_senha(nova_senha), usuario_id))
    conn.commit()
    conn.close()
    return True

def get_usuarios(apenas_ativos=False):
    conn = get_connection()
    q = "SELECT id, nome, email, perfil, ativo FROM usuarios" + (" WHERE ativo = 1" if apenas_ativos else "") + " ORDER BY nome ASC"
    df = pd.read_sql_query(q, conn)
    conn.close()
    return df

def add_usuario(nome, email, senha, perfil):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO usuarios (nome, email, senha_hash, perfil, ativo) VALUES (?, ?, ?, ?, 1)", (nome.strip(), email.strip().lower(), hash_senha(senha), perfil))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def update_usuario(usuario_id, nome, email, perfil, ativo, nova_senha=None):
    conn = get_connection()
    c = conn.cursor()
    try:
        if nova_senha and str(nova_senha).strip():
            c.execute("UPDATE usuarios SET nome = ?, email = ?, perfil = ?, ativo = ?, senha_hash = ? WHERE id = ?", (nome.strip(), email.strip().lower(), perfil, ativo, hash_senha(nova_senha), usuario_id))
        else:
            c.execute("UPDATE usuarios SET nome = ?, email = ?, perfil = ?, ativo = ? WHERE id = ?", (nome.strip(), email.strip().lower(), perfil, ativo, usuario_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_usuario(usuario_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE tarefas SET responsavel_id = NULL WHERE responsavel_id = ?", (usuario_id,))
    c.execute("DELETE FROM tarefas_compartilhadas WHERE usuario_id = ?", (usuario_id,))
    c.execute("DELETE FROM compromissos_participantes WHERE usuario_id = ?", (usuario_id,))
    c.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    conn.commit()
    conn.close()

# --- Funções: Tabelas de Apoio (CRUDs) ---
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
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def update_tipo_tarefa(tipo_id, nome):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("UPDATE tipos_tarefas SET nome = ? WHERE id = ?", (nome.strip(), tipo_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_tipo_tarefa(tipo_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE tarefas SET tipo_tarefa_id = NULL WHERE tipo_tarefa_id = ?", (tipo_id,))
    c.execute("DELETE FROM tipos_tarefas WHERE id = ?", (tipo_id,))
    conn.commit()
    conn.close()

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
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def update_grupo_tarefas_n1(n1_id, nome):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("UPDATE grupos_tarefas_n1 SET nome = ? WHERE id = ?", (nome.strip(), n1_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

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
    df = pd.read_sql_query("""
        SELECT n2.id, n1.id AS grupo_n1_id, n1.nome AS grupo_n1, n2.nome AS subgrupo_n2, n1.nome || ' ➔ ' || n2.nome AS caminho_completo
        FROM grupos_tarefas_n2 n2 JOIN grupos_tarefas_n1 n1 ON n2.grupo_n1_id = n1.id ORDER BY n1.nome, n2.nome ASC
    """, conn)
    conn.close()
    return df

def add_grupo_tarefas_n2(grupo_n1_id, nome):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO grupos_tarefas_n2 (grupo_n1_id, nome) VALUES (?, ?)", (grupo_n1_id, nome.strip()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def update_grupo_tarefas_n2(n2_id, grupo_n1_id, nome):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("UPDATE grupos_tarefas_n2 SET grupo_n1_id = ?, nome = ? WHERE id = ?", (grupo_n1_id, nome.strip(), n2_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_grupo_tarefas_n2(n2_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE tarefas SET subgrupo_id = NULL WHERE subgrupo_id = ?", (n2_id,))
    c.execute("DELETE FROM grupos_tarefas_n2 WHERE id = ?", (n2_id,))
    conn.commit()
    conn.close()

def get_contas_sinteticas(tipo=None):
    conn = get_connection()
    q = "SELECT id, tipo, nome FROM contas_sinteticas" + (f" WHERE tipo = '{tipo}'" if tipo else "") + " ORDER BY tipo, nome ASC"
    df = pd.read_sql_query(q, conn)
    conn.close()
    return df

def add_conta_sintetica(tipo, nome):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO contas_sinteticas (tipo, nome) VALUES (?, ?)", (tipo, nome.strip()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def update_conta_sintetica(sintetica_id, tipo, nome):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("UPDATE contas_sinteticas SET tipo = ?, nome = ? WHERE id = ?", (tipo, nome.strip(), sintetica_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

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
    q = """
        SELECT a.id, s.tipo, s.id AS sintetica_id, s.nome AS conta_sintetica, a.nome AS conta_analitica, a.historico_padrao_id,
               h.codigo || ' - ' || h.descricao AS historico_padrao_nome, s.tipo || ' ➔ ' || s.nome || ' ➔ ' || a.nome AS caminho_completo
        FROM contas_analiticas a JOIN contas_sinteticas s ON a.sintetica_id = s.id LEFT JOIN historicos_padrao h ON a.historico_padrao_id = h.id
    """
    if tipo:
        q += f" WHERE s.tipo = '{tipo}'"
    q += " ORDER BY s.tipo, s.nome, a.nome ASC"
    df = pd.read_sql_query(q, conn)
    conn.close()
    return df

def add_conta_analitica(sintetica_id, nome, historico_padrao_id=None):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO contas_analiticas (sintetica_id, nome, historico_padrao_id) VALUES (?, ?, ?)", (sintetica_id, nome.strip(), historico_padrao_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def update_conta_analitica(analitica_id, sintetica_id, nome, historico_padrao_id=None):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("UPDATE contas_analiticas SET sintetica_id = ?, nome = ?, historico_padrao_id = ? WHERE id = ?", (sintetica_id, nome.strip(), historico_padrao_id, analitica_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_conta_analitica(analitica_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE lancamentos SET conta_analitica_id = NULL WHERE conta_analitica_id = ?", (analitica_id,))
    c.execute("DELETE FROM contas_recorrentes WHERE conta_analitica_id = ?", (analitica_id,))
    c.execute("DELETE FROM regras_classificacao WHERE analitica_id = ?", (analitica_id,))
    c.execute("DELETE FROM contas_analiticas WHERE id = ?", (analitica_id,))
    conn.commit()
    conn.close()

def get_contatos(tipo=None):
    conn = get_connection()
    q = "SELECT id, nome, tipo FROM contatos" + (f" WHERE tipo = '{tipo}'" if tipo else "") + " ORDER BY nome ASC"
    df = pd.read_sql_query(q, conn)
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
    c.execute("UPDATE compromissos_recorrentes SET cliente_id = NULL WHERE cliente_id = ?", (contato_id,))
    c.execute("DELETE FROM contatos WHERE id = ?", (contato_id,))
    conn.commit()
    conn.close()

def get_historicos(tipo=None):
    conn = get_connection()
    q = "SELECT id, codigo, descricao, tipo_aplicavel FROM historicos_padrao"
    if tipo:
        q += f" WHERE tipo_aplicavel = '{tipo}' OR tipo_aplicavel = 'Ambos'"
    q += " ORDER BY codigo ASC"
    df = pd.read_sql_query(q, conn)
    conn.close()
    return df

def add_historico(codigo, descricao, tipo_aplicavel):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO historicos_padrao (codigo, descricao, tipo_aplicavel) VALUES (?, ?, ?)", (codigo.strip().upper(), descricao.strip(), tipo_aplicavel))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def update_historico(hist_id, codigo, descricao, tipo_aplicavel):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("UPDATE historicos_padrao SET codigo = ?, descricao = ?, tipo_aplicavel = ? WHERE id = ?", (codigo.strip().upper(), descricao.strip(), tipo_aplicavel, hist_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

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

def get_regras_classificacao():
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT r.id, r.padrao_texto, r.tipo, r.sintetica_id, s.nome AS categoria, r.analitica_id, a.nome AS subcategoria,
               r.historico_id, h.codigo || ' - ' || h.descricao AS historico_padrao
        FROM regras_classificacao r JOIN contas_sinteticas s ON r.sintetica_id = s.id JOIN contas_analiticas a ON r.analitica_id = a.id
        LEFT JOIN historicos_padrao h ON r.historico_id = h.id ORDER BY r.tipo, s.nome, a.nome ASC
    """, conn)
    conn.close()
    return df

def add_regra_classificacao(padrao_texto, tipo, sintetica_id, analitica_id, historico_id=None):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO regras_classificacao (padrao_texto, tipo, sintetica_id, analitica_id, historico_id) VALUES (?, ?, ?, ?, ?)", (padrao_texto.strip().lower(), tipo, sintetica_id, analitica_id, historico_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_regra_classificacao(regra_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM regras_classificacao WHERE id = ?", (regra_id,))
    conn.commit()
    conn.close()

# --- Funções: Financeiro (Lançamentos e Recorrência) ---
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
        UPDATE lancamentos SET tipo = ?, data_vencimento = ?, data_pagamento = ?, valor = ?, contato_id = ?, historico_id = ?, conta_analitica_id = ?, complemento = ?, status = ?, pago_por = ? WHERE id = ?
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
        c.execute("UPDATE lancamentos SET status = 'Concluído', data_pagamento = ?" + (", pago_por = ?" if pago_por else "") + " WHERE id = ?", ((str(data_baixa), pago_por, l_id) if pago_por else (str(data_baixa), l_id)))
    conn.commit()
    conn.close()

def get_lancamentos_df(tipo_filtro=None):
    conn = get_connection()
    q = """
        SELECT l.id, l.data_vencimento, l.data_pagamento, l.tipo, c.nome AS contato, c.id AS contato_id, s.nome AS conta_sintetica,
               a.nome AS conta_analitica, a.id AS conta_analitica_id, h.codigo || ' - ' || h.descricao AS historico_padrao, h.id AS historico_id,
               l.complemento, l.valor, l.status, l.pago_por, l.mes_referencia, l.recorrente_id
        FROM lancamentos l LEFT JOIN contatos c ON l.contato_id = c.id LEFT JOIN historicos_padrao h ON l.historico_id = h.id
        LEFT JOIN contas_analiticas a ON l.conta_analitica_id = a.id LEFT JOIN contas_sinteticas s ON a.sintetica_id = s.id
    """
    if tipo_filtro:
        q += f" WHERE l.tipo = '{tipo_filtro}'"
    q += " ORDER BY l.data_vencimento DESC, l.id DESC"
    df = pd.read_sql_query(q, conn)
    conn.close()
    return df

def get_contas_recorrentes():
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT r.id, r.titulo, c.nome AS fornecedor, r.contato_id, s.nome AS conta_sintetica, a.nome AS conta_analitica, r.conta_analitica_id,
               h.codigo || ' - ' || h.descricao AS historico_padrao, r.historico_id, r.valor, r.dia_vencimento, r.complemento_padrao, r.pago_por_padrao
        FROM contas_recorrentes r LEFT JOIN contatos c ON r.contato_id = c.id LEFT JOIN contas_analiticas a ON r.conta_analitica_id = a.id
        LEFT JOIN contas_sinteticas s ON a.sintetica_id = s.id LEFT JOIN historicos_padrao h ON r.historico_id = h.id ORDER BY r.dia_vencimento ASC
    """, conn)
    conn.close()
    return df

def gerar_contas_do_mes(ano, mes):
    conn = get_connection()
    mes_ref = f"{ano:04d}-{mes:02d}"
    df_rec = pd.read_sql_query("SELECT * FROM contas_recorrentes", conn)
    if df_rec.empty:
        conn.close()
        return 0, 0, "Nenhuma conta recorrente configurada."
    df_ex = pd.read_sql_query("SELECT recorrente_id FROM lancamentos WHERE mes_referencia = ?", conn, params=(mes_ref,))
    ex_ids = set(df_ex["recorrente_id"].dropna().astype(int).tolist())
    
    gerados = 0
    ignorados = 0
    c = conn.cursor()
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    for _, item in df_rec.iterrows():
        rid = int(item["id"])
        if rid in ex_ids:
            ignorados += 1
            continue
        dia = min(int(item["dia_vencimento"]), ultimo_dia)
        c.execute("""
            INSERT INTO lancamentos (tipo, data_vencimento, valor, contato_id, historico_id, conta_analitica_id, complemento, status, pago_por, recorrente_id, mes_referencia)
            VALUES ('Despesa', ?, ?, ?, ?, ?, ?, 'Pendente', ?, ?, ?)
        """, (f"{ano:04d}-{mes:02d}-{dia:02d}", float(item["valor"] or 0.0), item["contato_id"] if pd.notna(item["contato_id"]) else None,
              item["historico_id"] if pd.notna(item["historico_id"]) else None, int(item["conta_analitica_id"]), item["complemento_padrao"],
              item["pago_por_padrao"] if pd.notna(item["pago_por_padrao"]) else None, rid, mes_ref))
        gerados += 1
    conn.commit()
    conn.close()
    return gerados, ignorados, "Processamento concluído."

# --- Funções: Tarefas & Recorrência ---
def get_tarefas_df(usuario_logado_id=None):
    conn = get_connection()
    q = """
        SELECT DISTINCT t.id, t.titulo, tt.nome AS tipo_tarefa, t.tipo_tarefa_id, gn1.nome AS grupo_tarefa, gn2.nome AS subgrupo_tarefa,
               t.subgrupo_id, t.data_limite, t.prioridade, t.status, u.nome AS responsavel, t.responsavel_id, c.nome AS cliente,
               t.cliente_id, t.processo_ref, t.descricao, t.visibilidade, t.recorrente_origem_id, criador.nome AS criador, t.criador_id
        FROM tarefas t LEFT JOIN tipos_tarefas tt ON t.tipo_tarefa_id = tt.id LEFT JOIN grupos_tarefas_n2 gn2 ON t.subgrupo_id = gn2.id
        LEFT JOIN grupos_tarefas_n1 gn1 ON gn2.grupo_n1_id = gn1.id LEFT JOIN usuarios u ON t.responsavel_id = u.id
        LEFT JOIN usuarios criador ON t.criador_id = criador.id LEFT JOIN contatos c ON t.cliente_id = c.id
        LEFT JOIN tarefas_compartilhadas tc ON t.id = tc.tarefa_id
    """
    params = ()
    if usuario_logado_id:
        q += " WHERE (t.visibilidade = 'Compartilhada' OR t.criador_id = ? OR t.responsavel_id = ? OR tc.usuario_id = ?)"
        params = (usuario_logado_id, usuario_logado_id, usuario_logado_id)
    q += " ORDER BY t.data_limite ASC"
    df = pd.read_sql_query(q, conn, params=params)
    conn.close()
    return df

def add_tarefa(titulo, descricao, data_limite, prioridade, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade, usuarios_compartilhados=None, recorrente_origem_id=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO tarefas (titulo, descricao, data_limite, prioridade, status, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade, recorrente_origem_id, criado_em)
        VALUES (?, ?, ?, ?, 'Não Iniciada', ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (titulo, descricao, str(data_limite), prioridade, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade, recorrente_origem_id, str(date.today())))
    tid = c.lastrowid
    if visibilidade == "Compartilhada" and usuarios_compartilhados:
        for uid in usuarios_compartilhados:
            c.execute("INSERT OR IGNORE INTO tarefas_compartilhadas (tarefa_id, usuario_id) VALUES (?, ?)", (tid, uid))
    conn.commit()
    conn.close()
    return tid

def update_tarefa(tarefa_id, titulo, descricao, data_limite, prioridade, status, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, visibilidade, usuarios_compartilhados=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE tarefas SET titulo = ?, descricao = ?, data_limite = ?, prioridade = ?, status = ?, responsavel_id = ?, cliente_id = ?, processo_ref = ?, tipo_tarefa_id = ?, subgrupo_id = ?, visibilidade = ? WHERE id = ?
    """, (titulo, descricao, str(data_limite), prioridade, status, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, visibilidade, tarefa_id))
    c.execute("DELETE FROM tarefas_compartilhadas WHERE tarefa_id = ?", (tarefa_id,))
    if visibilidade == "Compartilhada" and usuarios_compartilhados:
        for uid in usuarios_compartilhados:
            c.execute("INSERT OR IGNORE INTO tarefas_compartilhadas (tarefa_id, usuario_id) VALUES (?, ?)", (tarefa_id, uid))
    conn.commit()
    conn.close()
    if "Concluíd" in status:
        processar_conclusao_recorrente(tarefa_id)

def delete_tarefa(tarefa_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM tarefas_compartilhadas WHERE tarefa_id = ?", (tarefa_id,))
    c.execute("DELETE FROM tarefas WHERE id = ?", (tarefa_id,))
    conn.commit()
    conn.close()

def get_tarefas_recorrentes():
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT tr.id, tr.titulo, tr.frequencia, tr.intervalo, tr.data_inicio, tr.proxima_execucao, tr.prioridade, tr.visibilidade, tr.ativo,
               u.nome AS responsavel, tr.responsavel_id, c.nome AS cliente, tr.cliente_id, tt.nome AS tipo_tarefa, tr.tipo_tarefa_id,
               gn2.nome AS subgrupo_tarefa, tr.subgrupo_id, tr.descricao, tr.processo_ref
        FROM tarefas_recorrentes tr LEFT JOIN usuarios u ON tr.responsavel_id = u.id LEFT JOIN contatos c ON tr.cliente_id = c.id
        LEFT JOIN tipos_tarefas tt ON tr.tipo_tarefa_id = tt.id LEFT JOIN grupos_tarefas_n2 gn2 ON tr.subgrupo_id = gn2.id ORDER BY tr.proxima_execucao ASC
    """, conn)
    conn.close()
    return df

def add_tarefa_recorrente(titulo, descricao, frequencia, intervalo, data_inicio, prioridade, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO tarefas_recorrentes (titulo, descricao, frequencia, intervalo, data_inicio, proxima_execucao, prioridade, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade, ativo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (titulo, descricao, frequencia, intervalo, str(data_inicio), str(data_inicio), prioridade, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade))
    rid = c.lastrowid
    conn.commit()
    conn.close()
    add_tarefa(titulo, descricao, data_inicio, prioridade, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade, recorrente_origem_id=rid)
    return rid

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
    rid = row[0]
    dt_base = parse_data_iso(row[1])
    c.execute("SELECT frequencia, intervalo, ativo, titulo, descricao, prioridade, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade FROM tarefas_recorrentes WHERE id = ?", (rid,))
    regra = c.fetchone()
    if not regra or regra[2] != 1:
        conn.close()
        return
    nova_dt = calcular_proxima_data(dt_base, regra[0], max(1, int(regra[1] or 1)))
    c.execute("UPDATE tarefas_recorrentes SET proxima_execucao = ? WHERE id = ?", (str(nova_dt), rid))
    conn.commit()
    conn.close()
    add_tarefa(regra[3], regra[4], nova_dt, regra[5], regra[6], regra[7], regra[8], regra[9], regra[10], regra[11], regra[12], recorrente_origem_id=rid)

def sincronizar_tarefas_recorrentes():
    conn = get_connection()
    hoje = str(date.today())
    c = conn.cursor()
    c.execute("SELECT id, titulo, descricao, frequencia, intervalo, proxima_execucao, prioridade, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade FROM tarefas_recorrentes WHERE ativo = 1 AND proxima_execucao <= ?", (hoje,))
    recs = c.fetchall()
    criados = 0
    for r in recs:
        c.execute("SELECT COUNT(*) FROM tarefas WHERE recorrente_origem_id = ? AND data_limite = ?", (r[0], r[5]))
        if c.fetchone()[0] == 0:
            c.execute("""
                INSERT INTO tarefas (titulo, descricao, data_limite, prioridade, status, responsavel_id, cliente_id, processo_ref, tipo_tarefa_id, subgrupo_id, criador_id, visibilidade, recorrente_origem_id, criado_em)
                VALUES (?, ?, ?, ?, 'Não Iniciada', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (r[1], r[2], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13], r[0], hoje))
            criados += 1
    conn.commit()
    conn.close()
    return criados

# --- Funções: Agenda & Recorrência ---
def get_compromissos_df(usuario_logado_id=None):
    conn = get_connection()
    q = """
        SELECT DISTINCT cp.id, cp.titulo, cp.data_inicio, cp.hora_inicio, cp.data_fim, cp.hora_fim, cp.dia_inteiro, cp.local_link, cp.descricao,
               u.nome AS organizador, cp.organizador_id, c.nome AS cliente, cp.cliente_id, cp.processo_ref, cp.visibilidade, cp.recorrente_origem_id
        FROM compromissos cp LEFT JOIN usuarios u ON cp.organizador_id = u.id LEFT JOIN contatos c ON cp.cliente_id = c.id
        LEFT JOIN compromissos_participantes cpp ON cp.id = cpp.compromisso_id
    """
    params = ()
    if usuario_logado_id:
        q += " WHERE (cp.visibilidade = 'Compartilhada' OR cp.organizador_id = ? OR cpp.usuario_id = ?)"
        params = (usuario_logado_id, usuario_logado_id)
    q += " ORDER BY cp.data_inicio ASC, cp.hora_inicio ASC"
    df = pd.read_sql_query(q, conn, params=params)
    conn.close()
    return df

def add_compromisso(titulo, descricao, data_inicio, hora_inicio, data_fim, hora_fim, dia_inteiro, local_link, cliente_id, processo_ref, organizador_id, visibilidade, participantes_ids=None, recorrente_origem_id=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO compromissos (titulo, descricao, data_inicio, hora_inicio, data_fim, hora_fim, dia_inteiro, local_link, cliente_id, processo_ref, organizador_id, visibilidade, recorrente_origem_id, criado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (titulo, descricao, str(data_inicio), str(hora_inicio) if not dia_inteiro else None, str(data_fim), str(hora_fim) if not dia_inteiro else None, 1 if dia_inteiro else 0, local_link, cliente_id, processo_ref, organizador_id, visibilidade, recorrente_origem_id, str(date.today())))
    cid = c.lastrowid
    if participantes_ids:
        for uid in participantes_ids:
            c.execute("INSERT OR IGNORE INTO compromissos_participantes (compromisso_id, usuario_id) VALUES (?, ?)", (cid, uid))
    conn.commit()
    conn.close()
    return cid

def update_compromisso(comp_id, titulo, descricao, data_inicio, hora_inicio, data_fim, hora_fim, dia_inteiro, local_link, cliente_id, processo_ref, visibilidade):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE compromissos SET titulo = ?, descricao = ?, data_inicio = ?, hora_inicio = ?, data_fim = ?, hora_fim = ?, dia_inteiro = ?, local_link = ?, cliente_id = ?, processo_ref = ?, visibilidade = ? WHERE id = ?
    """, (titulo, descricao, str(data_inicio), str(hora_inicio) if not dia_inteiro else None, str(data_fim), str(hora_fim) if not dia_inteiro else None, 1 if dia_inteiro else 0, local_link, cliente_id, processo_ref, visibilidade, comp_id))
    conn.commit()
    conn.close()

def delete_compromisso(comp_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM compromissos_participantes WHERE compromisso_id = ?", (comp_id,))
    c.execute("DELETE FROM compromissos WHERE id = ?", (comp_id,))
    conn.commit()
    conn.close()

def get_compromissos_recorrentes():
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT cr.id, cr.titulo, cr.frequencia, cr.intervalo, cr.data_inicio, cr.hora_inicio, cr.duracao_minutos, cr.dia_inteiro, cr.local_link,
               cr.descricao, u.nome AS organizador, cr.organizador_id, c.nome AS cliente, cr.cliente_id, cr.processo_ref, cr.visibilidade, cr.ativo
        FROM compromissos_recorrentes cr LEFT JOIN usuarios u ON cr.organizador_id = u.id LEFT JOIN contatos c ON cr.cliente_id = c.id ORDER BY cr.data_inicio ASC
    """, conn)
    conn.close()
    return df

def add_compromisso_recorrente(titulo, descricao, frequencia, intervalo, data_inicio, hora_inicio, duracao_minutos, dia_inteiro, local_link, cliente_id, processo_ref, organizador_id, visibilidade, participantes_ids=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO compromissos_recorrentes (titulo, descricao, frequencia, intervalo, data_inicio, hora_inicio, duracao_minutos, dia_inteiro, local_link, cliente_id, processo_ref, organizador_id, visibilidade, ativo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (titulo, descricao, frequencia, max(1, int(intervalo or 1)), str(data_inicio), str(hora_inicio) if not dia_inteiro else None, duracao_minutos, 1 if dia_inteiro else 0, local_link, cliente_id, processo_ref, organizador_id, visibilidade))
    rid = c.lastrowid
    conn.commit()
    conn.close()
    gerar_ocorrencias_compromisso_recorrente(rid, data_inicio, dias_a_frente=60, participantes_ids=participantes_ids)
    return rid

def gerar_ocorrencias_compromisso_recorrente(rec_id, data_base: date, dias_a_frente: int = 60, participantes_ids=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT titulo, descricao, frequencia, intervalo, hora_inicio, duracao_minutos, dia_inteiro, local_link, cliente_id, processo_ref, organizador_id, visibilidade, ativo
        FROM compromissos_recorrentes WHERE id = ?
    """, (rec_id,))
    row = c.fetchone()
    if not row or row[12] != 1:
        conn.close()
        return
    tit, desc, freq, interv, h_ini, dur_min, dia_int, local_l, cli_id, proc, org_id, vis, ativo = row
    limite = date.today() + timedelta(days=dias_a_frente)
    cur = data_base
    iter_seguranca = 0
    while cur <= limite and iter_seguranca < 100:
        iter_seguranca += 1
        c.execute("SELECT COUNT(*) FROM compromissos WHERE recorrente_origem_id = ? AND data_inicio = ?", (rec_id, str(cur)))
        if c.fetchone()[0] == 0:
            if not dia_int and h_ini:
                try:
                    dt_fim_obj = datetime.combine(cur, parse_hora_str(h_ini)) + timedelta(minutes=int(dur_min or 60))
                    d_fim, h_fim = dt_fim_obj.date(), dt_fim_obj.time().strftime("%H:%M")
                except Exception:
                    d_fim, h_fim = cur, h_ini
            else:
                d_fim, h_fim = cur, None
            c.execute("""
                INSERT INTO compromissos (titulo, descricao, data_inicio, hora_inicio, data_fim, hora_fim, dia_inteiro, local_link, cliente_id, processo_ref, organizador_id, visibilidade, recorrente_origem_id, criado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (tit, desc, str(cur), h_ini if not dia_int else None, str(d_fim), h_fim, dia_int, local_l, cli_id, proc, org_id, vis, rec_id, str(date.today())))
            cid = c.lastrowid
            if participantes_ids:
                for uid in participantes_ids:
                    c.execute("INSERT OR IGNORE INTO compromissos_participantes (compromisso_id, usuario_id) VALUES (?, ?)", (cid, uid))
        prox = calcular_proxima_data(cur, freq, max(1, int(interv or 1)))
        if prox <= cur:
            prox = cur + timedelta(days=1)
        cur = prox
    conn.commit()
    conn.close()

def delete_compromisso_recorrente(rec_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM compromissos_recorrentes WHERE id = ?", (rec_id,))
    conn.commit()
    conn.close()

def sincronizar_todos_compromissos_recorrentes():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, data_inicio FROM compromissos_recorrentes WHERE ativo = 1")
    recs = c.fetchall()
    conn.close()
    for rid, dini in recs:
        gerar_ocorrencias_compromisso_recorrente(rid, parse_data_iso(dini), dias_a_frente=60)

# Inicialização do banco
init_db()

# ----------------------------------------------------
# GERENCIAMENTO DE SESSÃO & LOGIN
# ----------------------------------------------------
if "usuario_autenticado" not in st.session_state:
    st.session_state["usuario_autenticado"] = None

if not st.session_state["usuario_autenticado"]:
    st.markdown("<br><br>", unsafe_allow_html=True)
    _, col_l2, _ = st.columns([1, 1.2, 1])
    with col_l2:
        st.markdown("## ⚖️ Fabíola Guimarães Advocacia")
        st.markdown("#### Acesso Restrito ao Sistema")
        with st.form("form_login"):
            login_email = st.text_input("E-mail Profissional", placeholder="fabricioggoncalves@gmail.com")
            login_senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar no Sistema", type="primary", use_container_width=True):
                user = autenticar_usuario(login_email, login_senha)
                if user:
                    st.session_state["usuario_autenticado"] = user
                    st.rerun()
                else:
                    st.error("E-mail ou senha inválidos, ou usuário inativo.")
        st.info("💡 Credenciais padrão: e-mail cadastrado e senha **111111**.")
        with st.expander("🔑 Redefinir senha padrão inicial (Contingência)"):
            reset_email = st.text_input("Confirmar e-mail para reset", value="fabricioggoncalves@gmail.com")
            if st.button("Restaurar senha deste e-mail para 111111"):
                if resetar_senha_padrao_admin(reset_email):
                    st.success("Senha restaurada para 111111!")
                else:
                    st.error("E-mail não encontrado.")
    st.stop()

# Sessão Ativa
usuario_logado = st.session_state["usuario_autenticado"]
operador_atual_id = usuario_logado["id"]
operador_atual_nome = usuario_logado["nome"]

# ----------------------------------------------------
# BARRA LATERAL (ROTEAMENTO POR CHAVE SEGURA)
# ----------------------------------------------------
st.sidebar.markdown("## ⚖️ Fabíola Guimarães")
st.sidebar.caption("ADVOCACIA & CONSULTORIA")
st.sidebar.markdown(f"👤 **{operador_atual_nome}**")
st.sidebar.caption(f"Perfil: {usuario_logado['perfil']}")

if st.sidebar.button("🚪 Sair / Logout", use_container_width=True):
    st.session_state["usuario_autenticado"] = None
    st.rerun()

st.sidebar.divider()

opcoes_modulos = {
    "financeiro": "💼 Gestão Financeira",
    "tarefas": "✅ Gestão de Tarefas",
    "agenda": "📅 Agenda de Compromissos",
    "tabelas": "🛠️ Manutenção de Tabelas (CRUDs)",
    "usuarios": "👥 Usuários"
}

chave_modulo_ativo = st.sidebar.selectbox(
    "Selecione o Módulo:",
    options=list(opcoes_modulos.keys()),
    format_func=lambda k: opcoes_modulos[k],
    key="sistema_principal_chave"
)
st.sidebar.divider()

# ====================================================
# MÓDULO 1: GESTÃO FINANCEIRA
# ====================================================
if chave_modulo_ativo == "financeiro":
    st.title("💼 Gestão Financeira - Dra. Fabíola & Fabrício")
    menu = st.sidebar.radio("Menu Financeiro", ["Painel Geral", "🔴 Contas a Pagar", "🟢 Contas a Receber", "⚡ Gerar Contas a Pagar", "📊 Relatórios", "Cadastros"])

    if menu == "Painel Geral":
        st.subheader("Resumo Financeiro & Balanço")
        df = get_lancamentos_df()
        if df.empty:
            st.info("Nenhum lançamento registrado até o momento.")
        else:
            df["valor"] = pd.to_numeric(df["valor"])
            c1, c2 = st.columns(2)
            tf = c1.multiselect("Tipo", ["Receita", "Despesa"], default=["Receita", "Despesa"])
            sf = c2.multiselect("Status", ["Concluído", "Pendente"], default=["Concluído", "Pendente"])
            df_f = df[(df["tipo"].isin(tf)) & (df["status"].isin(sf))].copy()
            rec = df_f[df_f["tipo"] == "Receita"]["valor"].sum()
            desp = df_f[df_f["tipo"] == "Despesa"]["valor"].sum()
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Receitas", f"R$ {rec:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            m2.metric("Total Despesas", f"R$ {desp:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            m3.metric("Resultado", f"R$ {(rec - desp):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            st.divider()
            st.subheader("⚖️ Acerto de Contas entre Sócios (50/50)")
            desp_pagas = df[(df["tipo"] == "Despesa") & (df["status"] == "Concluído")]
            t_fab = desp_pagas[desp_pagas["pago_por"] == "Fabrício"]["valor"].sum()
            t_fabi = desp_pagas[desp_pagas["pago_por"] == "Fabíola"]["valor"].sum()
            col1, col2, col3 = st.columns(3)
            col1.metric("Pago por Fabrício", f"R$ {t_fab:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            col2.metric("Pago por Fabíola", f"R$ {t_fabi:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            dif = (t_fab - t_fabi) / 2
            with col3:
                if dif > 0:
                    st.success(f"**Fabíola deve a Fabrício:** R$ {dif:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                elif dif < 0:
                    st.info(f"**Fabrício deve a Fabíola:** R$ {abs(dif):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                else:
                    st.success("**Contas equilibradas!**")
            st.divider()
            df_view = df_f[["id", "data_vencimento", "data_pagamento", "tipo", "contato", "conta_sintetica", "conta_analitica", "historico_padrao", "complemento", "valor", "status", "pago_por"]].copy()
            df_view["data_vencimento"] = df_view["data_vencimento"].apply(formatar_data_br)
            df_view["data_pagamento"] = df_view["data_pagamento"].apply(formatar_data_br)
            st.dataframe(df_view, use_container_width=True)

    elif menu in ["🔴 Contas a Pagar", "🟢 Contas a Receber"]:
        tipo_op = "Despesa" if "Pagar" in menu else "Receita"
        st.subheader(f"{'🔴 Contas a Pagar (Despesas)' if tipo_op == 'Despesa' else '🟢 Contas a Receber (Receitas)'}")
        t1, t2, t3, t4 = st.tabs(["➕ Incluir", "✅ Baixa / Confirmação", "✏️ Alterar", "🗑️ Excluir"])
        contatos_df = get_contatos("Fornecedor" if tipo_op == "Despesa" else "Cliente")
        analiticas_df = get_contas_analiticas(tipo_op)
        historicos_df = get_historicos(tipo_op)
        map_cont = {"(Opcional)": None}
        if not contatos_df.empty:
            map_cont.update(dict(zip(contatos_df["nome"], contatos_df["id"])))
        map_anal = dict(zip(analiticas_df["caminho_completo"], analiticas_df["id"])) if not analiticas_df.empty else {}
        map_hist = {"(Sem histórico)": None}
        if not historicos_df.empty:
            map_hist.update({f"{r['codigo']} - {r['descricao']}": r['id'] for _, r in historicos_df.iterrows()})

        with t1:
            if not map_anal:
                st.warning("Cadastre primeiro uma Conta Analítica.")
            else:
                with st.form(f"form_inc_{tipo_op}", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    dt_venc = c1.date_input("Data de Vencimento", value=date.today(), format="DD/MM/YYYY")
                    val = c2.number_input("Valor (R$)", min_value=0.01, step=50.0, format="%.2f")
                    cont_sel = c1.selectbox("Contato", list(map_cont.keys()))
                    anal_sel = c2.selectbox("Classificação Analítica", list(map_anal.keys()))
                    hist_sel = c1.selectbox("Histórico Padrão", list(map_hist.keys()))
                    compl = c2.text_input("Complemento")
                    c3, c4, c5 = st.columns(3)
                    st_sel = c3.selectbox("Status", ["Pendente", "Concluído"])
                    dt_pg = c4.date_input("Data Pagamento", value=date.today(), format="DD/MM/YYYY") if st_sel == "Concluído" else None
                    pg_por = c5.selectbox("Pago por", SOCIOS) if (st_sel == "Concluído" and tipo_op == "Despesa") else None
                    if st.form_submit_button("Salvar"):
                        add_lancamento(tipo_op, dt_venc, val, map_cont[cont_sel], map_hist[hist_sel], map_anal[anal_sel], compl.strip(), st_sel, dt_pg, pg_por)
                        st.success("Lançamento salvo!")
                        st.rerun()

        with t2:
            c1, c2 = st.columns(2)
            d_ini = c1.date_input("Vencimento Inicial", value=date.today().replace(day=1), format="DD/MM/YYYY", key=f"bx_ini_{tipo_op}")
            d_fim = c2.date_input("Vencimento Final", value=date.today(), format="DD/MM/YYYY", key=f"bx_fim_{tipo_op}")
            df_bx = get_lancamentos_df(tipo_op)
            df_pend = df_bx[(df_bx["status"] == "Pendente") & (df_bx["data_vencimento"] >= str(d_ini)) & (df_bx["data_vencimento"] <= str(d_fim))].copy() if not df_bx.empty else pd.DataFrame()
            if df_pend.empty:
                st.info("Nenhum título pendente no período.")
            else:
                df_pend["Baixar?"] = False
                df_pend["data_vencimento"] = df_pend["data_vencimento"].apply(formatar_data_br)
                tb = st.data_editor(df_pend[["Baixar?", "id", "data_vencimento", "contato", "conta_analitica", "complemento", "valor"]], hide_index=True, use_container_width=True)
                sel_ids = tb[tb["Baixar?"] == True]["id"].tolist()
                if sel_ids:
                    with st.form(f"form_bx_{tipo_op}"):
                        c3, c4 = st.columns(2)
                        dt_bx = c3.date_input("Data Efetiva", value=date.today(), format="DD/MM/YYYY")
                        pg_s = c4.selectbox("Pago por", SOCIOS) if tipo_op == "Despesa" else None
                        if st.form_submit_button(f"Confirmar Baixa ({len(sel_ids)} títulos)"):
                            baixar_lancamentos_em_lote(sel_ids, dt_bx, pg_s)
                            st.success("Baixa concluída!")
                            st.rerun()

        with t3:
            df_all = get_lancamentos_df(tipo_op)
            if df_all.empty:
                st.info("Nenhum lançamento cadastrado.")
            else:
                op_map = {f"ID {r['id']} | Venc: {formatar_data_br(r['data_vencimento'])} | R$ {r['valor']:.2f} | {r['contato']}": r['id'] for _, r in df_all.iterrows()}
                l_id = op_map[st.selectbox("Selecione para Alterar", list(op_map.keys()), key=f"sel_alt_{tipo_op}")]
                item = df_all[df_all["id"] == l_id].iloc[0]
                with st.form(f"form_alt_item_{tipo_op}"):
                    c1, c2 = st.columns(2)
                    dt_v = c1.date_input("Vencimento", value=parse_data_iso(item["data_vencimento"]), format="DD/MM/YYYY")
                    vl = c2.number_input("Valor (R$)", value=float(item["valor"]), step=50.0)
                    cp = c1.text_input("Complemento", value=item["complemento"] if pd.notna(item["complemento"]) else "")
                    st_e = c2.selectbox("Status", ["Pendente", "Concluído"], index=0 if item["status"] == "Pendente" else 1)
                    dt_p = c1.date_input("Data Pagamento", value=parse_data_iso(item["data_pagamento"]), format="DD/MM/YYYY") if st_e == "Concluído" else None
                    pg_e = c2.selectbox("Pago por", SOCIOS, index=SOCIOS.index(item["pago_por"]) if item["pago_por"] in SOCIOS else 0) if (st_e == "Concluído" and tipo_op == "Despesa") else None
                    if st.form_submit_button("Atualizar"):
                        update_lancamento(l_id, tipo_op, dt_v, dt_p, vl, item["contato_id"], item["historico_id"], item["conta_analitica_id"], cp.strip(), st_e, pg_e)
                        st.success("Atualizado!")
                        st.rerun()

        with t4:
            df_all = get_lancamentos_df(tipo_op)
            if not df_all.empty:
                del_map = {f"ID {r['id']} | Venc: {formatar_data_br(r['data_vencimento'])} | R$ {r['valor']:.2f} | {r['contato']}": r['id'] for _, r in df_all.iterrows()}
                d_id = del_map[st.selectbox("Selecione para Excluir", list(del_map.keys()), key=f"sel_del_{tipo_op}")]
                if st.button("🗑️ Excluir Lançamento", type="primary"):
                    delete_lancamento(d_id)
                    st.success("Excluído!")
                    st.rerun()

    elif menu == "⚡ Gerar Contas a Pagar":
        st.subheader("⚡ Geração Automática Mensal de Contas a Pagar")
        c1, c2 = st.columns(2)
        mes = c1.selectbox("Mês", list(range(1, 13)), index=date.today().month - 1)
        ano = c2.number_input("Ano", min_value=2024, max_value=2040, value=date.today().year)
        if st.button("Executar Geração", type="primary"):
            g, ig, msg = gerar_contas_do_mes(ano, mes)
            st.success(f"Concluído! {g} geradas, {ig} ignoradas (já existiam).")
            st.rerun()

    elif menu == "📊 Relatórios":
        st.subheader("📊 Relatórios Financeiros")
        df_base = get_lancamentos_df()
        if not df_base.empty:
            df_base["valor"] = pd.to_numeric(df_base["valor"])
            c1, c2 = st.columns(2)
            d1 = c1.date_input("Início", value=date.today().replace(day=1), format="DD/MM/YYYY")
            d2 = c2.date_input("Fim", value=date.today(), format="DD/MM/YYYY")
            df_rel = df_base[(df_base["data_vencimento"] >= str(d1)) & (df_base["data_vencimento"] <= str(d2))]
            st.dataframe(df_rel, use_container_width=True)
            st.download_button("Exportar Excel", data=to_excel_bytes(df_rel, "Financeiro"), file_name="relatorio_financeiro.xlsx", use_container_width=True)

    elif menu == "Cadastros":
        st.subheader("Cadastros de Apoio Financeiro")
        t_rec, t_reg = st.tabs(["Contas Recorrentes", "Regras de Classificação"])
        with t_rec:
            st.dataframe(get_contas_recorrentes(), use_container_width=True)
        with t_reg:
            st.dataframe(get_regras_classificacao(), use_container_width=True)

# ====================================================
# MÓDULO 2: GESTÃO DE TAREFAS
# ====================================================
elif chave_modulo_ativo == "tarefas":
    st.title("✅ Fabíola Guimarães Advocacia — Gestão de Tarefas")
    tab_p, tab_n, tab_rec, tab_rel, tab_g = st.tabs(["📋 Painel de Tarefas", "➕ Nova Tarefa", "🔄 Tarefas Recorrentes", "📊 Relatórios de Tarefas", "⚙️ Gerenciar / Alterar"])

    with tab_p:
        c1, c2 = st.columns([3, 1])
        with c2:
            if st.button("⚡ Sincronizar Recorrentes", use_container_width=True):
                q = sincronizar_tarefas_recorrentes()
                st.success(f"{q} nova(s) tarefa(s) gerada(s)!")
                st.rerun()
        df_tar = get_tarefas_df(operador_atual_id)
        if df_tar.empty:
            st.info("Nenhuma tarefa cadastrada.")
        else:
            col1, col2, col3 = st.columns(3)
            st_f = col1.multiselect("Status", ["Não Iniciada", "Em Andamento", "Concluída", "Cancelada"], default=["Não Iniciada", "Em Andamento"])
            pr_f = col2.multiselect("Prioridade", ["Baixa", "Média", "Alta", "Urgente"], default=["Baixa", "Média", "Alta", "Urgente"])
            u_df = get_usuarios(True)
            u_lista = ["Todos"] + u_df["nome"].tolist() if not u_df.empty else ["Todos"]
            resp_f = col3.selectbox("Responsável", u_lista)
            df_fil = df_tar[(df_tar["status"].isin(st_f)) & (df_tar["prioridade"].isin(pr_f))]
            if resp_f != "Todos":
                df_fil = df_fil[df_fil["responsavel"] == resp_f]
            df_v = df_fil[["id", "titulo", "status", "prioridade", "data_limite", "responsavel", "tipo_tarefa", "grupo_tarefa", "subgrupo_tarefa", "cliente", "processo_ref"]].copy()
            df_v["data_limite"] = df_v["data_limite"].apply(formatar_data_br)
            st.dataframe(df_v, use_container_width=True)

    with tab_n:
        st.markdown("#### Criar Nova Tarefa")
        tipos_df = get_tipos_tarefas()
        subg_df = get_grupos_tarefas_n2()
        u_df = get_usuarios(True)
        cli_df = get_contatos("Cliente")
        if tipos_df.empty or subg_df.empty:
            st.warning("Cadastre Grupos/Subgrupos e Tipos de Tarefas em 'Manutenção de Tabelas'.")
        else:
            m_tipos = dict(zip(tipos_df["nome"], tipos_df["id"]))
            m_subg = dict(zip(subg_df["caminho_completo"], subg_df["id"]))
            m_u = dict(zip(u_df["nome"], u_df["id"])) if not u_df.empty else {}
            m_cli = {"(Nenhum)": None}
            if not cli_df.empty:
                m_cli.update(dict(zip(cli_df["nome"], cli_df["id"])))
            with st.form("form_nova_tarefa", clear_on_submit=True):
                c1, c2 = st.columns(2)
                tit = c1.text_input("Título da Tarefa")
                dt_l = c2.date_input("Prazo Limite", value=date.today(), format="DD/MM/YYYY")
                tipo_s = c1.selectbox("Tipo de Tarefa", list(m_tipos.keys()))
                subg_s = c2.selectbox("Grupo / Subgrupo", list(m_subg.keys()))
                prio_s = c1.selectbox("Prioridade", ["Baixa", "Média", "Alta", "Urgente"], index=1)
                resp_s = c2.selectbox("Responsável", list(m_u.keys()))
                cli_s = c1.selectbox("Cliente", list(m_cli.keys()))
                proc = c2.text_input("Processo (Opcional)")
                desc = st.text_area("Descrição")
                vis = st.radio("Visibilidade", ["Compartilhada", "Privada"], horizontal=True)
                if st.form_submit_button("Salvar Tarefa", type="primary"):
                    if tit.strip():
                        add_tarefa(tit.strip(), desc.strip(), dt_l, prio_s, m_u[resp_s], m_cli[cli_s], proc.strip(), m_tipos[tipo_s], m_subg[subg_s], operador_atual_id, vis)
                        st.success("Tarefa cadastrada!")
                        st.rerun()

    with tab_rec:
        st.markdown("#### Tarefas Recorrentes (Rotinas Periódicas)")
        t_rec_in, t_rec_ls = st.tabs(["➕ Nova Regra", "📋 Regras Ativas"])
        with t_rec_in:
            tipos_df = get_tipos_tarefas()
            subg_df = get_grupos_tarefas_n2()
            u_df = get_usuarios(True)
            if not tipos_df.empty and not subg_df.empty:
                m_tipos = dict(zip(tipos_df["nome"], tipos_df["id"]))
                m_subg = dict(zip(subg_df["caminho_completo"], subg_df["id"]))
                m_u = dict(zip(u_df["nome"], u_df["id"]))
                with st.form("form_inc_tar_rec", clear_on_submit=True):
                    c1, c2, c3 = st.columns(3)
                    tit_r = c1.text_input("Título da Rotina")
                    freq_r = c2.selectbox("Frequência", ["Semanal", "Diária", "Mensal", "Anual"], index=0)
                    dt_ini_r = c3.date_input("Início", value=date.today(), format="DD/MM/YYYY")
                    tipo_sr = c1.selectbox("Tipo de Tarefa", list(m_tipos.keys()))
                    subg_sr = c2.selectbox("Grupo / Subgrupo", list(m_subg.keys()))
                    resp_sr = c3.selectbox("Responsável", list(m_u.keys()))
                    desc_r = st.text_area("Instruções")
                    if st.form_submit_button("Criar Regra Recorrente"):
                        if tit_r.strip():
                            add_tarefa_recorrente(tit_r.strip(), desc_r.strip(), freq_r, 1, dt_ini_r, "Média", m_u[resp_sr], None, "", m_tipos[tipo_sr], m_subg[subg_sr], operador_atual_id, "Compartilhada")
                            st.success("Regra criada!")
                            st.rerun()
        with t_rec_ls:
            df_recs = get_tarefas_recorrentes()
            if df_recs.empty:
                st.info("Nenhuma rotina cadastrada.")
            else:
                st.dataframe(df_recs[["id", "titulo", "frequencia", "proxima_execucao", "responsavel", "subgrupo_tarefa"]], use_container_width=True)
                r_map = {f"ID {r['id']} | {r['titulo']}": r['id'] for _, r in df_recs.iterrows()}
                d_rid = r_map[st.selectbox("Excluir Regra", list(r_map.keys()))]
                if st.button("🗑️ Excluir Regra de Recorrência", type="primary"):
                    delete_tarefa_recorrente(d_rid)
                    st.success("Regra removida!")
                    st.rerun()

    with tab_rel:
        st.markdown("#### 📊 Relatórios de Tarefas com Pré-Filtros")
        c1, c2, c3 = st.columns([1.5, 1.2, 1.3])
        pf_dt = c1.radio("Período:", ["Todas", "Vencidas", "Hoje", "Amanhã", "Esta Semana", "Este Mês"], horizontal=True)
        pf_st = c2.selectbox("Status:", ["Todas", "Pendentes (Ativas)", "Concluídas"])
        u_df = get_usuarios(True)
        resp_lista = ["Todos os Responsáveis", "👤 Minhas Tarefas"] + (u_df["nome"].tolist() if not u_df.empty else [])
        pf_resp = c3.selectbox("Responsável:", resp_lista)
        
        df_tar_base = get_tarefas_df(operador_atual_id)
        if not df_tar_base.empty:
            df_rf = df_tar_base.copy()
            hoje = date.today()
            if pf_dt == "Hoje":
                df_rf = df_rf[df_rf["data_limite"] == str(hoje)]
            elif pf_dt == "Amanhã":
                df_rf = df_rf[df_rf["data_limite"] == str(hoje + timedelta(days=1))]
            elif pf_dt == "Vencidas":
                df_rf = df_rf[(df_rf["data_limite"] < str(hoje)) & (df_rf["status"] != "Concluída")]
            elif pf_dt == "Esta Semana":
                ini_s = hoje - timedelta(days=hoje.weekday())
                df_rf = df_rf[(df_rf["data_limite"] >= str(ini_s)) & (df_rf["data_limite"] <= str(ini_s + timedelta(days=6)))]
            elif pf_dt == "Este Mês":
                df_rf = df_rf[(df_rf["data_limite"] >= str(hoje.replace(day=1))) & (df_rf["data_limite"] <= str(hoje.replace(day=calendar.monthrange(hoje.year, hoje.month)[1])))]

            if pf_st == "Pendentes (Ativas)":
                df_rf = df_rf[df_rf["status"].isin(["Não Iniciada", "Em Andamento"])]
            elif pf_st == "Concluídas":
                df_rf = df_rf[df_rf["status"] == "Concluída"]

            if pf_resp == "👤 Minhas Tarefas":
                df_rf = df_rf[df_rf["responsavel_id"] == operador_atual_id]
            elif pf_resp != "Todos os Responsáveis":
                df_rf = df_rf[df_rf["responsavel"] == pf_resp]

            st.metric("Total de Tarefas Filtradas", len(df_rf))
            df_rf_view = df_rf[["id", "titulo", "status", "prioridade", "data_limite", "responsavel", "tipo_tarefa", "grupo_tarefa", "subgrupo_tarefa", "cliente", "processo_ref"]].copy()
            df_rf_view["data_limite"] = df_rf_view["data_limite"].apply(formatar_data_br)
            st.dataframe(df_rf_view, use_container_width=True)
            st.download_button("Exportar (.XLSX)", data=to_excel_bytes(df_rf_view, "Tarefas"), file_name="relatorio_tarefas.xlsx", use_container_width=True)

    with tab_g:
        df_tar_all = get_tarefas_df(operador_atual_id)
        if df_tar_all.empty:
            st.info("Nenhuma tarefa para gerenciar.")
        else:
            t_map = {f"ID {r['id']} | [{r['status']}] {r['titulo']} (Prazo: {formatar_data_br(r['data_limite'])})": r['id'] for _, r in df_tar_all.iterrows()}
            tar_id = t_map[st.selectbox("Selecione a Tarefa", list(t_map.keys()))]
            item_t = df_tar_all[df_tar_all["id"] == tar_id].iloc[0]
            with st.form("form_edit_tar"):
                c1, c2 = st.columns(2)
                t_tit = c1.text_input("Título", value=item_t["titulo"])
                t_dt = c2.date_input("Prazo Limite", value=parse_data_iso(item_t["data_limite"]), format="DD/MM/YYYY")
                st_list = ["Não Iniciada", "Em Andamento", "Concluída", "Cancelada"]
                t_st = c1.selectbox("Status", st_list, index=st_list.index(item_t["status"]) if item_t["status"] in st_list else 0)
                pr_list = ["Baixa", "Média", "Alta", "Urgente"]
                t_pr = c2.selectbox("Prioridade", pr_list, index=pr_list.index(item_t["prioridade"]) if item_t["prioridade"] in pr_list else 1)
                t_desc = st.text_area("Descrição", value=item_t["descricao"] if pd.notna(item_t["descricao"]) else "")
                if st.form_submit_button("Atualizar Tarefa"):
                    update_tarefa(tar_id, t_tit.strip(), t_desc.strip(), t_dt, t_pr, t_st, item_t["responsavel_id"], item_t["cliente_id"], item_t["processo_ref"], item_t["tipo_tarefa_id"], item_t["subgrupo_id"], item_t["visibilidade"])
                    st.success("Tarefa atualizada!")
                    st.rerun()
            if st.button("🗑️ Excluir Tarefa", type="primary"):
                delete_tarefa(tar_id)
                st.success("Tarefa excluída!")
                st.rerun()

# ====================================================
# MÓDULO 3: AGENDA DE COMPROMISSOS (COM RECORRÊNCIA)
# ====================================================
elif chave_modulo_ativo == "agenda":
    st.title("📅 Fabíola Guimarães Advocacia — Agenda de Compromissos")
    t_v, t_n, t_rec, t_g = st.tabs(["📆 Visualizar Agenda", "➕ Novo Compromisso", "🔄 Compromissos Recorrentes", "⚙️ Gerenciar / Alterar"])

    with t_v:
        c1, c2 = st.columns([3, 1])
        with c2:
            if st.button("⚡ Sincronizar Agenda", use_container_width=True):
                sincronizar_todos_compromissos_recorrentes()
                st.success("Ocorrências atualizadas!")
                st.rerun()
        df_cp = get_compromissos_df(operador_atual_id)
        if df_cp.empty:
            st.info("Nenhum compromisso agendado.")
        else:
            df_cp_v = df_cp[["id", "titulo", "data_inicio", "hora_inicio", "data_fim", "hora_fim", "local_link", "organizador", "cliente", "processo_ref", "descricao"]].copy()
            df_cp_v["data_inicio"] = df_cp_v["data_inicio"].apply(formatar_data_br)
            df_cp_v["data_fim"] = df_cp_v["data_fim"].apply(formatar_data_br)
            st.dataframe(df_cp_v, use_container_width=True)

    with t_n:
        st.markdown("#### Agendar Compromisso")
        u_df = get_usuarios(True)
        cli_df = get_contatos("Cliente")
        m_cli = {"(Nenhum)": None}
        if not cli_df.empty:
            m_cli.update(dict(zip(cli_df["nome"], cli_df["id"])))
        with st.form("form_novo_comp", clear_on_submit=True):
            c1, c2 = st.columns(2)
            c_tit = c1.text_input("Título")
            c_loc = c2.text_input("Local ou Link")
            c3, c4, c5, c6 = st.columns(4)
            d_ini = c3.date_input("Data Início", value=date.today(), format="DD/MM/YYYY")
            h_ini = c4.time_input("Hora Início", value=time(9, 0))
            d_fim = c5.date_input("Data Término", value=date.today(), format="DD/MM/YYYY")
            h_fim = c6.time_input("Hora Término", value=time(10, 0))
            c_cli = c1.selectbox("Cliente", list(m_cli.keys()))
            c_proc = c2.text_input("Processo (Opcional)")
            c_desc = st.text_area("Anotações")
            if st.form_submit_button("Salvar Compromisso", type="primary"):
                if c_tit.strip():
                    add_compromisso(c_tit.strip(), c_desc.strip(), d_ini, h_ini.strftime("%H:%M"), d_fim, h_fim.strftime("%H:%M"), 0, c_loc.strip(), m_cli[c_cli], c_proc.strip(), operador_atual_id, "Compartilhada")
                    st.success("Compromisso salvo!")
                    st.rerun()

    with t_rec:
        st.markdown("#### Compromissos Periódicos da Agenda")
        t_cr_in, t_cr_ls = st.tabs(["➕ Nova Regra", "📋 Regras Cadastradas"])
        with t_cr_in:
            with st.form("form_inc_comp_rec", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                cr_tit = c1.text_input("Título")
                cr_freq = c2.selectbox("Frequência", ["Semanal", "Diária", "Mensal", "Anual"])
                cr_dt = c3.date_input("Data Início", value=date.today(), format="DD/MM/YYYY")
                c4, c5 = st.columns(2)
                cr_hr = c4.time_input("Horário", value=time(9, 0))
                cr_dur = c5.number_input("Duração (Minutos)", min_value=15, max_value=480, value=60, step=15)
                cr_loc = st.text_input("Local / Link")
                if st.form_submit_button("Criar Regra de Repetição"):
                    if cr_tit.strip():
                        add_compromisso_recorrente(cr_tit.strip(), "", cr_freq, 1, cr_dt, cr_hr.strftime("%H:%M"), int(cr_dur), 0, cr_loc.strip(), None, "", operador_atual_id, "Compartilhada")
                        st.success("Regra criada e ocorrências geradas!")
                        st.rerun()
        with t_cr_ls:
            df_crec = get_compromissos_recorrentes()
            if df_crec.empty:
                st.info("Nenhuma regra de repetição de agenda cadastrada.")
            else:
                st.dataframe(df_crec[["id", "titulo", "frequencia", "data_inicio", "hora_inicio", "local_link"]], use_container_width=True)
                cr_map = {f"ID {r['id']} | {r['titulo']}": r['id'] for _, r in df_crec.iterrows()}
                c_del_id = cr_map[st.selectbox("Excluir Regra de Repetição", list(cr_map.keys()))]
                if st.button("🗑️ Excluir Regra", type="primary"):
                    delete_compromisso_recorrente(c_del_id)
                    st.success("Regra excluída!")
                    st.rerun()

    with t_g:
        df_cp_all = get_compromissos_df(operador_atual_id)
        if df_cp_all.empty:
            st.info("Nenhum compromisso para alterar.")
        else:
            cp_map = {f"ID {r['id']} | {r['titulo']} ({formatar_data_br(r['data_inicio'])})": r['id'] for _, r in df_cp_all.iterrows()}
            comp_id = cp_map[st.selectbox("Selecione para Alterar", list(cp_map.keys()))]
            item_c = df_cp_all[df_cp_all["id"] == comp_id].iloc[0]
            with st.form("form_edit_comp"):
                c1, c2 = st.columns(2)
                ce_tit = c1.text_input("Título", value=item_c["titulo"])
                ce_loc = c2.text_input("Local/Link", value=item_c["local_link"] if pd.notna(item_c["local_link"]) else "")
                ce_dt = c1.date_input("Data", value=parse_data_iso(item_c["data_inicio"]), format="DD/MM/YYYY")
                ce_hr = c2.time_input("Hora", value=parse_hora_str(item_c["hora_inicio"]))
                ce_desc = st.text_area("Descrição", value=item_c["descricao"] if pd.notna(item_c["descricao"]) else "")
                if st.form_submit_button("Atualizar"):
                    update_compromisso(comp_id, ce_tit.strip(), ce_desc.strip(), ce_dt, ce_hr.strftime("%H:%M"), ce_dt, ce_hr.strftime("%H:%M"), 0, ce_loc.strip(), item_c["cliente_id"], item_c["processo_ref"], item_c["visibilidade"])
                    st.success("Atualizado!")
                    st.rerun()
            if st.button("🗑️ Excluir Compromisso", type="primary"):
                delete_compromisso(comp_id)
                st.success("Compromisso excluído!")
                st.rerun()

# ====================================================
# MÓDULO 4: MANUTENÇÃO DE TABELAS (CRUDs COMPLETOS)
# ====================================================
elif chave_modulo_ativo == "tabelas":
    st.title("🛠️ Manutenção de Tabelas e Cadastros")
    st.markdown("Gerencie centralizadamente todas as tabelas de apoio do escritório.")
    
    t_tipos, t_grupos, t_plano, t_hist, t_cont, t_regras = st.tabs([
        "🏷️ Tipos de Tarefas", "📂 Grupos de Tarefas (2 Níveis)", "🌳 Plano de Contas", "📑 Históricos Padrão", "👥 Clientes e Fornecedores", "⚙️ Regras de Classificação"
    ])

    with t_tipos:
        st.subheader("Tipos de Tarefas")
        c1, c2, c3 = st.tabs(["➕ Incluir", "✏️ Alterar", "🗑️ Excluir"])
        with c1:
            with st.form("f_inc_tt", clear_on_submit=True):
                n_tt = st.text_input("Nome do Tipo")
                if st.form_submit_button("Salvar") and n_tt.strip():
                    if add_tipo_tarefa(n_tt):
                        st.success("Cadastrado!")
                        st.rerun()
        with c2:
            df_tt = get_tipos_tarefas()
            if not df_tt.empty:
                m_tt = dict(zip(df_tt["nome"], df_tt["id"]))
                s_tt = st.selectbox("Selecione", list(m_tt.keys()), key="alt_tt")
                with st.form("f_alt_tt"):
                    nn_tt = st.text_input("Novo Nome", value=s_tt)
                    if st.form_submit_button("Atualizar") and nn_tt.strip():
                        update_tipo_tarefa(m_tt[s_tt], nn_tt)
                        st.success("Atualizado!")
                        st.rerun()
        with c3:
            df_tt = get_tipos_tarefas()
            if not df_tt.empty:
                m_tt = dict(zip(df_tt["nome"], df_tt["id"]))
                d_tt = st.selectbox("Excluir", list(m_tt.keys()), key="del_tt")
                if st.button("Excluir Tipo", type="primary"):
                    delete_tipo_tarefa(m_tt[d_tt])
                    st.success("Excluído!")
                    st.rerun()
        st.dataframe(get_tipos_tarefas(), use_container_width=True)

    with t_grupos:
        st.subheader("Grupos e Subgrupos de Tarefas")
        sub_g1, sub_g2 = st.tabs(["Nível 1: Grupos", "Nível 2: Subgrupos"])
        with sub_g1:
            g1_inc, g1_alt, g1_exc = st.tabs(["➕ Incluir", "✏️ Alterar", "🗑️ Excluir"])
            with g1_inc:
                with st.form("f_inc_g1", clear_on_submit=True):
                    ng1 = st.text_input("Nome do Grupo Nível 1")
                    if st.form_submit_button("Salvar Grupo N1") and ng1.strip():
                        if add_grupo_tarefas_n1(ng1):
                            st.success("Grupo N1 cadastrado!")
                            st.rerun()
            with g1_alt:
                df_g1 = get_grupos_tarefas_n1()
                if not df_g1.empty:
                    mg1 = dict(zip(df_g1["nome"], df_g1["id"]))
                    sg1 = st.selectbox("Selecione para Alterar", list(mg1.keys()), key="alt_g1")
                    with st.form("f_alt_g1"):
                        nng1 = st.text_input("Novo Nome", value=sg1)
                        if st.form_submit_button("Atualizar") and nng1.strip():
                            update_grupo_tarefas_n1(mg1[sg1], nng1)
                            st.success("Atualizado!")
                            st.rerun()
            with g1_exc:
                df_g1 = get_grupos_tarefas_n1()
                if not df_g1.empty:
                    mg1 = dict(zip(df_g1["nome"], df_g1["id"]))
                    dg1 = st.selectbox("Selecione para Excluir", list(mg1.keys()), key="del_g1")
                    st.warning("⚠️ Ao excluir o Grupo N1, todos os subgrupos N2 vinculados serão excluídos permanentemente.")
                    if st.button("Excluir Grupo N1 Definitivamente", type="primary"):
                        delete_grupo_tarefas_n1(mg1[dg1])
                        st.success("Grupo N1 excluído sem retornar!")
                        st.rerun()
            st.dataframe(get_grupos_tarefas_n1(), use_container_width=True)

        with sub_g2:
            g2_inc, g2_alt, g2_exc = st.tabs(["➕ Incluir", "✏️ Alterar", "🗑️ Excluir"])
            df_g1_disp = get_grupos_tarefas_n1()
            with g2_inc:
                if df_g1_disp.empty:
                    st.warning("Cadastre primeiro um Grupo Nível 1.")
                else:
                    mg1 = dict(zip(df_g1_disp["nome"], df_g1_disp["id"]))
                    with st.form("f_inc_g2", clear_on_submit=True):
                        pg1 = st.selectbox("Grupo Pai (Nível 1)", list(mg1.keys()))
                        ng2 = st.text_input("Nome do Subgrupo Nível 2")
                        if st.form_submit_button("Salvar Subgrupo N2") and ng2.strip():
                            if add_grupo_tarefas_n2(mg1[pg1], ng2):
                                st.success("Subgrupo cadastrado!")
                                st.rerun()
            with g2_alt:
                df_g2 = get_grupos_tarefas_n2()
                if not df_g2.empty:
                    mg2 = dict(zip(df_g2["caminho_completo"], df_g2["id"]))
                    sg2 = st.selectbox("Selecione para Alterar", list(mg2.keys()), key="alt_g2")
                    it_g2 = df_g2[df_g2["id"] == mg2[sg2]].iloc[0]
                    mg1 = dict(zip(df_g1_disp["nome"], df_g1_disp["id"]))
                    with st.form("f_alt_g2"):
                        n_pg1 = st.selectbox("Grupo Pai", list(mg1.keys()), index=list(mg1.values()).index(it_g2["grupo_n1_id"]))
                        n_ng2 = st.text_input("Nome Subgrupo", value=it_g2["subgrupo_n2"])
                        if st.form_submit_button("Atualizar") and n_ng2.strip():
                            update_grupo_tarefas_n2(it_g2["id"], mg1[n_pg1], n_ng2)
                            st.success("Atualizado!")
                            st.rerun()
            with g2_exc:
                df_g2 = get_grupos_tarefas_n2()
                if not df_g2.empty:
                    mg2 = dict(zip(df_g2["caminho_completo"], df_g2["id"]))
                    dg2 = st.selectbox("Selecione para Excluir", list(mg2.keys()), key="del_g2")
                    if st.button("Excluir Subgrupo N2", type="primary"):
                        delete_grupo_tarefas_n2(mg2[dg2])
                        st.success("Subgrupo excluído!")
                        st.rerun()
            st.dataframe(get_grupos_tarefas_n2(), use_container_width=True)

    with t_plano:
        st.subheader("Plano de Contas Financeiro")
        sp_sint, sp_anal = st.tabs(["Contas Sintéticas", "Contas Analíticas"])
        with sp_sint:
            s1, s2, s3 = st.tabs(["➕ Incluir", "✏️ Alterar", "🗑️ Excluir"])
            with s1:
                with st.form("f_inc_sint", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    tp_s = c1.selectbox("Tipo", ["Receita", "Despesa"])
                    nm_s = c2.text_input("Nome da Conta Sintética")
                    if st.form_submit_button("Salvar") and nm_s.strip():
                        if add_conta_sintetica(tp_s, nm_s):
                            st.success("Cadastrado!")
                            st.rerun()
            with s2:
                df_sint = get_contas_sinteticas()
                if not df_sint.empty:
                    msint = {f"[{r['tipo']}] {r['nome']}": r['id'] for _, r in df_sint.iterrows()}
                    sel_s = st.selectbox("Selecione para Alterar", list(msint.keys()), key="alt_sint")
                    it_s = df_sint[df_sint["id"] == msint[sel_s]].iloc[0]
                    with st.form("f_alt_sint"):
                        c1, c2 = st.columns(2)
                        ntp_s = c1.selectbox("Tipo", ["Receita", "Despesa"], index=0 if it_s["tipo"] == "Receita" else 1)
                        nnm_s = c2.text_input("Nome", value=it_s["nome"])
                        if st.form_submit_button("Atualizar") and nnm_s.strip():
                            update_conta_sintetica(it_s["id"], ntp_s, nnm_s)
                            st.success("Atualizado!")
                            st.rerun()
            with s3:
                df_sint = get_contas_sinteticas()
                if not df_sint.empty:
                    msint = {f"[{r['tipo']}] {r['nome']}": r['id'] for _, r in df_sint.iterrows()}
                    ds = msint[st.selectbox("Selecione para Excluir", list(msint.keys()), key="del_sint")]
                    if st.button("Excluir Conta Sintética", type="primary"):
                        delete_conta_sintetica(ds)
                        st.success("Excluído!")
                        st.rerun()
            st.dataframe(get_contas_sinteticas(), use_container_width=True)

        with sp_anal:
            a1, a2, a3 = st.tabs(["➕ Incluir", "✏️ Alterar", "🗑️ Excluir"])
            df_sint_disp = get_contas_sinteticas()
            with a1:
                if df_sint_disp.empty:
                    st.warning("Cadastre primeiro uma Conta Sintética.")
                else:
                    msint = {f"[{r['tipo']}] {r['nome']}": r['id'] for _, r in df_sint_disp.iterrows()}
                    with st.form("f_inc_anal", clear_on_submit=True):
                        psint = st.selectbox("Conta Sintética Pai", list(msint.keys()))
                        nan = st.text_input("Nome da Conta Analítica")
                        if st.form_submit_button("Salvar") and nan.strip():
                            if add_conta_analitica(msint[psint], nan):
                                st.success("Cadastrado!")
                                st.rerun()
            with a2:
                df_an = get_contas_analiticas()
                if not df_an.empty:
                    man = dict(zip(df_an["caminho_completo"], df_an["id"]))
                    san = st.selectbox("Selecione para Alterar", list(man.keys()), key="alt_anal")
                    it_an = df_an[df_an["id"] == man[san]].iloc[0]
                    msint = {f"[{r['tipo']}] {r['nome']}": r['id'] for _, r in df_sint_disp.iterrows()}
                    with st.form("f_alt_anal"):
                        n_psint = st.selectbox("Conta Sintética Pai", list(msint.keys()), index=list(msint.values()).index(it_an["sintetica_id"]))
                        n_nan = st.text_input("Nome Analítica", value=it_an["conta_analitica"])
                        if st.form_submit_button("Atualizar") and n_nan.strip():
                            update_conta_analitica(it_an["id"], msint[n_psint], n_nan)
                            st.success("Atualizado!")
                            st.rerun()
            with a3:
                df_an = get_contas_analiticas()
                if not df_an.empty:
                    man = dict(zip(df_an["caminho_completo"], df_an["id"]))
                    dan = man[st.selectbox("Selecione para Excluir", list(man.keys()), key="del_anal")]
                    if st.button("Excluir Conta Analítica", type="primary"):
                        delete_conta_analitica(dan)
                        st.success("Excluído!")
                        st.rerun()
            st.dataframe(get_contas_analiticas(), use_container_width=True)

    with t_hist:
        st.subheader("Históricos Padrão")
        h1, h2, h3 = st.tabs(["➕ Incluir", "✏️ Alterar", "🗑️ Excluir"])
        with h1:
            with st.form("f_inc_h", clear_on_submit=True):
                c1, c2 = st.columns(2)
                cod_h = c1.text_input("Código")
                tp_h = c2.selectbox("Aplica-se a", ["Receita", "Despesa", "Ambos"])
                desc_h = st.text_input("Descrição")
                if st.form_submit_button("Salvar") and cod_h.strip() and desc_h.strip():
                    if add_historico(cod_h, desc_h, tp_h):
                        st.success("Cadastrado!")
                        st.rerun()
        with h2:
            df_h = get_historicos()
            if not df_h.empty:
                mh = {f"{r['codigo']} - {r['descricao']}": r['id'] for _, r in df_h.iterrows()}
                sh = st.selectbox("Selecione para Alterar", list(mh.keys()), key="alt_h")
                it_h = df_h[df_h["id"] == mh[sh]].iloc[0]
                with st.form("f_alt_h"):
                    c1, c2 = st.columns(2)
                    ncod = c1.text_input("Código", value=it_h["codigo"])
                    ntp = c2.selectbox("Tipo", ["Receita", "Despesa", "Ambos"], index=["Receita", "Despesa", "Ambos"].index(it_h["tipo_aplicavel"]))
                    ndesc = st.text_input("Descrição", value=it_h["descricao"])
                    if st.form_submit_button("Atualizar") and ncod.strip() and ndesc.strip():
                        update_historico(it_h["id"], ncod, ndesc, ntp)
                        st.success("Atualizado!")
                        st.rerun()
        with h3:
            df_h = get_historicos()
            if not df_h.empty:
                mh = {f"{r['codigo']} - {r['descricao']}": r['id'] for _, r in df_h.iterrows()}
                dh = mh[st.selectbox("Selecione para Excluir", list(mh.keys()), key="del_h")]
                if st.button("Excluir Histórico", type="primary"):
                    delete_historico(dh)
                    st.success("Excluído!")
                    st.rerun()
        st.dataframe(get_historicos(), use_container_width=True)

    with t_cont:
        st.subheader("Clientes e Fornecedores")
        tc_cli, tc_forn = st.tabs(["Clientes", "Fornecedores"])
        for aba, t_ent in [(tc_cli, "Cliente"), (tc_forn, "Fornecedor")]:
            with aba:
                c1, c2, c3 = st.tabs(["➕ Incluir", "✏️ Alterar", "🗑️ Excluir"])
                with c1:
                    with st.form(f"f_inc_{t_ent}", clear_on_submit=True):
                        nm_c = st.text_input(f"Nome do {t_ent}")
                        if st.form_submit_button("Salvar") and nm_c.strip():
                            add_contato(nm_c.strip(), t_ent)
                            st.success("Salvo!")
                            st.rerun()
                with c2:
                    df_c = get_contatos(t_ent)
                    if not df_c.empty:
                        mc = dict(zip(df_c["nome"], df_c["id"]))
                        sc = st.selectbox("Selecione", list(mc.keys()), key=f"alt_{t_ent}")
                        with st.form(f"f_alt_{t_ent}"):
                            nnc = st.text_input("Novo Nome", value=sc)
                            if st.form_submit_button("Atualizar") and nnc.strip():
                                update_contato(mc[sc], nnc.strip())
                                st.success("Atualizado!")
                                st.rerun()
                with c3:
                    df_c = get_contatos(t_ent)
                    if not df_c.empty:
                        mc = dict(zip(df_c["nome"], df_c["id"]))
                        dc = mc[st.selectbox("Excluir", list(mc.keys()), key=f"del_{t_ent}")]
                        if st.button(f"Excluir {t_ent}", type="primary"):
                            delete_contato(dc)
                            st.success("Excluído!")
                            st.rerun()
                st.dataframe(get_contatos(t_ent), use_container_width=True)

    with t_regras:
        st.subheader("Regras de Classificação Automática")
        r1, r2 = st.tabs(["➕ Incluir", "📋 Cadastradas"])
        df_an = get_contas_analiticas()
        with r1:
            if df_an.empty:
                st.warning("Cadastre primeiro uma Conta Analítica.")
            else:
                man = dict(zip(df_an["caminho_completo"], df_an["id"]))
                with st.form("f_inc_regra", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    ptxt = c1.text_input("Palavra-Chave / Padrão de Texto (ex: copasa, cemig)")
                    an_s = c2.selectbox("Classificação Analítica", list(man.keys()))
                    it_an = df_an[df_an["id"] == man[an_s]].iloc[0]
                    if st.form_submit_button("Salvar Regra") and ptxt.strip():
                        if add_regra_classificacao(ptxt.strip(), it_an["tipo"], it_an["sintetica_id"], it_an["id"]):
                            st.success("Regra cadastrada!")
                            st.rerun()
        with r2:
            df_rg = get_regras_classificacao()
            if df_rg.empty:
                st.info("Nenhuma regra cadastrada.")
            else:
                st.dataframe(df_rg[["id", "padrao_texto", "tipo", "categoria", "subcategoria"]], use_container_width=True)
                mrg = {f"'{r['padrao_texto']}' ➔ {r['subcategoria']}": r['id'] for _, r in df_rg.iterrows()}
                drg = mrg[st.selectbox("Excluir Regra", list(mrg.keys()))]
                if st.button("🗑️ Excluir Regra", type="primary"):
                    delete_regra_classificacao(drg)
                    st.success("Excluído!")
                    st.rerun()

# ====================================================
# MÓDULO 5: USUÁRIOS
# ====================================================
elif chave_modulo_ativo == "usuarios":
    st.title("👥 Gestão de Usuários")
    u_ls, u_nc, u_ed, u_sn = st.tabs(["📋 Cadastrados", "➕ Novo Usuário", "✏️ Alterar / Excluir", "🔑 Minha Senha"])
    
    with u_ls:
        st.dataframe(get_usuarios(), use_container_width=True)
    with u_nc:
        with st.form("f_new_user", clear_on_submit=True):
            c1, c2 = st.columns(2)
            unome = c1.text_input("Nome Completo")
            uemail = c2.text_input("E-mail")
            usenha = c1.text_input("Senha", type="password")
            uperfil = c2.selectbox("Perfil", ["Administrador", "Advogado", "Assistente"])
            if st.form_submit_button("Cadastrar") and unome.strip() and uemail.strip() and usenha.strip():
                if add_usuario(unome, uemail, usenha, uperfil):
                    st.success("Usuário cadastrado!")
                    st.rerun()
                else:
                    st.error("E-mail já existente.")
    with u_ed:
        df_u = get_usuarios()
        if not df_u.empty:
            mu = dict(zip(df_u["nome"], df_u["id"]))
            su = st.selectbox("Selecione", list(mu.keys()))
            it_u = df_u[df_u["id"] == mu[su]].iloc[0]
            with st.form("f_ed_user"):
                c1, c2 = st.columns(2)
                enome = c1.text_input("Nome", value=it_u["nome"])
                eemail = c2.text_input("E-mail", value=it_u["email"])
                eperfil = c1.selectbox("Perfil", ["Administrador", "Advogado", "Assistente"], index=["Administrador", "Advogado", "Assistente"].index(it_u["perfil"]))
                esenha = c2.text_input("Nova Senha (Opcional)", type="password")
                eativo = c1.checkbox("Ativo", value=bool(it_u["ativo"]))
                if st.form_submit_button("Salvar Alterações"):
                    update_usuario(it_u["id"], enome, eemail, eperfil, 1 if eativo else 0, esenha)
                    st.success("Atualizado!")
                    st.rerun()
            if st.button("🗑️ Excluir Usuário", type="secondary"):
                if it_u["id"] == operador_atual_id:
                    st.error("Não é possível excluir o próprio usuário logado.")
                else:
                    delete_usuario(it_u["id"])
                    st.success("Excluído!")
                    st.rerun()
    with u_sn:
        st.subheader("Alterar Minha Senha")
        with st.form("f_minha_senha"):
            s_at = st.text_input("Senha Atual", type="password")
            s_nv = st.text_input("Nova Senha", type="password")
            s_cf = st.text_input("Confirmar Senha", type="password")
            if st.form_submit_button("Alterar Senha"):
                if not autenticar_usuario(usuario_logado["email"], s_at):
                    st.error("Senha atual incorreta.")
                elif s_nv != s_cf or len(s_nv) < 4:
                    st.warning("Confirmação incorreta ou senha com menos de 4 caracteres.")
                else:
                    alterar_senha_usuario(operador_atual_id, s_nv)
                    st.success("Senha alterada com sucesso!")
