from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
import os
import pandas as pd
import streamlit as st
import re
from sqlalchemy import create_engine, Column, Integer, String, Date, Text, ForeignKey, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, scoped_session

# ---------------------------
# Config / DB
# ---------------------------

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    st.error("Defina a variável de ambiente DATABASE_URL.")
    st.stop()

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False))
Base = declarative_base()

# ---------------------------
# Upload de Termos de Compromisso
# ---------------------------

UPLOAD_DIR = "uploads/termos"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# Função para compatibilidade com o bloco de relatório obrigatório
def session():
    return SessionLocal()

# ---------------------------
# Models
# ---------------------------

class Estagiario(Base):
    __tablename__ = "estagiarios"
    id_estagiario = Column(Integer, primary_key=True)
    nome = Column(String(150), nullable=False)
    curso = Column(String(150), nullable=True)
    semestre = Column(String(20), nullable=True)
    lotacao = Column(String(100), nullable=True)
    supervisor = Column(String(150), nullable=True)
    turno = Column(String(20), nullable=True)
    status = Column(String(10), nullable=False, default="Ativo")


    contratos = relationship("Contrato", back_populates="estagiario", cascade="all, delete-orphan")
    ferias = relationship("Ferias", back_populates="estagiario", cascade="all, delete-orphan")

class Contrato(Base):
    __tablename__ = "contrato"
    id_contrato = Column(Integer, primary_key=True)
    id_estagiario = Column(Integer, ForeignKey("estagiarios.id_estagiario", ondelete="CASCADE"), nullable=False)
    data_inicio = Column(Date, nullable=False)
    data_termino = Column(Date, nullable=False)
    status = Column(String(20), nullable=True)
    substituindo = Column(String(120), nullable=True)
    obs = Column(Text, nullable=True)
    tipo_contrato = Column(String(20), nullable=True)
    id_contrato_anterior = Column(Integer, ForeignKey("contrato.id_contrato"), nullable=True)

    estagiario = relationship("Estagiario", back_populates="contratos")

class Ferias(Base):
    __tablename__ = "ferias"
    id_ferias = Column(Integer, primary_key=True)
    id_estagiario = Column(Integer, ForeignKey("estagiarios.id_estagiario", ondelete="CASCADE"), nullable=False)
    periodo_inicio = Column(Date, nullable=False)
    periodo_fim = Column(Date, nullable=False)
    dias_usufruidos = Column(String(50), nullable=True)
    memorando = Column(String(100), nullable=True)

    estagiario = relationship("Estagiario", back_populates="ferias")

class TermoCompromisso(Base):
    __tablename__ = "termos_compromisso"

    id_termo = Column(Integer, primary_key=True)
    id_contrato = Column(Integer, ForeignKey("contrato.id_contrato", ondelete="CASCADE"), nullable=False)

    nome_arquivo = Column(String(255), nullable=False)
    caminho_arquivo = Column(Text, nullable=False)
    mime_type = Column(String(100))
    tamanho_arquivo = Column(Integer)

    data_upload = Column(Date, default=date.today)

    contrato = relationship("Contrato")

Base.metadata.create_all(bind=engine)

# ---------------------------
# Funções auxiliares
# ---------------------------

def dias_usufruidos_total(db_session, id_estagiario: int) -> float:
    ferias_list = db_session.query(Ferias).filter(Ferias.id_estagiario == id_estagiario).all()
    soma = 0.0
    for f in ferias_list:
        if f.dias_usufruidos:
            m = re.search(r"(\d+)", str(f.dias_usufruidos))
            if m:
                soma += float(m.group(1))
    return soma

# ---------------------------
# Streamlit UI
# ---------------------------

st.set_page_config(page_title="Gestão Estagiários", layout="wide")

menu = st.sidebar.selectbox(
    "Menu",
    ["Dashboard", "Estagiários", "Contratos", "Férias", "Cálculo de Férias", "Termos de Compromisso"],
    index=["Dashboard", "Estagiários", "Contratos", "Férias", "Cálculo de Férias", "Termos de Compromisso"]
    .index(st.session_state.get("menu", "Dashboard"))
)


db = SessionLocal()

