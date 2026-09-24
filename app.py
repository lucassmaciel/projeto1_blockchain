# app.py
# Interface Streamlit do CertChain UEA — registrar, consultar e visualizar a blockchain.
# Executar:  streamlit run app.py
import json
import os
from datetime import date, datetime

import pandas as pd
import streamlit as st

from contrato import (ATIVO, AUTORIZAR_EMISSOR, EMITIR_CERTIFICADO, REMOVER_EMISSOR,
                      REVOGAR_CERTIFICADO, hash_arquivo, hash_titular)
from no import No

PASTA_DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")

st.set_page_config(page_title="CertChain UEA", page_icon="🎓", layout="wide")


@st.cache_resource
def obter_no():
    """Um único nó local por execução do servidor (a blockchain fica em dados/)."""
    return No(PASTA_DADOS, dificuldade=4)


no = obter_no()
contrato = no.contrato


# ------------------------------------------------------------------ utilidades
def nome_conta(endereco):
    c = no.carteira(endereco)
    return c.nome if c else (endereco[:10] + "…" if endereco else "—")


def quando(ts):
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S")


def mostrar_resultado(r):
    if r["ok"]:
        b = r["bloco"]
        st.success(f"✅ Transação aceita pelo contrato e minerada no **bloco #{b['index']}** "
                   f"(nonce {b['nonce']:,}, {r['tempo_mineracao']:.2f}s)".replace(",", "."))
        st.code(f"hash:          {b['hash']}\nhash anterior: {b['previous_hash']}", language=None)
    else:
        st.error(f"❌ Transação **rejeitada** pelo contrato — regra **{r['regra']}**: {r['erro']}\n\n"
                 "Nenhum bloco foi criado.")


def enviar(chave, tipo, payload):
    """Envia a transação e recarrega a página para atualizar barra lateral, tabelas e explorador."""
    st.session_state["resultado"] = {"chave": chave, "r": no.enviar(conta, tipo, payload), "payload": payload}
    st.rerun()


def exibir_resultado(chave):
    res = st.session_state.get("resultado")
    if res and res["chave"] == chave:
        mostrar_resultado(res["r"])
        with st.expander("Payload da transação enviada"):
            st.json(res["payload"])


def cartao_certificado(c):
    if c is None:
        st.error("❌ **Não encontrado.** Documento não registrado na blockchain ou adulterado.")
        return
    if c["status"] == ATIVO:
        st.success(f"✅ Certificado **AUTÊNTICO** e **ATIVO** — {c['codigo']}")
    else:
        rv = c["revogacao"]
        st.error(f"🚫 Certificado **REVOGADO** no bloco #{rv['bloco']} — motivo: {rv['motivo']}")
    st.write(f"**Curso:** {c['curso']}  \n"
             f"**Carga horária:** {c['carga_horaria']} h  \n"
             f"**Conclusão:** {date.fromisoformat(c['data_conclusao']).strftime('%d/%m/%Y')}  \n"
             f"**Instituição emissora:** {c['instituicao']}  \n"
             f"**Emissor (endereço):** `{c['emissor']}`  \n"
             f"**Registrado no bloco:** #{c['emitido_no_bloco']} em {quando(c['emitido_em'])}  \n"
             f"**Hash do documento:** `{c['documento_hash']}`")
    st.caption("Histórico na blockchain")
    st.dataframe(pd.DataFrame([{"Bloco": h["bloco"], "Operação": h["operacao"], "Por": nome_conta(h["por"]),
                                "Quando": quando(h["timestamp"])} for h in c["historico"]]),
                 hide_index=True, use_container_width=True)


