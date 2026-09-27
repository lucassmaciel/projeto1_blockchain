"""Regras de negócio do contrato inteligente: operações válidas, entradas inválidas e sem permissão."""
import json

import pytest

from contrato import ATIVO, REVOGADO, hash_arquivo, hash_titular
from no import No
from transacao import criar_transacao


def rejeitada(r, regra):
    return r["ok"] is False and r["regra"] == regra


# ------------------------------------------------------------------ operações válidas
class TestOperacoesValidas:
    def test_emissores_iniciais_vem_do_genesis(self, no, contas):
        genesis = no.cadeia.blocks[0].data
        assert {e["endereco"] for e in genesis["emissores_iniciais"]} == {contas["est"], contas["esa"]}
        assert no.contrato.papel(contas["est"]) == "EMISSOR"

    def test_admin_autoriza_emissor(self, no, contas):
        r = no.enviar(contas["admin"], "AUTORIZAR_EMISSOR", {"endereco": contas["aluno"], "nome": "UEA — Pós-graduação"})
        assert r["ok"] and r["bloco"]["index"] == 1
        assert no.contrato.papel(contas["aluno"]) == "EMISSOR"

    def test_emissor_emite_certificado_e_estado_muda(self, no, contas, cert):
        antes = len(no.cadeia.blocks)
        r = no.enviar(contas["est"], "EMITIR_CERTIFICADO", cert)
        assert r["ok"] and len(no.cadeia.blocks) == antes + 1
        c = no.contrato.consultar("UEA-2026-0001")
        assert c["status"] == ATIVO and c["instituicao"] == "Secretaria Acadêmica EST/UEA" and c["emitido_no_bloco"] == antes

    def test_verificacao_pelo_hash_do_documento(self, no, contas, cert):
        no.enviar(contas["est"], "EMITIR_CERTIFICADO", cert)
        assert no.contrato.verificar_documento(cert["documento_hash"])["codigo"] == "UEA-2026-0001"

    def test_documento_adulterado_nao_e_reconhecido(self, no, contas, cert):
        no.enviar(contas["est"], "EMITIR_CERTIFICADO", cert)
        assert no.contrato.verificar_documento(hash_arquivo(b"PDF do diploma da Ana!")) is None

    def test_conferencia_do_titular(self, no, contas, cert):
        no.enviar(contas["est"], "EMITIR_CERTIFICADO", cert)
        c = no.contrato.consultar("UEA-2026-0001")
        assert c["titular_hash"] == hash_titular("  ana   SOUZA ", "2021001")   # normaliza espaços/caixa
        assert c["titular_hash"] != hash_titular("Ana Souza", "2021002")

    def test_emissor_revoga_certificado(self, no, contas, cert):
        no.enviar(contas["est"], "EMITIR_CERTIFICADO", cert)
        r = no.enviar(contas["est"], "REVOGAR_CERTIFICADO", {"codigo": "UEA-2026-0001", "motivo": "Erro no histórico"})
        c = no.contrato.consultar("UEA-2026-0001")
        assert r["ok"] and c["status"] == REVOGADO and len(c["historico"]) == 2

    def test_admin_pode_revogar(self, no, contas, cert):
        no.enviar(contas["est"], "EMITIR_CERTIFICADO", cert)
        assert no.enviar(contas["admin"], "REVOGAR_CERTIFICADO", {"codigo": "UEA-2026-0001", "motivo": "Fraude apurada"})["ok"]

    def test_admin_remove_emissor(self, no, contas):
        assert no.enviar(contas["admin"], "REMOVER_EMISSOR", {"endereco": contas["est"]})["ok"]
        assert no.contrato.papel(contas["est"]) == "SEM PERMISSÃO"

    def test_certificado_continua_valido_apos_remover_emissor(self, no, contas, cert):
        no.enviar(contas["est"], "EMITIR_CERTIFICADO", cert)
        no.enviar(contas["admin"], "REMOVER_EMISSOR", {"endereco": contas["est"]})
        assert no.contrato.consultar("UEA-2026-0001")["status"] == ATIVO