# ---------------------------
# DASHBOARD
# ---------------------------
if menu == "Dashboard":
    st.title("📊 Dashboard de Controle")
    
    # MÉTRICAS PRINCIPAIS
    # Estagiário ativo = aquele que possui pelo menos um contrato que NÃO está encerrado
    ativos_count = db.query(Estagiario).join(Contrato).filter(Contrato.status != "encerrado").distinct().count()
    total_contratos = db.query(Contrato).count()

    c1, c2 = st.columns(2)
    c1.metric("Estagiários Ativos", ativos_count)
    c2.metric("Contratos Totais", total_contratos)

    st.divider()

    # SEÇÃO DE ALERTAS E VENCIMENTOS
    col_venc, col_ferias = st.columns(2)

    with col_venc:
        st.subheader("📅 Contratos a Vencer")
        prazo = st.radio("Período:", ["1 semana", "30 dias", "60 dias"], horizontal=True)
        dias_map = {"1 semana": 7, "30 dias": 30, "60 dias": 60}
        data_limite = date.today() + timedelta(days=dias_map[prazo])
        
        vencendo = db.query(Contrato).join(Estagiario).filter(
            Contrato.status != "Encerrado", # Apenas os que ainda estão ativos
            Contrato.data_termino >= date.today(),
            Contrato.data_termino <= data_limite
        ).all()

        if vencendo:
            st.dataframe(pd.DataFrame([{
                "Estagiário": c.estagiario.nome,
                "Vencimento": c.data_termino,
                "Dias Restantes": (c.data_termino - date.today()).days
            } for c in vencendo]), use_container_width=True)
        else:
            st.info("Nenhum contrato vencendo no período selecionado.")

    with col_ferias:
        st.subheader("🏖️ Estagiários em Férias")
        hoje = date.today()
        em_ferias = db.query(Ferias).join(Estagiario).filter(
            Ferias.periodo_inicio <= hoje,
            Ferias.periodo_fim >= hoje
        ).all()

        if em_ferias:
            st.table(pd.DataFrame([{
                "Nome": f.estagiario.nome,
                "Retorno": f.periodo_fim,
                "Dias para voltar": (f.periodo_fim - hoje).days
            } for f in em_ferias]))
        else:
            st.write("Não há estagiários em férias no momento.")

    # NOVO BLOCO: CICLO CONCLUÍDO (4 CONTRATOS ENCERRADOS)
    st.divider()
    
    # Subquery para contar contratos por estagiário
    count_subquery = db.query(
        Contrato.id_estagiario, 
        func.count(Contrato.id_contrato).label('total')
    ).group_by(Contrato.id_estagiario).subquery()

    # Busca estagiários que:
    # 1. Têm 4 ou mais contratos
    # 2. Nenhum desses contratos está ativo (todos encerrados)
    concluidos = db.query(Estagiario).join(count_subquery, Estagiario.id_estagiario == count_subquery.c.id_estagiario).filter(
        count_subquery.c.total >= 4,
        ~Estagiario.contratos.any(Contrato.status != "encerrado")
    ).all()

    if concluidos:
        st.subheader("🎓 Ciclo de Estágio Concluído")
        for est in concluidos:
            st.success(f"✨ **{est.nome}** finalizou sua jornada! Este estagiário completou todos os 4 períodos de contrato permitidos e todos constam como encerrados no sistema.")