# ------------------------------------------------------------------ barra lateral
with st.sidebar:
    st.title("🎓 CertChain UEA")
    st.caption("Registro de certificados acadêmicos em blockchain local")
    opcoes = [c.endereco for c in no.carteiras]
    conta = st.selectbox("Conta ativa (quem assina as transações)", opcoes,
                         format_func=lambda e: f"{nome_conta(e)}")
    papel = contrato.papel(conta)
    cor = {"ADMINISTRADOR": "blue", "EMISSOR": "green"}.get(papel, "red")
    st.markdown(f"Papel no contrato: :{cor}[**{papel}**]")
    st.code(conta, language=None)

    st.divider()
    valida, idx_inv, motivo_inv = no.cadeia.validate()
    st.metric("Blocos", len(no.cadeia.blocks))
    st.metric("Dificuldade (zeros no hash)", no.cadeia.difficulty)
    st.metric("Certificados", len(contrato.certificados))
    if valida:
        st.success("Cadeia íntegra ✅")
    else:
        st.error(f"Cadeia CORROMPIDA ❌ no bloco #{idx_inv}: {motivo_inv}")

(aba_emitir, aba_verificar, aba_revogar, aba_emissores,
 aba_cadeia, aba_rejeitadas) = st.tabs(["🎓 Emitir", "🔎 Verificar", "🚫 Revogar",
                                        "🏛️ Emissores", "⛓️ Blockchain", "⚠️ Rejeitadas"])

# ------------------------------------------------------------------ emitir
with aba_emitir:
    st.header("Emitir certificado")
    st.caption(f"A transação será assinada por **{nome_conta(conta)}** ({papel}).")
    with st.form("emitir", clear_on_submit=False):
        c1, c2 = st.columns(2)
        codigo = c1.text_input("Código do certificado", value=f"UEA-2026-{len(contrato.certificados) + 1:04d}")
        curso = c2.text_input("Curso", value="Sistemas de Informação")
        nome = c1.text_input("Nome do aluno (não vai para a blockchain)")
        matricula = c2.text_input("Matrícula (não vai para a blockchain)")
        carga = c1.number_input("Carga horária (h)", min_value=0, max_value=50000, value=3200, step=10)
        conclusao = c2.date_input("Data de conclusão", value=date.today(),
                                  min_value=date(1990, 1, 1), max_value=date(2100, 12, 31), format="DD/MM/YYYY")
        pdf = st.file_uploader("Diploma (PDF) — só o hash SHA-256 é registrado", type=["pdf"])
        registrar = st.form_submit_button("Registrar na blockchain", type="primary")
    if registrar:
        if not nome.strip() or not matricula.strip():
            st.warning("Preencha nome e matrícula do aluno.")
        else:
            payload = {
                "codigo": codigo.strip().upper(),
                "documento_hash": hash_arquivo(pdf.getvalue()) if pdf else "",
                "titular_hash": hash_titular(nome, matricula),
                "curso": curso,
                "carga_horaria": int(carga),
                "data_conclusao": conclusao.isoformat(),
            }
            enviar("emitir", EMITIR_CERTIFICADO, payload)
    exibir_resultado("emitir")

# ------------------------------------------------------------------ verificar
with aba_verificar:
    st.header("Verificar certificado")
    st.caption("Consulta pública: qualquer pessoa pode verificar, sem conta e sem transação.")
    col_pdf, col_cod = st.columns(2)
    with col_pdf:
        st.subheader("Pelo arquivo PDF")
        pdf_v = st.file_uploader("Arraste o diploma recebido", type=["pdf"], key="pdf_verificar")
        if pdf_v:
            h = hash_arquivo(pdf_v.getvalue())
            st.caption(f"SHA-256 calculado: `{h}`")
            cartao_certificado(contrato.verificar_documento(h))
    with col_cod:
        st.subheader("Pelo código")
        cod_v = st.text_input("Código impresso no diploma", placeholder="UEA-2026-0001")
        if cod_v:
            cert_v = contrato.consultar(cod_v.strip().upper())
            cartao_certificado(cert_v)
            if cert_v:
                with st.expander("Conferir titular (nome + matrícula)"):
                    n = st.text_input("Nome", key="tit_nome")
                    m = st.text_input("Matrícula", key="tit_mat")
                    if n and m:
                        if hash_titular(n, m) == cert_v["titular_hash"]:
                            st.success("Titular confere ✅")
                        else:
                            st.error("Titular NÃO confere ❌")

    st.divider()
    st.subheader("Estado do contrato — certificados registrados")
    if contrato.certificados:
        st.dataframe(pd.DataFrame([{
            "Código": c["codigo"], "Status": c["status"], "Curso": c["curso"],
            "Instituição": c["instituicao"], "Bloco": c["emitido_no_bloco"],
            "Hash do documento": c["documento_hash"][:16] + "…"} for c in contrato.certificados.values()]),
            hide_index=True, use_container_width=True)
    else:
        st.info("Nenhum certificado emitido ainda.")

