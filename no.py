# no.py
# NÓ LOCAL da rede: junta a blockchain (blocos + mineração) ao contrato inteligente.
#
# Fluxo de uma operação:
#   login -> transação -> contrato confere as regras
#     -> rejeitada: vai para o log de rejeições e NÃO entra na cadeia
#     -> aceita: vira um bloco, é minerado (prova de trabalho) e salvo em disco
import json
import os
import time

from blockchain import Blockchain
from contas import Conta, carregar_contas, hash_senha, salvar_contas
from contrato import ContratoCertificados, ErroContrato
from transacao import criar_transacao

# Contas que já vêm criadas na demonstração.
CONTAS_PADRAO = [
    {"usuario": "reitoria", "nome": "Reitoria UEA (administrador)", "senha": "reitoria123", "tipo": "ADMIN"},
    {"usuario": "sec_est", "nome": "Secretaria Acadêmica EST/UEA", "senha": "est123", "tipo": "SECRETARIA"},
    {"usuario": "sec_esa", "nome": "Secretaria Acadêmica ESA/UEA", "senha": "esa123", "tipo": "SECRETARIA"},
    {"usuario": "caio", "nome": "Caio", "senha": "caio123", "tipo": "ALUNO", "matricula": "2026001"},
    {"usuario": "lucas", "nome": "Lucas", "senha": "lucas123", "tipo": "ALUNO", "matricula": "2026002"},
]
ADMIN = "reitoria"
EMISSORES_INICIAIS = ["sec_est", "sec_esa"]


def contas_padrao():
    return [Conta(c["usuario"], c["nome"], hash_senha(c["senha"]), c["tipo"], c.get("matricula"))
            for c in CONTAS_PADRAO]