# ---------------------------
# ESTAGIÁRIOS
# ---------------------------
elif menu == "Estagiários":
    st.header("Gestão de Estagiários")
    aba1, aba2 = st.tabs(["Cadastrar Novo", "Ver / Editar Tudo"])

    # =====================================================
    # ABA 1 — CADASTRO
    # =====================================================
    with aba1:
        with st.form("add_est", clear_on_submit=True):
            nome = st.text_input("Nome completo", key="est_nome")
            curso = st.text_input("Curso", key="est_curso")
            semestre = st.text_input("Semestre", key="est_semestre")
            lotacao = st.text_input("Lotação", key="est_lotacao")
            supervisor = st.text_input("Supervisor", key="est_supervisor")
            turno = st.selectbox(
                "Turno",
                ["Manhã", "Tarde", "Integral"],
                key="est_turno"
            )

            submit = st.form_submit_button("Salvar Estagiário")

        if submit:
            novo = Estagiario(
                nome=nome,
                curso=curso,
                semestre=semestre,
                lotacao=lotacao,
                supervisor=supervisor,
                turno=turno,
                status="Ativo"   # 🔹 já nasce ativo
            )
            db.add(novo)
            db.commit()

            st.success("✅ Estagiário cadastrado com sucesso!")

            # Limpa campos manualmente (garantia extra)
            for k in [
                "est_nome", "est_curso", "est_semestre",
                "est_lotacao", "est_supervisor", "est_turno"
            ]:
                if k in st.session_state:
                    del st.session_state[k]

    # =====================================================
    # ABA 2 — VER / EDITAR
    # =====================================================
    with aba2:
        lista_est = db.query(Estagiario).order_by(Estagiario.nome).all()

        if not lista_est:
            st.info("Nenhum estagiário cadastrado.")
        else:
            st.subheader("📋 Lista de Estagiários")

            for e in lista_est:
                with st.container():
                    col1, col2, col3 = st.columns([6, 2, 2])

                    # -------- COLUNA 1 — DADOS COMPLETOS --------
                    col1.markdown(
                        f"""
                        **{e.nome}**  
                        📘 Curso: {e.curso or "-"}  
                        🎓 Semestre: {e.semestre or "-"}  
                        🏢 Lotação: {e.lotacao or "-"}  
                        👤 Supervisor: {e.supervisor or "-"}  
                        ⏰ Turno: {e.turno or "-"}
                        """
                    )

                    # -------- COLUNA 2 — STATUS --------
                    if e.status == "Ativo":
                        col2.success("🟢 Ativo")
                    else:
                        col2.error("🔴 Inativo")

                    # -------- COLUNA 3 — BOTÃO --------
                    if e.status == "Ativo":
                        if col3.button(
                            "Desativar",
                            key=f"desativar_{e.id_estagiario}"
                        ):
                            e.status = "Inativo"
                            db.commit()
                            st.rerun()
                    else:
                        if col3.button(
                            "Ativar",
                            key=f"ativar_{e.id_estagiario}"
                        ):
                            e.status = "Ativo"
                            db.commit()
                            st.rerun()

                    st.divider()



            # ----- EDIÇÃO COMPLETA -----
            st.subheader("✏️ Editar Informações")

            selected_est = st.selectbox(
                "Selecione para editar",
                [""] + [f"{e.id_estagiario} - {e.nome}" for e in lista_est]
            )

            if selected_est:
                est_id = int(selected_est.split(" - ")[0])
                est_obj = db.get(Estagiario, est_id)

                with st.form(f"edit_est_{est_id}"):
                    col1, col2 = st.columns(2)

                    new_nome = col1.text_input("Nome", est_obj.nome)
                    new_curso = col2.text_input("Curso", est_obj.curso)
                    new_sem = col1.text_input("Semestre", est_obj.semestre)
                    new_lot = col2.text_input("Lotação", est_obj.lotacao)
                    new_sup = col1.text_input("Supervisor", est_obj.supervisor)
                    new_turno = col2.selectbox(
                        "Turno",
                        ["Manhã", "Tarde", "Integral"],
                        index=["Manhã", "Tarde", "Integral"].index(est_obj.turno)
                        if est_obj.turno in ["Manhã", "Tarde", "Integral"] else 0
                    )

                    if st.form_submit_button("Atualizar Cadastro"):
                        est_obj.nome = new_nome
                        est_obj.curso = new_curso
                        est_obj.semestre = new_sem
                        est_obj.lotacao = new_lot
                        est_obj.supervisor = new_sup
                        est_obj.turno = new_turno
                        db.commit()

                        st.success("✅ Dados atualizados com sucesso!")
                        st.rerun()

