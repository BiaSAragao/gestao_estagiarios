import streamlit as st
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from passlib.hash import pbkdf2_sha256

Base = declarative_base()

# Definimos o Administrador aqui para evitar o erro de importação circular
class Administrador(Base):
    __tablename__ = "administrador"
    id_adm = Column(Integer, primary_key=True)
    nome = Column(String(150))
    email = Column(String(150), unique=True)
    senha_hash = Column(String(255))

def verificar_senha(senha_pura, senha_hash):
    try:
        return pbkdf2_sha256.verify(senha_pura, senha_hash)
    except:
        return False

def autenticar_usuario(db: Session, email, senha):
    # Agora ele busca a classe que está neste mesmo arquivo
    adm = db.query(Administrador).filter(Administrador.email == email).first()
    if adm and verificar_senha(senha, adm.senha_hash):
        return adm
    return None

def render_login(db_session):
    st.title("🔐 Acesso Restrito")
    with st.form("login_form"):
        email = st.text_input("E-mail")
        senha = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar", use_container_width=True):
            usuario = autenticar_usuario(db_session, email, senha)
            if usuario:
                st.session_state["autenticado"] = True
                st.session_state["usuario_nome"] = usuario.nome
                st.rerun()
            else:
                st.error("Credenciais inválidas")