class No:
    def __init__(self, pasta_dados="dados", dificuldade=4):
        self.pasta = pasta_dados
        self.dificuldade = dificuldade
        self.arq_cadeia = os.path.join(pasta_dados, "blockchain.json")
        self.arq_contas = os.path.join(pasta_dados, "contas.json")
        self.arq_rejeitadas = os.path.join(pasta_dados, "rejeitadas.json")
        os.makedirs(self.pasta, exist_ok=True)

        if os.path.exists(self.arq_contas):
            self.contas = carregar_contas(self.arq_contas)
        else:
            self.contas = contas_padrao()
            salvar_contas(self.contas, self.arq_contas)

        self.rejeitadas = []
        if os.path.exists(self.arq_rejeitadas):
            with open(self.arq_rejeitadas, encoding="utf-8") as f:
                self.rejeitadas = json.load(f)

        if os.path.exists(self.arq_cadeia) and self._cadeia_compativel():
            self.restaurar_do_disco()
        else:
            self._criar_cadeia()

    def _cadeia_compativel(self):
        """Só reaproveita a cadeia salva se o gênesis for desta versão do sistema."""
        try:
            genesis = Blockchain.load(self.arq_cadeia).blocks[0].data
        except (OSError, ValueError, KeyError, IndexError):
            return False
        return "emissores_iniciais" in genesis and genesis.get("admin") == ADMIN

    def _criar_cadeia(self):
        # O gênesis define o administrador e os emissores iniciais (secretarias EST e ESA).
        # Assim a permissão delas fica NA blockchain e volta quando a cadeia é reexecutada.
        emissores = [{"usuario": u, "nome": self.nome_conta(u)} for u in EMISSORES_INICIAIS]
        self.cadeia = Blockchain(self.dificuldade, genesis_data={
            "tipo": "GENESIS", "rede": "CertChain UEA", "admin": ADMIN,
            "emissores_iniciais": emissores,
            "descricao": "Registro de certificados acadêmicos"})
        self.contrato = ContratoCertificados(ADMIN, emissores)
        self.cadeia.save(self.arq_cadeia)
        self.rejeitadas = []
        with open(self.arq_rejeitadas, "w", encoding="utf-8") as f:
            json.dump([], f)

    # ------------------------------------------------------------ estado
    @staticmethod
    def reconstruir_estado(cadeia):
        """Reexecuta todas as transações desde o gênesis para obter o estado do contrato."""
        genesis = cadeia.blocks[0].data
        contrato = ContratoCertificados(genesis["admin"], genesis.get("emissores_iniciais", ()))
        for bloco in cadeia.blocks[1:]:
            contrato.executar(bloco.data, bloco.index)
        return contrato

    def restaurar_do_disco(self):
        self.cadeia = Blockchain.load(self.arq_cadeia)
        valida, indice, motivo = self.cadeia.validate()
        if not valida:
            raise RuntimeError(f"Arquivo da blockchain corrompido no bloco {indice}: {motivo}")
        self.contrato = self.reconstruir_estado(self.cadeia)

    # ------------------------------------------------------------ contas
    def conta(self, usuario):
        return next((c for c in self.contas if c.usuario == usuario), None)

    def nome_conta(self, usuario):
        c = self.conta(usuario)
        return c.nome if c else usuario

    def autenticar(self, usuario, senha):
        """Devolve a conta se usuário e senha conferem, senão None."""
        c = self.conta((usuario or "").strip())
        return c if c and c.confere_senha(senha) else None

    def registrar_aluno(self, nome, matricula, senha):
        """Cria a conta de um aluno. O usuário de login é aluno_<matrícula>."""
        nome, matricula, senha = (nome or "").strip(), (matricula or "").strip(), (senha or "").strip()
        if not nome or not matricula or not senha:
            return None
        if any(c.matricula == matricula for c in self.contas):
            return None
        nova = Conta("aluno_" + matricula, nome, hash_senha(senha), "ALUNO", matricula)
        self.contas.append(nova)
        salvar_contas(self.contas, self.arq_contas)
        return nova

    def listar_contas(self):
        return list(self.contas)

    def listar_alunos(self):
        return [c for c in self.contas if c.tipo == "ALUNO"]

    def papel_exibicao(self, usuario):
        """Papel mostrado na interface. Para o contrato, aluno é 'SEM PERMISSÃO'."""
        papel = self.contrato.papel(usuario)
        c = self.conta(usuario)
        if papel == "SEM PERMISSÃO" and c and c.tipo == "ALUNO":
            return "ALUNO"
        return papel

    # ------------------------------------------------------------ operações
    def enviar(self, conta, tipo, payload):
        """Cria a transação em nome da conta logada e submete ao nó."""
        if conta is None:
            return {"ok": False, "regra": "AUTH", "erro": "é preciso estar logado para enviar transações"}
        return self.submeter(criar_transacao(conta.usuario, tipo, payload))

    def submeter(self, tx):
        """Passa a transação pelo contrato e, se aceita, minera o bloco."""
        valida, indice, motivo = self.cadeia.validate()
        if not valida:
            return self._rejeitar(tx, "N1", f"nó recusou: blockchain corrompida no bloco {indice} ({motivo})")
        bloco = self.cadeia.new_block(tx)
        try:
            self.contrato.executar(tx, bloco.index)
        except ErroContrato as e:
            return self._rejeitar(tx, e.regra, e.mensagem)
        inicio = time.time()
        self.cadeia.add_block(bloco)  # mineração (prova de trabalho)
        self.cadeia.save(self.arq_cadeia)
        return {"ok": True, "bloco": bloco.to_dict(), "tempo_mineracao": time.time() - inicio}

    def _rejeitar(self, tx, regra, mensagem):
        registro = {"timestamp": time.time(), "tipo": tx.get("tipo") if isinstance(tx, dict) else None,
                    "remetente": tx.get("remetente") if isinstance(tx, dict) else None,
                    "regra": regra, "motivo": mensagem}
        self.rejeitadas.append(registro)
        with open(self.arq_rejeitadas, "w", encoding="utf-8") as f:
            json.dump(self.rejeitadas, f, ensure_ascii=False, indent=2)
        return {"ok": False, "regra": regra, "erro": mensagem}

    # ------------------------------------------------------------ demonstração
    def adulterar_bloco(self, indice, campo, valor):
        """APENAS PARA DEMONSTRAÇÃO: altera um bloco em memória para mostrar que a validação detecta."""
        self.cadeia.blocks[indice].data["payload"][campo] = valor