# ---------------------------
# CONTRATOS
# ---------------------------
elif menu == "Contratos":
    st.header("Gestão de Contratos")
    aba1, aba2 = st.tabs(["Novo Contrato", "Ver / Editar Tudo"])

    estagiarios = db.query(Estagiario).all()
    est_dict = {f"{e.nome} (ID: {e.id_estagiario})": e.id_estagiario for e in estagiarios}

    # ---------------------------
    # NOVO CONTRATO
    # ---------------------------
    with aba1:
        if not estagiarios:
            st.warning("Cadastre um estagiário primeiro.")
        else:
            with st.form("add_ct", clear_on_submit=True):
                nome_sel = st.selectbox("Estagiário", options=list(est_dict.keys()))
                inicio = st.date_input("Início", date.today())
                fim = st.date_input("Término", date.today() + relativedelta(months=6))
                subst = st.text_input("Substituindo")
                tipo = st.selectbox("Tipo", ["inicial", "renovacao"])
                status_c = st.selectbox("Status", ["Ativo", "Encerrado", "Suspenso"])
                obs = st.text_area("Observações")

                submit_ct = st.form_submit_button("Gerar Contrato")

            if submit_ct:
                novo_c = Contrato(
                    id_estagiario=est_dict[nome_sel],
                    data_inicio=inicio,
                    data_termino=fim,
                    substituindo=subst,
                    obs=obs,
                    tipo_contrato=tipo,
                    status=status_c
                )
                db.add(novo_c)
                db.commit()

                st.success("✅ Contrato cadastrado com sucesso!")

    # ---------------------------
    # VER / EDITAR CONTRATOS
    # ---------------------------
    with aba2:
        contratos = db.query(Contrato).join(Estagiario).all()

        if contratos:
            df_c = pd.DataFrame([{
                "ID": c.id_contrato,
                "Estagiário": c.estagiario.nome,
                "Início": c.data_inicio,
                "Fim": c.data_termino,
                "Status": c.status
            } for c in contratos])

            st.dataframe(df_c, use_container_width=True)

            st.divider()
            ct_sel = st.selectbox(
                "Selecione Contrato para Editar",
                [""] + [f"ID {c.id_contrato} - {c.estagiario.nome}" for c in contratos]
            )

            if ct_sel:
                c_id = int(re.search(r"ID (\d+)", ct_sel).group(1))
                c_obj = db.get(Contrato, c_id)

                with st.form(f"edit_ct_{c_id}"):
                    c1, c2 = st.columns(2)
                    n_ini = c1.date_input("Data Início", c_obj.data_inicio)
                    n_fim = c2.date_input("Data Término", c_obj.data_termino)
                    n_sub = c1.text_input("Substituindo", c_obj.substituindo)
                    n_tipo = c2.selectbox(
                        "Tipo",
                        ["inicial", "renovacao"],
                        index=0 if c_obj.tipo_contrato == "inicial" else 1
                    )
                    n_status = c1.selectbox(
                        "Status",
                        ["Ativo", "Encerrado", "Suspenso"],
                        index=["Ativo", "Encerrado", "Suspenso"].index(c_obj.status)
                        if c_obj.status in ["Ativo", "Encerrado", "Suspenso"] else 0
                    )
                    n_obs = st.text_area("Observações", c_obj.obs)

                    if st.form_submit_button("Salvar Alterações do Contrato"):
                        c_obj.data_inicio = n_ini
                        c_obj.data_termino = n_fim
                        c_obj.substituindo = n_sub
                        c_obj.tipo_contrato = n_tipo
                        c_obj.status = n_status
                        c_obj.obs = n_obs
                        db.commit()

                        st.success("✅ Contrato atualizado com sucesso!")
                        st.rerun()

# ---------------------------
# FÉRIAS
# ---------------------------
elif menu == "Férias":
    st.header("Registro de Férias")

    db = SessionLocal()

    # ---------------------------------
    # PRÉ-PREENCHIMENTO VINDO DO CÁLCULO
    # ---------------------------------
    prefill = st.session_state.get("ferias_prefill")

    if prefill:
        est_id_prefill = prefill["id_estagiario"]
        data_ini_prefill = prefill["data_inicio"]
        data_fim_prefill = prefill["data_fim"]
        dias_prefill = prefill["dias"]
    else:
        est_id_prefill = None
        data_ini_prefill = date.today()
        data_fim_prefill = date.today()
        dias_prefill = 0

    # -----------------------------
    # SELEÇÃO DO ESTAGIÁRIO
    # -----------------------------
    estagiarios = db.query(Estagiario).order_by(Estagiario.nome).all()

    est_dict = {f"{e.id_estagiario} - {e.nome}": e.id_estagiario for e in estagiarios}

    est_sel = st.selectbox(
        "Selecione o estagiário",
        [""] + list(est_dict.keys()),
        index=list(est_dict.values()).index(est_id_prefill) + 1 if est_id_prefill else 0
    )

    if est_sel:
        est_id = est_dict[est_sel]

        st.divider()

        # -----------------------------
        # FORMULÁRIO DE FÉRIAS
        # -----------------------------
        col1, col2 = st.columns(2)

        with col1:
            data_inicio = st.date_input(
                "Data de início das férias",
                value=data_ini_prefill
            )

        with col2:
            data_fim = st.date_input(
                "Data de fim das férias",
                value=data_fim_prefill
            )

        # Cálculo automático dos dias
        dias_calculados = (data_fim - data_inicio).days + 1

        dias_usufruidos = st.number_input(
            "Dias de férias",
            min_value=1,
            value=dias_calculados if dias_prefill == 0 else dias_prefill,
            step=1
        )

        memorando = st.text_input("Memorando / Observação")

        # -----------------------------
        # SALVAR FÉRIAS
        # -----------------------------
        if st.button("💾 Registrar Férias"):
            if data_fim < data_inicio:
                st.error("❌ A data final não pode ser anterior à data inicial.")
            else:
                nova_ferias = Ferias(
                    id_estagiario=est_id,
                    periodo_inicio=data_inicio,
                    periodo_fim=data_fim,
                    dias_usufruidos=dias_usufruidos,
                    memorando=memorando
                )

                db.add(nova_ferias)
                db.commit()

                st.success("✅ Férias registradas com sucesso!")

                # LIMPA O PREFILL PARA NÃO REUTILIZAR
                if "ferias_prefill" in st.session_state:
                    del st.session_state["ferias_prefill"]

                st.rerun()

    db.close()

