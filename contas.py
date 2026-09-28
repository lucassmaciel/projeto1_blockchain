# contas.py
# Contas de usuário do sistema (Reitoria, secretarias e alunos).
# A senha não é guardada em texto: guardamos o hash SHA-256 dela, e no login
# comparamos o hash da senha digitada com o hash salvo.
import hashlib
import json
import os


def hash_senha(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


class Conta:
    def __init__(self, usuario, nome, senha_hash, tipo="ALUNO", matricula=None):
        self.usuario = usuario      # identificador da conta, é o "remetente" nas transações
        self.nome = nome
        self.senha_hash = senha_hash
        self.tipo = tipo            # ADMIN, SECRETARIA ou ALUNO
        self.matricula = matricula

    def confere_senha(self, senha):
        return hash_senha(senha or "") == self.senha_hash

    def to_dict(self):
        return {"usuario": self.usuario, "nome": self.nome, "senha_hash": self.senha_hash,
                "tipo": self.tipo, "matricula": self.matricula}

    @staticmethod
    def from_dict(d):
        return Conta(d["usuario"], d["nome"], d["senha_hash"], d.get("tipo", "ALUNO"), d.get("matricula"))


def salvar_contas(contas, caminho):
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump([c.to_dict() for c in contas], f, ensure_ascii=False, indent=2)


def carregar_contas(caminho):
    with open(caminho, encoding="utf-8") as f:
        return [Conta.from_dict(d) for d in json.load(f)]
