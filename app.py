# app.py
# Interface Streamlit do CertChain UEA — registrar, consultar e visualizar a blockchain.
# Executar: streamlit run app.py
#
# Princípio da interface: TODAS as operações ficam visíveis para todos os papéis.
# Quem decide se a operação é permitida é o CONTRATO INTELIGENTE (contrato.py),
# e a rejeição aparece na tela com a regra violada (ex.: E1, V3, A1).
import json
import os
from datetime import date, datetime

import pandas as pd
import streamlit as st

from contrato import (ATIVO, AUTORIZAR_EMISSOR, EMITIR_CERTIFICADO, REMOVER_EMISSOR,
                      REVOGAR_CERTIFICADO, hash_arquivo, hash_titular)
from diploma import gerar_diploma_pdf
from no import CONTAS_PADRAO, No

PASTA_DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")
PASTA_DIPLOMAS = os.path.join(PASTA_DADOS, "diplomas")  # PDFs ficam FORA da blockchain

st.set_page_config(page_title="CertChain UEA", page_icon="🎓", layout="wide")


@st.cache_resource
def obter_no():
    """Um único nó local por execução do servidor (compartilhado entre as sessões)."""
    return No(PASTA_DADOS, dificuldade=4)


no = obter_no()

st.session_state.setdefault("carteira_autenticada", None)
st.session_state.setdefault("resultado", None)
st.session_state.setdefault("tela", "login")  # "login" ou "verificar" (sem login)
st.session_state.setdefault("aviso", None)

COR_PAPEL = {"ADMINISTRADOR": "blue", "EMISSOR": "green"}
PERMISSOES = {
    "ADMINISTRADOR": "✅ Autorizar e remover emissores  \n✅ Revogar qualquer diploma  \n"
                     "❌ Emitir diplomas (separação de funções)",
    "EMISSOR": "✅ Emitir diplomas  \n✅ Revogar os diplomas que emitiu  \n❌ Gerenciar emissores",
}
PERMISSOES_PADRAO = ("✅ Verificar e baixar os próprios diplomas  \n"
                     "❌ Emitir, revogar ou gerenciar emissores — o contrato rejeita")


# ------------------------------------------------------------------ utilidades
def logado():
    return st.session_state["carteira_autenticada"]


def sair():
    if logado() is not None:
        logado().bloquear()
    st.session_state["carteira_autenticada"] = None
    st.session_state["resultado"] = None


def nome_conta(endereco):
    c = no.carteira(endereco)
    return c.nome if c else (endereco[:10] + "…" if endereco else "—")


def quando(ts):
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S")


def caminho_diploma(codigo):
    return os.path.join(PASTA_DIPLOMAS, f"{codigo}.pdf")


def aplicar_estilo():
    st.markdown("""
        <style>
        [data-testid="stMetric"] {
            border: 1px solid rgba(148, 163, 184, 0.25);
            border-radius: 0.8rem;
            padding: 0.6rem 0.9rem;
        }
        .block-container { padding-top: 2rem; }
        </style>""", unsafe_allow_html=True)


def metricas_cadeia():
    valida, idx, _ = no.cadeia.validate()
    a, b, c, d = st.columns(4)
    a.metric("Blocos na cadeia", len(no.cadeia.blocks))
    b.metric("Diplomas registrados", len(no.contrato.certificados))
    c.metric("Prova de trabalho", f"{no.cadeia.difficulty} zeros")
    d.metric("Integridade", "Íntegra ✅" if valida else f"Corrompida ❌ #{idx}")


def mostrar_resultado(r):
    if r["ok"]:
        b = r["bloco"]
        st.success(f"✅ Transação aceita pelo contrato e minerada no **bloco #{b['index']}** "
                   f"(nonce {b['nonce']:,}, {r['tempo_mineracao']:.2f}s)".replace(",", "."))
        st.code(f"hash:          {b['hash']}\nhash anterior: {b['previous_hash']}", language=None)
    else:
        st.error(f"❌ Transação **rejeitada** pelo contrato — regra **{r['regra']}**: {r['erro']}\n\n"
                 "Nenhum bloco foi criado.")