# ---------------------------
# CÁLCULO DE FÉRIAS

elif menu == "Cálculo de Férias":

    st.header("Cálculo de Férias")
    st.subheader("Calcular férias proporcionais (selecionando contratos)")

    db = SessionLocal()

    # 1) Pesquisar estagiário pelo nome
    nome_busca = st.text_input("Pesquisar estagiário por nome (parcial)")

    if nome_busca:
        ests = db.query(Estagiario).filter(
            Estagiario.nome.ilike(f"%{nome_busca}%")
        ).all()

        if not ests:
            st.warning("Nenhum estagiário encontrado.")
        else:
            nomes_dict = {f"{e.id_estagiario} - {e.nome}": e.id_estagiario for e in ests}
            escolha = st.selectbox("Selecione o estagiário", [""] + list(nomes_dict.keys()))

            if escolha:
                est_id = nomes_dict[escolha]

                # 2) Contratos do estagiário
                contratos = db.query(Contrato).filter(
                    Contrato.id_estagiario == est_id
                ).order_by(Contrato.data_inicio).all()

                if not contratos:
                    st.error("Este estagiário não possui contratos cadastrados.")
                else:
                    st.write("Selecione os contratos que farão parte do cálculo:")

                    marcados = []
                    for c in contratos:
                        label = f"ID {c.id_contrato} | {c.data_inicio} → {c.data_termino}"
                        if st.checkbox(label, key=f"calc_ctr_{c.id_contrato}"):
                            marcados.append(c)

                    if marcados:

                        # Data inicial do cálculo
                        data_ini = min(c.data_inicio for c in marcados)

                        # Data final padrão (maior término)
                        data_contrato_fim = max(c.data_termino for c in marcados)

                        hoje = date.today()

                        # ---------------------------------
                        # MODO DE CÁLCULO
                        # ---------------------------------
                        st.subheader("Modo de cálculo")

                        modo = st.radio(
                            "Selecione o tipo de cálculo:",
                            (
                                "Direito adquirido (até hoje)",
                                "Projeção até o fim do contrato",
                                "Informar data manualmente"
                            )
                        )

                        if modo == "Direito adquirido (até hoje)":
                            data_fim = hoje
                            st.info("Cálculo considera apenas o tempo já trabalhado.")

                        elif modo == "Projeção até o fim do contrato":
                            data_fim = data_contrato_fim
                            st.warning(
                                "⚠️ Este é um cálculo de PROJEÇÃO. "
                                "O direito só será adquirido se o contrato for cumprido até esta data."
                            )

                        else:
                            data_fim = st.date_input(
                                "Informe a data final desejada",
                                value=hoje
                            )
                            st.warning("⚠️ Cálculo realizado com data informada manualmente.")

                        # -------------------------------
                        # VERIFICAÇÃO
                        # -------------------------------
                        if data_fim < data_ini:
                            st.error("A data final não pode ser anterior à data inicial.")
                        else:
                            # -------------------------------
                            # CÁLCULO PROPORCIONAL
                            # -------------------------------
                            dias_totais = (data_fim - data_ini).days + 1
                            meses_equivalentes = dias_totais / 30
                            direito_ferias = meses_equivalentes * 2.5

                            # Arredondamento conforme norma administrativa
                            dias_ferias_int = int(round(direito_ferias))

                            # Exibição
                            st.success("Resultado do cálculo:")
                            st.write(f"📌 **Período considerado:** {data_ini} → {data_fim}")
                            st.write(f"📌 **Dias totais considerados:** {dias_totais} dias")
                            st.write(f"📌 **Meses equivalentes:** {meses_equivalentes:.2f}")
                            st.write(f"🏖️ **Direito a férias:** **{dias_ferias_int} dias**")

                            # -------------------------------
                            # REDIRECIONAR PARA FÉRIAS
                            # -------------------------------
                            st.divider()
                            st.subheader("Registrar férias com base neste cálculo")

                            if st.button("➡️ Ir para Registro de Férias"):
                                data_inicio_ferias = data_fim + timedelta(days=1)
                                data_fim_ferias = data_inicio_ferias + timedelta(days=dias_ferias_int - 1)

                                st.session_state["ferias_prefill"] = {
                                    "id_estagiario": est_id,
                                    "data_inicio": data_inicio_ferias,
                                    "data_fim": data_fim_ferias,
                                    "dias": dias_ferias_int
                                }

                                st.session_state["menu"] = "Férias"
                                st.rerun()

                    else:
                        st.info("Selecione ao menos um contrato para realizar o cálculo.")

    db.close()

