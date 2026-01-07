import streamlit as st
from sqlalchemy.orm import Session
from passlib.hash import pbkdf2_sha256 # Use o mesmo do cadastro

def verificar_senha(senha_pura, senha_hash):
    try:
        return pbkdf2_sha256.verify(senha_pura, senha_hash)
    except:
        return False

def autenticar_usuario(db: Session, email, senha):
    from estagiario_app import Administrador 
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