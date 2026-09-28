# contrato.py
# CONTRATO INTELIGENTE de certificação acadêmica.
#
# Toda transação passa por este contrato antes de virar bloco:
#   - se alguma regra falhar, ele lança ErroContrato e a transação NÃO entra na cadeia;
#   - se todas as regras passarem, ele atualiza o estado e o nó minera o bloco.
#
# O estado (emissores e certificados) não é salvo à parte. Quando o nó inicia,
# ele reexecuta todas as transações da cadeia desde o bloco gênesis.
#
# Operações: AUTORIZAR_EMISSOR e REMOVER_EMISSOR (só o administrador)
#            EMITIR_CERTIFICADO e REVOGAR_CERTIFICADO (secretarias autorizadas)
#            a consulta de certificados é pública e não cria transação
import hashlib
import re
import unicodedata
from datetime import date, datetime

AUTORIZAR_EMISSOR = "AUTORIZAR_EMISSOR"
REMOVER_EMISSOR = "REMOVER_EMISSOR"
EMITIR_CERTIFICADO = "EMITIR_CERTIFICADO"
REVOGAR_CERTIFICADO = "REVOGAR_CERTIFICADO"
OPERACOES = (AUTORIZAR_EMISSOR, REMOVER_EMISSOR, EMITIR_CERTIFICADO, REVOGAR_CERTIFICADO)

ATIVO = "ATIVO"
REVOGADO = "REVOGADO"

RE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
RE_CODIGO = re.compile(r"^[A-Z0-9][A-Z0-9-]{3,39}$")


class ErroContrato(Exception):
    """Regra de negócio violada. `regra` diz qual foi (ex.: E1)."""

    def __init__(self, regra, mensagem):
        super().__init__(f"[{regra}] {mensagem}")
        self.regra = regra
        self.mensagem = mensagem


def _normalizar_nome(nome):
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.upper().split())


def hash_titular(nome, matricula):
    """Hash que identifica o aluno sem colocar nome e matrícula na cadeia."""
    return hashlib.sha256(f"{matricula.strip()}|{_normalizar_nome(nome)}".encode("utf-8")).hexdigest()


def hash_arquivo(conteudo_bytes):
    return hashlib.sha256(conteudo_bytes).hexdigest()


def _texto(payload, campo, regra, minimo, maximo):
    valor = payload.get(campo)
    if not isinstance(valor, str) or not (minimo <= len(valor.strip()) <= maximo):
        raise ErroContrato(regra, f"'{campo}' deve ter entre {minimo} e {maximo} caracteres")
    return valor.strip()