# ---------------------------
# TERMOS DE COMPROMISSO
# ---------------------------
elif menu == "Termos de Compromisso":

    st.header("📄 Gestão de Termos de Compromisso")

    db = SessionLocal()

    # ---------------------------------
    # SELEÇÃO DO ESTAGIÁRIO
    # ---------------------------------
    estagiarios = db.query(Estagiario).order_by(Estagiario.nome).all()

    est_dict = {
        f"{e.id_estagiario} - {e.nome}": e.id_estagiario
        for e in estagiarios
    }

    est_sel = st.selectbox(
        "Selecione o estagiário",
        [""] + list(est_dict.keys())
    )

    if est_sel:
        est_id = est_dict[est_sel]

        # ---------------------------------
        # LISTAR CONTRATOS DO ESTAGIÁRIO
        # ---------------------------------
        contratos = db.query(Contrato).filter(
            Contrato.id_estagiario == est_id
        ).order_by(Contrato.data_inicio).all()

        if not contratos:
            st.warning("Este estagiário não possui contratos.")
        else:
            contrato_dict = {
                f"ID {c.id_contrato} | {c.data_inicio} → {c.data_termino}": c.id_contrato
                for c in contratos
            }

            ct_sel = st.selectbox(
                "Selecione o contrato",
                [""] + list(contrato_dict.keys())
            )

            if ct_sel:
                c_id = contrato_dict[ct_sel]

                st.divider()
                st.subheader("Termo de Compromisso")

                termo = db.query(TermoCompromisso).filter(
                    TermoCompromisso.id_contrato == c_id
                ).first()

                # ---------------------------------
                # SE JÁ EXISTE TERMO
                # ---------------------------------
                
                if termo:
                    st.success("✅ Termo de compromisso cadastrado")
                    st.write(f"📄 Arquivo: **{termo.nome_arquivo}**")

                    with open(termo.caminho_arquivo, "rb") as f:
                        st.download_button(
                            "⬇️ Baixar Termo de Compromisso",
                            data=f,
                            file_name=termo.nome_arquivo,
                            mime=termo.mime_type
                        )

                    st.divider()

                    if st.button("🔄 Substituir Termo"):
                        st.session_state["substituir_termo"] = True

                # ---------------------------------
                # UPLOAD DO TERMO
                # ---------------------------------
                if not termo or st.session_state.get("substituir_termo"):

                    arquivo = st.file_uploader(
                        "Enviar Termo de Compromisso (PDF)",
                        type=["pdf"]
                    )

                    if arquivo and st.button("💾 Salvar Termo"):
                        caminho = os.path.join(
                            UPLOAD_DIR,
                            f"contrato_{c_id}_{arquivo.name}"
                        )

                        with open(caminho, "wb") as f:
                            f.write(arquivo.read())

                        if termo:
                            # Atualiza
                            termo.nome_arquivo = arquivo.name
                            termo.caminho_arquivo = caminho
                            termo.mime_type = arquivo.type
                            termo.tamanho_arquivo = len(arquivo.getbuffer())
                            termo.data_upload = date.today()
                        else:
                            # Cria novo
                            novo = TermoCompromisso(
                                id_contrato=c_id,
                                nome_arquivo=arquivo.name,
                                caminho_arquivo=caminho,
                                mime_type=arquivo.type,
                                tamanho_arquivo=len(arquivo.getbuffer())
                            )
                            db.add(novo)

                        db.commit()

                        st.success("📄 Termo salvo com sucesso!")
                        st.session_state.pop("substituir_termo", None)
                        st.rerun()

    db.close()