def enviar(chave, tipo, payload, pdf=None):
    """Assina com a carteira desta sessão, submete ao nó e recarrega a página.
    Se a emissão for aceita, guarda o PDF do diploma fora da blockchain."""
    r = no.enviar(logado(), tipo, payload)
    diploma = None
    if r["ok"] and pdf is not None:
        os.makedirs(PASTA_DIPLOMAS, exist_ok=True)
        with open(caminho_diploma(payload["codigo"]), "wb") as f:
            f.write(pdf)
        diploma = payload["codigo"]
    st.session_state["resultado"] = {"chave": chave, "r": r, "payload": payload, "diploma": diploma}
    st.rerun()


def exibir_resultado(chave):
    res = st.session_state.get("resultado")
    if not res or res["chave"] != chave:
        return
    mostrar_resultado(res["r"])
    if res.get("diploma"):
        botao_diploma(res["diploma"], f"res_{res['diploma']}", primario=True)
    with st.expander("O que foi enviado para a blockchain (payload da transação)"):
        st.json(res["payload"])
        if chave == "emitir":
            st.caption("Nome e matrícula do aluno não aparecem: só o hash do titular e o hash do PDF.")


def botao_diploma(codigo, chave, primario=False):
    caminho = caminho_diploma(codigo)
    if os.path.exists(caminho):
        with open(caminho, "rb") as f:
            st.download_button("⬇️ Baixar diploma (PDF)", f.read(), file_name=f"diploma_{codigo}.pdf",
                               mime="application/pdf", key=f"dl_{chave}",
                               type="primary" if primario else "secondary")


def cartao_certificado(c, chave):
    if c is None:
        st.error("❌ **Não encontrado.** Documento não registrado na blockchain ou adulterado.")
        return
    if c["status"] == ATIVO:
        st.success(f"✅ Diploma **AUTÊNTICO** e **ATIVO** — {c['codigo']}")
    else:
        rv = c["revogacao"]
        st.error(f"🚫 Diploma **REVOGADO** no bloco #{rv['bloco']} — motivo: {rv['motivo']}")
    st.markdown(f"**Curso:** {c['curso']}  \n"
                f"**Carga horária:** {c['carga_horaria']} h  \n"
                f"**Conclusão:** {date.fromisoformat(c['data_conclusao']).strftime('%d/%m/%Y')}  \n"
                f"**Instituição emissora:** {c['instituicao']}  \n"
                f"**Registrado no bloco:** #{c['emitido_no_bloco']} em {quando(c['emitido_em'])}  \n"
                f"**Hash do documento:** `{c['documento_hash']}`")
    with st.expander("Histórico na blockchain"):
        st.dataframe(pd.DataFrame([{"Bloco": h["bloco"], "Operação": h["operacao"], "Por": nome_conta(h["por"]),
                                    "Quando": quando(h["timestamp"])} for h in c["historico"]]),
                     hide_index=True, use_container_width=True)
    botao_diploma(c["codigo"], chave)