# ------------------------------------------------------------------ sem permissão
class TestSemPermissao:
    def test_aluno_nao_autoriza_emissor(self, no, contas):
        r = no.enviar(contas["aluno"], "AUTORIZAR_EMISSOR", {"endereco": contas["aluno"], "nome": "Eu mesmo"})
        assert rejeitada(r, "A1") and len(no.cadeia.blocks) == 1

    def test_aluno_nao_emite(self, no, contas, cert):
        assert rejeitada(no.enviar(contas["aluno"], "EMITIR_CERTIFICADO", cert), "E1")

    def test_emissor_removido_nao_emite(self, no, contas, cert):
        no.enviar(contas["admin"], "REMOVER_EMISSOR", {"endereco": contas["est"]})
        assert rejeitada(no.enviar(contas["est"], "EMITIR_CERTIFICADO", cert), "E1")

    def test_outro_emissor_nao_revoga(self, no, contas, cert):
        no.enviar(contas["est"], "EMITIR_CERTIFICADO", cert)
        r = no.enviar(contas["esa"], "REVOGAR_CERTIFICADO", {"codigo": "UEA-2026-0001", "motivo": "Tentativa indevida"})
        assert rejeitada(r, "V3")

    def test_emissor_nao_remove_emissor(self, no, contas):
        assert rejeitada(no.enviar(contas["est"], "REMOVER_EMISSOR", {"endereco": contas["est"]}), "R1")


# ------------------------------------------------------------------ entradas inválidas
class TestEntradasInvalidas:
    @pytest.mark.parametrize("campo, valor, regra", [
        ("codigo", "ab", "E2"),
        ("codigo", "UEA 2026 01", "E2"),
        ("documento_hash", "abc", "E4"),
        ("documento_hash", "G" * 64, "E4"),
        ("titular_hash", "", "E6"),
        ("curso", "  ", "E7"),
        ("carga_horaria", 0, "E8"),
        ("carga_horaria", "3200", "E8"),
        ("data_conclusao", "15/07/2026", "E9"),
        ("data_conclusao", "2099-01-01", "E9"),
    ])
    def test_emissao_com_campo_invalido(self, no, contas, cert, campo, valor, regra):
        r = no.enviar(contas["est"], "EMITIR_CERTIFICADO", {**cert, campo: valor})
        assert rejeitada(r, regra)

    def test_codigo_duplicado(self, no, contas, cert):
        no.enviar(contas["est"], "EMITIR_CERTIFICADO", cert)
        r = no.enviar(contas["est"], "EMITIR_CERTIFICADO", {**cert, "documento_hash": hash_arquivo(b"outro")})
        assert rejeitada(r, "E3")

    def test_mesmo_documento_duas_vezes(self, no, contas, cert):
        no.enviar(contas["est"], "EMITIR_CERTIFICADO", cert)
        assert rejeitada(no.enviar(contas["est"], "EMITIR_CERTIFICADO", {**cert, "codigo": "UEA-2026-0002"}), "E5")

    def test_revogar_inexistente(self, no, contas):
        r = no.enviar(contas["est"], "REVOGAR_CERTIFICADO", {"codigo": "NAO-EXISTE", "motivo": "qualquer"})
        assert rejeitada(r, "V1")

    def test_revogar_duas_vezes(self, no, contas, cert):
        no.enviar(contas["est"], "EMITIR_CERTIFICADO", cert)
        no.enviar(contas["est"], "REVOGAR_CERTIFICADO", {"codigo": "UEA-2026-0001", "motivo": "Erro no histórico"})
        r = no.enviar(contas["est"], "REVOGAR_CERTIFICADO", {"codigo": "UEA-2026-0001", "motivo": "De novo"})
        assert rejeitada(r, "V2")

    def test_revogar_sem_motivo(self, no, contas, cert):
        no.enviar(contas["est"], "EMITIR_CERTIFICADO", cert)
        assert rejeitada(no.enviar(contas["est"], "REVOGAR_CERTIFICADO", {"codigo": "UEA-2026-0001", "motivo": ""}), "V4")

    def test_autorizar_endereco_invalido(self, no, contas):
        assert rejeitada(no.enviar(contas["admin"], "AUTORIZAR_EMISSOR", {"endereco": "0x123", "nome": "X Y Z"}), "A2")

    def test_admin_nao_pode_ser_emissor(self, no, contas):
        assert rejeitada(no.enviar(contas["admin"], "AUTORIZAR_EMISSOR", {"endereco": contas["admin"], "nome": "Reitoria"}), "A4")

    def test_autorizar_emissor_ja_ativo(self, no, contas):
        r = no.enviar(contas["admin"], "AUTORIZAR_EMISSOR", {"endereco": contas["est"], "nome": "UEA — EST"})
        assert rejeitada(r, "A5")

    def test_operacao_desconhecida(self, no, contas):
        assert rejeitada(no.enviar(contas["admin"], "APAGAR_TUDO", {}), "G2")

    def test_rejeicao_nao_cria_bloco_e_fica_no_log(self, no, contas, cert):
        blocos = len(no.cadeia.blocks)
        no.enviar(contas["aluno"], "EMITIR_CERTIFICADO", cert)
        assert len(no.cadeia.blocks) == blocos
        assert no.rejeitadas[-1]["regra"] == "E1"