# ------------------------------------------------------------------ revogar
with aba_revogar:
    st.header("Revogar certificado")
    st.caption(f"A transação será assinada por **{nome_conta(conta)}** ({papel}). "
               "Só o emissor original ou o administrador podem revogar.")
    if not contrato.certificados:
        st.info("Nenhum certificado emitido ainda.")
    else:
        with st.form("revogar"):
            cod_r = st.selectbox("Certificado", list(contrato.certificados),
                                 format_func=lambda k: f"{k} — {contrato.certificados[k]['status']}")
            motivo = st.text_area("Motivo da revogação")
            revogar = st.form_submit_button("Revogar", type="primary")
        if revogar:
            enviar("revogar", REVOGAR_CERTIFICADO, {"codigo": cod_r, "motivo": motivo})
    exibir_resultado("revogar")

# ------------------------------------------------------------------ emissores
with aba_emissores:
    st.header("Emissores autorizados")
    st.caption(f"Administrador (definido no bloco gênesis): **{nome_conta(contrato.admin)}** `{contrato.admin}`")
    if contrato.emissores:
        st.dataframe(pd.DataFrame([{
            "Instituição": e["nome"], "Conta": nome_conta(e["endereco"]), "Endereço": e["endereco"],
            "Ativo": "✅" if e["ativo"] else "❌", "Autorizado no bloco": e["autorizado_no_bloco"],
            "Removido no bloco": e["removido_no_bloco"]} for e in contrato.emissores.values()]),
            hide_index=True, use_container_width=True)
    else:
        st.info("Nenhum emissor autorizado ainda.")

    st.caption(f"As operações abaixo serão assinadas por **{nome_conta(conta)}** ({papel}).")
    c1, c2 = st.columns(2)
    with c1.form("autorizar"):
        st.subheader("Autorizar emissor")
        alvo = st.selectbox("Conta", opcoes, format_func=nome_conta, key="alvo_aut")
        inst = st.text_input("Nome da instituição/setor", value="UEA — Escola Superior de Tecnologia")
        if st.form_submit_button("Autorizar", type="primary"):
            enviar("emissores", AUTORIZAR_EMISSOR, {"endereco": alvo, "nome": inst})
    with c2.form("remover"):
        st.subheader("Remover emissor")
        alvo_r = st.selectbox("Conta", opcoes, format_func=nome_conta, key="alvo_rem")
        if st.form_submit_button("Remover"):
            enviar("emissores", REMOVER_EMISSOR, {"endereco": alvo_r})
    exibir_resultado("emissores")

# ------------------------------------------------------------------ blockchain
with aba_cadeia:
    st.header("Explorador da blockchain")
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
        invalido = (not valida) and b.index >= idx_inv
        with st.container(border=True):
            titulo = f"**Bloco #{b.index}** · `{tipo}`"
            if b.index > 0:
                titulo += f" · assinado por {nome_conta(b.data.get('remetente'))}"
            st.markdown(titulo + ("  :red[**⚠ inválido**]" if invalido and b.index == idx_inv else ""))
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

# ------------------------------------------------------------------ rejeitadas
with aba_rejeitadas:
    st.header("Transações rejeitadas pelo contrato")
    st.caption("Ficam só neste log do nó — nunca entram na blockchain.")
    if no.rejeitadas:
        st.dataframe(pd.DataFrame([{
            "Quando": quando(r["timestamp"]), "Conta": nome_conta(r["remetente"]),
            "Operação": r["tipo"], "Regra": r["regra"], "Motivo": r["motivo"]} for r in reversed(no.rejeitadas)]),
            hide_index=True, use_container_width=True)
    else:
        st.info("Nenhuma rejeição até agora.")