# ------------------------------------------------------------------ verificação (pública)
def secao_verificacao():
    """Consulta pública de diplomas (por PDF ou por código). Não cria transações."""
    st.subheader("Verificar diploma")
    st.caption("Qualquer pessoa pode verificar, sem conta e sem transação: a consulta só lê o estado do contrato.")
    col_pdf, col_cod = st.columns(2, gap="large")
    with col_pdf:
        with st.container(border=True):
            st.markdown("##### 📄 Pelo arquivo PDF")
            pdf_v = st.file_uploader("Arraste o diploma recebido", type=["pdf"], key="pdf_verificar")
            if pdf_v:
                h = hash_arquivo(pdf_v.getvalue())
                st.caption(f"SHA-256 calculado: `{h}`")
                cartao_certificado(no.contrato.verificar_documento(h), "ver_pdf")
    with col_cod:
        with st.container(border=True):
            st.markdown("##### 🔢 Pelo código")
            cod_v = st.text_input("Código impresso no diploma", placeholder="UEA-2026-0001")
            if cod_v:
                cert_v = no.contrato.consultar(cod_v.strip().upper())
                cartao_certificado(cert_v, "ver_cod")
                if cert_v:
                    with st.expander("Conferir titular (nome + matrícula)"):
                        n = st.text_input("Nome", key="tit_nome")
                        m = st.text_input("Matrícula", key="tit_mat")
                        if n and m:
                            if hash_titular(n, m) == cert_v["titular_hash"]:
                                st.success("Titular confere ✅")
                            else:
                                st.error("Titular NÃO confere ❌")

    st.markdown("##### Estado do contrato — diplomas registrados")
    if no.contrato.certificados:
        st.dataframe(pd.DataFrame([{
            "Código": c["codigo"], "Status": c["status"], "Curso": c["curso"],
            "Instituição": c["instituicao"], "Bloco": c["emitido_no_bloco"],
            "Hash do documento": c["documento_hash"][:16] + "…"} for c in no.contrato.certificados.values()]),
            hide_index=True, use_container_width=True)
    else:
        st.info("Nenhum diploma emitido ainda.")


# ------------------------------------------------------------------ telas sem login
def tela_login():
    st.title("🎓 CertChain UEA")
    st.caption("Diplomas da UEA registrados em uma blockchain local — autenticidade verificável por qualquer pessoa.")
    if st.session_state.get("aviso"):
        st.success(st.session_state.pop("aviso"))
    metricas_cadeia()
    st.write("")

    esquerda, direita = st.columns(2, gap="large")
    with esquerda:
        with st.container(border=True):
            st.subheader("🔐 Entrar")
            usuarios = no.listar_usuarios()
            mapa = {u["nome"]: u for u in usuarios}
            with st.form("login"):
                nome_usuario = st.selectbox("Conta", list(mapa),
                                            format_func=lambda n: f"{n} · {mapa[n]['papel']}")
                senha = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar", type="primary", use_container_width=True):
                    carteira = no.autenticar(mapa[nome_usuario]["endereco"], senha)
                    if carteira:
                        st.session_state["carteira_autenticada"] = carteira
                        st.session_state["resultado"] = None
                        st.rerun()
                    st.error("Senha incorreta.")
            with st.expander("👤 Sou aluno e ainda não tenho conta"):
                with st.form("cadastro_aluno", clear_on_submit=True):
                    nome_novo = st.text_input("Nome completo")
                    matricula_nova = st.text_input("Matrícula")
                    senha_nova = st.text_input("Senha", type="password")
                    if st.form_submit_button("Criar conta"):
                        if not nome_novo.strip() or not matricula_nova.strip() or not senha_nova.strip():
                            st.warning("Preencha nome, matrícula e senha.")
                        elif no.registrar_usuario(nome_novo, matricula_nova, senha_nova):
                            st.session_state["aviso"] = f"Conta criada para {nome_novo.strip()}. Já pode entrar."
                            st.rerun()
                        else:
                            st.warning("Já existe um aluno com esse nome e matrícula.")

    with direita:
        with st.container(border=True):
            st.subheader("🔎 Recebeu um diploma?")
            st.write("Confira se ele é autêntico **sem precisar de conta**: envie o PDF ou digite o código impresso.")
            if st.button("Verificar um diploma", use_container_width=True):
                st.session_state["tela"] = "verificar"
                st.rerun()
        with st.expander("🔑 Contas de demonstração"):
            st.dataframe(pd.DataFrame([{"Conta": nome, "Papel": no.contrato.papel(c.endereco), "Senha": senha}
                                       for c, (nome, senha) in zip(no.carteiras, CONTAS_PADRAO)]),
                         hide_index=True, use_container_width=True)
            st.caption("Senhas fixas apenas para a apresentação. Alunos cadastrados usam a senha que escolheram.")


def tela_verificacao_publica():
    st.title("🎓 CertChain UEA — Verificação pública")
    if st.button("← Voltar"):
        st.session_state["tela"] = "login"
        st.rerun()
    secao_verificacao()