# ------------------------------------------------------------------ segurança das transações
class TestSeguranca:
    def _tx(self, no, conta, cert):
        return criar_transacao(no.autenticada(conta), "EMITIR_CERTIFICADO", cert, no.contrato.proximo_nonce(conta))

    def test_transacao_alterada_apos_assinatura(self, no, contas, cert):
        tx = self._tx(no, contas["est"], cert)
        tx["payload"] = {**tx["payload"], "curso": "Medicina"}
        assert rejeitada(no.submeter(tx), "G4")

    def test_aluno_se_passa_por_emissor(self, no, contas, cert):
        tx = self._tx(no, contas["aluno"], cert)
        tx["remetente"] = contas["est"]            # finge ser a secretaria, mas a chave é do aluno
        assert rejeitada(no.submeter(tx), "G3")

    def test_replay_de_transacao(self, no, contas, cert):
        tx = self._tx(no, contas["est"], cert)
        assert no.submeter(tx)["ok"]
        assert rejeitada(no.submeter(tx), "G5")

    def test_transacao_mal_formada(self, no):
        assert rejeitada(no.submeter({"tipo": "EMITIR_CERTIFICADO"}), "G1")

    def test_no_recusa_operar_com_cadeia_adulterada(self, no, contas, cert):
        no.enviar(contas["est"], "EMITIR_CERTIFICADO", cert)
        no.adulterar_bloco(1, "curso", "Medicina")
        r = no.enviar(contas["est"], "EMITIR_CERTIFICADO",
                                  {**cert, "codigo": "UEA-2026-0002", "documento_hash": hash_arquivo(b"x")})
        assert rejeitada(r, "N1")


# ------------------------------------------------------------------ persistência
class TestPersistencia:
    def test_reiniciar_no_reconstroi_estado_da_cadeia(self, no, contas, cert):
        no.enviar(contas["est"], "EMITIR_CERTIFICADO", cert)
        no.enviar(contas["est"], "REVOGAR_CERTIFICADO", {"codigo": "UEA-2026-0001", "motivo": "Erro no histórico"})
        novo = No(no.pasta, dificuldade=2)
        assert novo.contrato.certificados == no.contrato.certificados
        assert novo.contrato.papel(contas["est"]) == "EMISSOR"

    def test_arquivo_adulterado_e_detectado_ao_iniciar(self, no, contas, cert):
        no.enviar(contas["est"], "EMITIR_CERTIFICADO", cert)
        with open(no.arq_cadeia, encoding="utf-8") as f:
            dados = json.load(f)
        dados["blocks"][1]["data"]["payload"]["curso"] = "Medicina"
        with open(no.arq_cadeia, "w", encoding="utf-8") as f:
            json.dump(dados, f)
        with pytest.raises(RuntimeError, match="corrompido no bloco 1"):
            No(no.pasta, dificuldade=2)

    def test_cadastrar_aluno_e_reiniciar_nao_apaga_a_cadeia(self, no, contas, cert):
        no.enviar(contas["est"], "EMITIR_CERTIFICADO", cert)
        no.registrar_usuario("Ana Souza", "2021001", "ana123")
        novo = No(no.pasta, dificuldade=2)
        assert len(novo.cadeia.blocks) == 2 and novo.contrato.admin == no.contrato.admin

    def test_emissor_removido_continua_removido_apos_reiniciar(self, no, contas):
        no.enviar(contas["admin"], "REMOVER_EMISSOR", {"endereco": contas["esa"]})
        assert No(no.pasta, dificuldade=2).contrato.papel(contas["esa"]) == "SEM PERMISSÃO"


# ------------------------------------------------------------------ autenticação
class TestAutenticacao:
    def test_sem_login_nao_envia_transacao(self, no, cert):
        r = No.enviar(no, None, "EMITIR_CERTIFICADO", cert)
        assert rejeitada(r, "AUTH") and len(no.cadeia.blocks) == 1

    def test_senha_errada_nao_desbloqueia_carteira(self, no, contas):
        assert no.autenticar(contas["est"], "senha-errada") is None