class ContratoCertificados:
    def __init__(self, admin, emissores_iniciais=()):
        """`admin` e `emissores_iniciais` vêm do bloco gênesis."""
        self.admin = admin
        self.emissores = {}       # usuario -> {usuario, nome, ativo, autorizado_no_bloco, removido_no_bloco}
        self.certificados = {}    # codigo -> dados do certificado
        self.codigo_por_hash = {} # hash do PDF -> codigo
        for e in emissores_iniciais:
            self.emissores[e["usuario"]] = {"usuario": e["usuario"], "nome": e["nome"], "ativo": True,
                                            "autorizado_no_bloco": 0, "removido_no_bloco": None}

    # ================================================================ execução
    def executar(self, tx, bloco):
        """Confere as regras da transação e, se todas passarem, atualiza o estado."""
        if not isinstance(tx, dict) or any(c not in tx for c in ("tipo", "remetente", "timestamp", "payload")) \
                or not isinstance(tx.get("payload"), dict):
            raise ErroContrato("G1", "transação mal formada (faltam campos obrigatórios)")
        if tx["tipo"] == AUTORIZAR_EMISSOR:
            self._autorizar_emissor(tx, bloco)
        elif tx["tipo"] == REMOVER_EMISSOR:
            self._remover_emissor(tx, bloco)
        elif tx["tipo"] == EMITIR_CERTIFICADO:
            self._emitir(tx, bloco)
        elif tx["tipo"] == REVOGAR_CERTIFICADO:
            self._revogar(tx, bloco)
        else:
            raise ErroContrato("G2", f"operação desconhecida: {tx['tipo']}")

    # ------------------------------------------------ administração (A*, R*)
    def _autorizar_emissor(self, tx, bloco):
        p = tx["payload"]
        if tx["remetente"] != self.admin:
            raise ErroContrato("A1", "permissão negada: somente o administrador autoriza emissores")
        usuario = p.get("usuario")
        if not isinstance(usuario, str) or not usuario.strip():
            raise ErroContrato("A2", "informe o usuário que será autorizado")
        nome = _texto(p, "nome", "A3", 3, 100)
        if usuario == self.admin:
            raise ErroContrato("A4", "o administrador não pode ser emissor (separação de funções)")
        if self.emissores.get(usuario, {}).get("ativo"):
            raise ErroContrato("A5", "emissor já está autorizado")

        self.emissores[usuario] = {"usuario": usuario, "nome": nome, "ativo": True,
                                   "autorizado_no_bloco": bloco, "removido_no_bloco": None}

    def _remover_emissor(self, tx, bloco):
        if tx["remetente"] != self.admin:
            raise ErroContrato("R1", "permissão negada: somente o administrador remove emissores")
        usuario = tx["payload"].get("usuario")
        if not self.emissores.get(usuario, {}).get("ativo"):
            raise ErroContrato("R2", "emissor não encontrado ou já removido")

        self.emissores[usuario]["ativo"] = False
        self.emissores[usuario]["removido_no_bloco"] = bloco

    # ------------------------------------------------ certificados (E*, V*)
    def _emitir(self, tx, bloco):
        p = tx["payload"]
        emissor = self.emissores.get(tx["remetente"])
        if not emissor or not emissor["ativo"]:
            raise ErroContrato("E1", "permissão negada: remetente não é um emissor autorizado")
        codigo = p.get("codigo")
        if not isinstance(codigo, str) or not RE_CODIGO.match(codigo):
            raise ErroContrato("E2", "código inválido (use de 4 a 40 caracteres: A-Z, 0-9 e hífen)")
        if codigo in self.certificados:
            raise ErroContrato("E3", f"já existe certificado com o código {codigo}")
        doc = p.get("documento_hash")
        if not isinstance(doc, str) or not RE_SHA256.match(doc):
            raise ErroContrato("E4", "hash do documento inválido (esperado SHA-256)")
        if doc in self.codigo_por_hash:
            raise ErroContrato("E5", f"este documento já foi registrado (certificado {self.codigo_por_hash[doc]})")
        titular = p.get("titular_hash")
        if not isinstance(titular, str) or not RE_SHA256.match(titular):
            raise ErroContrato("E6", "hash do titular inválido (esperado SHA-256)")
        curso = _texto(p, "curso", "E7", 3, 120)
        carga = p.get("carga_horaria")
        if not isinstance(carga, int) or isinstance(carga, bool) or not (1 <= carga <= 20000):
            raise ErroContrato("E8", "carga horária deve ser um inteiro entre 1 e 20000")
        try:
            conclusao = date.fromisoformat(p.get("data_conclusao"))
        except (TypeError, ValueError):
            raise ErroContrato("E9", "data de conclusão inválida (use AAAA-MM-DD)")
        if conclusao > datetime.fromtimestamp(tx["timestamp"]).date():
            raise ErroContrato("E9", "data de conclusão não pode estar no futuro")

        self.certificados[codigo] = {
            "codigo": codigo, "documento_hash": doc, "titular_hash": titular,
            "curso": curso, "carga_horaria": carga, "data_conclusao": conclusao.isoformat(),
            "instituicao": emissor["nome"], "emissor": tx["remetente"],
            "status": ATIVO, "emitido_no_bloco": bloco, "emitido_em": tx["timestamp"],
            "revogacao": None,
            "historico": [{"operacao": EMITIR_CERTIFICADO, "bloco": bloco,
                           "por": tx["remetente"], "timestamp": tx["timestamp"]}],
        }
        self.codigo_por_hash[doc] = codigo

    def _revogar(self, tx, bloco):
        p = tx["payload"]
        cert = self.certificados.get(p.get("codigo"))
        if not cert:
            raise ErroContrato("V1", "certificado não encontrado")
        if cert["status"] != ATIVO:
            raise ErroContrato("V2", "certificado já está revogado")
        rem = tx["remetente"]
        eh_emissor_original = rem == cert["emissor"] and self.emissores.get(rem, {}).get("ativo")
        if not (eh_emissor_original or rem == self.admin):
            raise ErroContrato("V3", "permissão negada: só o emissor original ou o administrador revoga")
        motivo = _texto(p, "motivo", "V4", 5, 200)

        cert["status"] = REVOGADO
        cert["revogacao"] = {"motivo": motivo, "bloco": bloco, "por": rem, "timestamp": tx["timestamp"]}
        cert["historico"].append({"operacao": REVOGAR_CERTIFICADO, "bloco": bloco,
                                  "por": rem, "timestamp": tx["timestamp"]})

    # ================================================================ consultas
    def papel(self, usuario):
        if usuario == self.admin:
            return "ADMINISTRADOR"
        if self.emissores.get(usuario, {}).get("ativo"):
            return "EMISSOR"
        return "SEM PERMISSÃO"

    def consultar(self, codigo):
        return self.certificados.get(codigo)

    def verificar_documento(self, documento_hash):
        codigo = self.codigo_por_hash.get(documento_hash)
        return self.certificados.get(codigo) if codigo else None