# ------------------------------------------------------------------ abas do painel
def aba_meus_diplomas(conta, papel):
    st.subheader("Meus diplomas")
    usuario = next((u for u in no.usuarios if u.get("endereco") == conta and u.get("matricula")), None)
    if not usuario:
        st.info("Esta conta não é de aluno.")
        return
    titular = hash_titular(usuario["nome"], usuario["matricula"])
    meus = [c for c in no.contrato.certificados.values() if c["titular_hash"] == titular]
    st.caption("Localizados comparando o hash de nome + matrícula com o registrado na blockchain — "
               "seus dados pessoais não ficam na cadeia.")
    if not meus:
        st.info("Nenhum diploma registrado em seu nome ainda.")
    for c in meus:
        with st.container(border=True):
            cartao_certificado(c, f"meus_{c['codigo']}")


def aba_emitir(conta, papel):
    st.subheader("Emitir diploma")
    st.caption(f"A transação será assinada por **{nome_conta(conta)}** ({papel}). "
               "O PDF do diploma é gerado a partir dos dados; só o hash dele vai para a blockchain.")
    if papel != "EMISSOR":
        st.warning("Esta conta não é emissora: o contrato inteligente vai **rejeitar** a emissão (regra E1).")

    alunos = no.listar_alunos()
    opcoes = [f"{a['nome']} — {a['matricula']}" for a in alunos] + ["✍️ Outro aluno (digitar)"]
    with st.container(border=True):
        c1, c2 = st.columns(2)
        escolha = c1.selectbox("Aluno", opcoes, key="em_aluno")
        if escolha == opcoes[-1]:
            nome = c1.text_input("Nome completo do aluno", key="em_nome")
            matricula = c2.text_input("Matrícula", key="em_mat")
        else:
            aluno = alunos[opcoes.index(escolha)]
            nome, matricula = aluno["nome"], str(aluno["matricula"])
            c2.text_input("Matrícula", value=matricula, disabled=True, key=f"em_mat_{escolha}")
        curso = c1.text_input("Curso", value="Sistemas de Informação", key="em_curso")
        codigo = c2.text_input("Código do diploma", value=f"UEA-2026-{len(no.contrato.certificados) + 1:04d}",
                               key=f"em_cod_{len(no.contrato.certificados)}")
        carga = c1.number_input("Carga horária (h)", min_value=0, max_value=50000, value=3200, step=10,
                                key="em_carga")
        conclusao = c2.date_input("Data de conclusão", value=date.today(), min_value=date(1990, 1, 1),
                                  max_value=date(2100, 12, 31), format="DD/MM/YYYY", key="em_data")
        with st.expander("Usar um PDF próprio em vez do gerado (opcional)"):
            pdf_proprio = st.file_uploader("Diploma em PDF", type=["pdf"], key="em_pdf")

        if st.button("Registrar na blockchain e gerar diploma", type="primary"):
            if not nome.strip() or not matricula.strip():
                st.warning("Informe nome e matrícula do aluno.")
            else:
                cod = codigo.strip().upper()
                instituicao = no.contrato.emissores.get(conta, {}).get("nome", nome_conta(conta))
                pdf = (pdf_proprio.getvalue() if pdf_proprio else
                       gerar_diploma_pdf(nome.strip(), curso.strip(), int(carga), conclusao, cod, instituicao))
                payload = {
                    "codigo": cod,
                    "documento_hash": hash_arquivo(pdf),
                    "titular_hash": hash_titular(nome, matricula),
                    "curso": curso,
                    "carga_horaria": int(carga),
                    "data_conclusao": conclusao.isoformat(),
                }
                enviar("emitir", EMITIR_CERTIFICADO, payload, pdf=pdf)
    exibir_resultado("emitir")


def aba_verificar(conta, papel):
    secao_verificacao()


def aba_revogar(conta, papel):
    st.subheader("Revogar diploma")
    st.caption(f"A transação será assinada por **{nome_conta(conta)}** ({papel}). "
               "Só o emissor original ou o administrador podem revogar.")
    if papel not in ("EMISSOR", "ADMINISTRADOR"):
        st.warning("Esta conta não pode revogar: o contrato vai **rejeitar** (regra V3).")
    certs = no.contrato.certificados
    if not certs:
        st.info("Nenhum diploma emitido ainda.")
    else:
        with st.form("revogar"):
            cod_r = st.selectbox("Diploma", list(certs), format_func=lambda k: (
                f"{k} · {certs[k]['curso']} · {certs[k]['status']} · emitido por {nome_conta(certs[k]['emissor'])}"))
            motivo = st.text_area("Motivo da revogação")
            if st.form_submit_button("Revogar", type="primary"):
                enviar("revogar", REVOGAR_CERTIFICADO, {"codigo": cod_r, "motivo": motivo})
    exibir_resultado("revogar")


def aba_emissores(conta, papel):
    st.subheader("Emissores autorizados")
    st.caption(f"Administrador (definido no bloco gênesis): **{nome_conta(no.contrato.admin)}**. "
               "Emissores com bloco 0 foram definidos no próprio gênesis.")
    if papel != "ADMINISTRADOR":
        st.warning("Só o administrador gerencia emissores: o contrato vai **rejeitar** (regras A1/R1).")
    st.dataframe(pd.DataFrame([{
        "Instituição": e["nome"], "Conta": nome_conta(e["endereco"]), "Endereço": e["endereco"],
        "Ativo": "✅" if e["ativo"] else "❌", "Autorizado no bloco": e["autorizado_no_bloco"],
        "Removido no bloco": e["removido_no_bloco"]} for e in no.contrato.emissores.values()]),
        hide_index=True, use_container_width=True)
    opcoes = [c.endereco for c in no.carteiras]
    c1, c2 = st.columns(2)
    with c1.form("autorizar"):
        st.markdown("##### Autorizar emissor")
        alvo = st.selectbox("Conta", opcoes, format_func=nome_conta, key="alvo_aut")
        inst = st.text_input("Nome da instituição/setor", value="UEA — Escola Superior de Tecnologia")
        if st.form_submit_button("Autorizar", type="primary"):
            enviar("emissores", AUTORIZAR_EMISSOR, {"endereco": alvo, "nome": inst})
    with c2.form("remover"):
        st.markdown("##### Remover emissor")
        alvo_r = st.selectbox("Conta", opcoes, format_func=nome_conta, key="alvo_rem")
        if st.form_submit_button("Remover"):
            enviar("emissores", REMOVER_EMISSOR, {"endereco": alvo_r})
    exibir_resultado("emissores")


def aba_blockchain(conta, papel):
    st.subheader("Explorador da blockchain")
    valida, idx_inv, motivo_inv = no.cadeia.validate()
    if valida:
        st.success(f"✅ Cadeia íntegra: {len(no.cadeia.blocks)} blocos, todos os hashes e elos conferem.")
    else:
        st.error(f"❌ Cadeia CORROMPIDA no bloco #{idx_inv}: {motivo_inv}")

    with st.expander("🧪 Demonstração: simular adulteração de um bloco"):
        st.caption("Altera um bloco só na memória, para mostrar que a validação detecta. "
                   "Depois clique em Restaurar para recarregar a cadeia do disco.")
        blocos_tx = [b.index for b in no.cadeia.blocks[1:]]
        if blocos_tx:
            i = st.selectbox("Bloco", blocos_tx)
            payload_i = no.cadeia.blocks[i].data["payload"]
            campo = next((k for k in ("curso", "nome", "motivo", "codigo", "endereco") if k in payload_i), None)
            novo = st.text_input(f"Novo valor para '{campo}'", value="Medicina")
            a, r = st.columns(2)
            if a.button("Adulterar bloco", type="primary"):
                no.adulterar_bloco(i, campo, novo)
                st.rerun()
            if r.button("Restaurar do disco"):
                no.restaurar_do_disco()
                st.rerun()
        else:
            st.info("Faça ao menos uma operação primeiro.")

    for b in reversed(no.cadeia.blocks):
        tipo = b.data.get("tipo", "?")
        with st.container(border=True):
            titulo = f"**Bloco #{b.index}** · `{tipo}`"
            if b.index > 0:
                titulo += f" · assinado por {nome_conta(b.data.get('remetente'))}"
            if not valida and b.index == idx_inv:
                titulo += "  :red[**⚠ inválido**]"
            st.markdown(titulo)
            z = no.cadeia.difficulty
            st.markdown(f"hash: `{b.hash[:z]}`**`{b.hash[z:]}`**  \n"
                        f"hash anterior: `{b.previous_hash}`  \n"
                        f"nonce: `{b.nonce}` · minerado em {quando(b.timestamp)}")
            with st.expander("Dados do bloco"):
                st.json(b.data.get("payload", b.data))
        if b.index > 0:
            st.markdown("<div style='text-align:center;font-size:20px;margin:-8px 0'>⬆</div>",
                        unsafe_allow_html=True)
    st.download_button("Baixar blockchain (JSON)", json.dumps(no.cadeia.to_dict(), ensure_ascii=False, indent=2),
                       file_name="blockchain.json", mime="application/json")


def aba_rejeitadas(conta, papel):
    st.subheader("Transações rejeitadas pelo contrato")
    st.caption("Ficam só neste log do nó — nunca entram na blockchain.")
    if no.rejeitadas:
        st.dataframe(pd.DataFrame([{
            "Quando": quando(r["timestamp"]), "Conta": nome_conta(r["remetente"]),
            "Operação": r["tipo"], "Regra": r["regra"], "Motivo": r["motivo"]} for r in reversed(no.rejeitadas)]),
            hide_index=True, use_container_width=True)
    else:
        st.info("Nenhuma rejeição até agora.")


ABAS = {
    "meus": ("🎓 Meus diplomas", aba_meus_diplomas),
    "emitir": ("📝 Emitir", aba_emitir),
    "verificar": ("🔎 Verificar", aba_verificar),
    "revogar": ("🚫 Revogar", aba_revogar),
    "emissores": ("🏛️ Emissores", aba_emissores),
    "cadeia": ("⛓️ Blockchain", aba_blockchain),
    "rejeitadas": ("⚠️ Rejeitadas", aba_rejeitadas),
}
# A primeira aba é a tarefa principal de cada papel; as demais continuam disponíveis.
ORDEM_POR_PAPEL = {
    "EMISSOR": ["emitir", "revogar", "verificar", "cadeia", "rejeitadas", "emissores"],
    "ADMINISTRADOR": ["emissores", "revogar", "verificar", "cadeia", "rejeitadas", "emitir"],
}
ORDEM_PADRAO = ["meus", "verificar", "cadeia", "emitir", "revogar", "emissores", "rejeitadas"]


def painel():
    carteira = logado()
    conta = carteira.endereco
    papel = no.contrato.papel(conta)

    with st.sidebar:
        st.title("🎓 CertChain UEA")
        st.markdown(f"**{carteira.nome}**  \n:{COR_PAPEL.get(papel, 'red')}[**{papel}**]")
        st.caption("Endereço na blockchain (público)")
        st.code(conta, language=None)
        if st.button("Sair", use_container_width=True):
            sair()
            st.rerun()
        st.divider()
        st.caption("O que esta conta pode fazer, segundo o contrato")
        st.markdown(PERMISSOES.get(papel, PERMISSOES_PADRAO))

    st.title(f"Olá, {carteira.nome.split(' (')[0]}")
    metricas_cadeia()
    ordem = ORDEM_POR_PAPEL.get(papel, ORDEM_PADRAO)
    for chave, aba in zip(ordem, st.tabs([ABAS[k][0] for k in ordem])):
        with aba:
            ABAS[chave][1](conta, papel)


aplicar_estilo()
if logado() is not None:
    painel()
elif st.session_state["tela"] == "verificar":
    tela_verificacao_publica()
else:
    tela_login()
