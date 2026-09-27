# carteira.py
# Identidade de cada participante da rede: um par de chaves Ed25519, protegida por senha.
#  - a chave PRIVADA assina as transações e fica CIFRADA em disco (Fernet + PBKDF2);
#    ela só existe em texto puro na memória depois que a senha certa é informada
#    (ver `desbloquear`) — isso é o que implementa o "login" de cada usuário.
#  - a chave PÚBLICA permite a qualquer um conferir a assinatura;
#  - o ENDEREÇO (0x + 40 hex) é derivado da chave pública, como no Ethereum.
#
# Obs.: nesta demo local, "desbloquear" uma carteira é o equivalente a logar como
# aquela conta. Em produção, cada instituição escolheria e guardaria sua própria
# senha — aqui usamos senhas de demonstração (ver README, seção "Credenciais de
# demonstração") só para o professor conseguir testar cada papel.
import base64
import hashlib
import json
import os

from cryptography.exceptions import InvalidSignature
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERACOES_PBKDF2 = 200_000


def endereco_de(chave_publica_hex):
    return "0x" + hashlib.sha256(bytes.fromhex(chave_publica_hex)).hexdigest()[:40]


def verificar_assinatura(chave_publica_hex, mensagem, assinatura_hex):
    try:
        chave = Ed25519PublicKey.from_public_bytes(bytes.fromhex(chave_publica_hex))
        chave.verify(bytes.fromhex(assinatura_hex), mensagem.encode("utf-8"))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def _chave_fernet(senha, sal):
    """Deriva uma chave simétrica (32 bytes, base64 url-safe) a partir da senha + sal."""
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sal, iterations=ITERACOES_PBKDF2)
    return base64.urlsafe_b64encode(kdf.derive(senha.encode("utf-8")))


class Carteira:
    """
    Uma carteira pode existir em dois estados:
      - BLOQUEADA:    criada via `from_dict` — tem nome/endereço/chave pública
                      (informação pública, ok para listar na interface), mas
                      NÃO consegue assinar nada (`self._privada is None`).
      - DESBLOQUEADA: criada via `criar()`, ou depois de um `desbloquear()` com
                      a senha certa — tem a chave privada em memória e assina.

    IMPORTANTE (concorrência no Streamlit): o nó (`No`) é compartilhado entre
    todas as sessões/usuários do servidor. Por isso `no.carteiras` guarda só
    carteiras BLOQUEADAS. Cada login deve chamar `No.autenticar(...)`, que
    devolve uma CÓPIA nova e isolada — nunca desbloqueie diretamente uma
    carteira que veio de `no.carteiras`, ou um usuário destrava a chave de
    outro.
    """

    def __init__(self, nome, endereco, chave_publica, sal, cifrada, privada=None):
        self.nome = nome
        self.endereco = endereco
        self.chave_publica = chave_publica
        self._sal = sal
        self._cifrada = cifrada
        self._privada = privada  # None = bloqueada

    # ---------------------------------------------------------------- estado
    @property
    def bloqueada(self):
        return self._privada is None

    def assinar(self, mensagem):
        if self.bloqueada:
            raise RuntimeError(f"carteira '{self.nome}' está bloqueada: informe a senha antes de assinar")
        return self._privada.sign(mensagem.encode("utf-8")).hex()

    def desbloquear(self, senha):
        """Tenta decifrar a chave privada com a senha informada.
        Devolve True (e passa a poder assinar) ou False (senha errada)."""
        try:
            bruta = Fernet(_chave_fernet(senha, self._sal)).decrypt(self._cifrada)
        except InvalidToken:
            return False
        self._privada = Ed25519PrivateKey.from_private_bytes(bruta)
        return True

    def bloquear(self):
        """Descarta a chave privada da memória (usado no logout)."""
        self._privada = None

    # ------------------------------------------------------------- criação
    @staticmethod
    def criar(nome, senha):
        """Gera um novo par de chaves e devolve a carteira já DESBLOQUEADA
        (uso único, no momento da criação da conta)."""
        privada = Ed25519PrivateKey.generate()
        publica = privada.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
        sal = os.urandom(16)
        bruta = privada.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        cifrada = Fernet(_chave_fernet(senha, sal)).encrypt(bruta)
        return Carteira(nome, endereco_de(publica), publica, sal, cifrada, privada)

    # -------------------------------------------------------- (de)serialização
    def to_dict(self):
        """Nunca inclui a chave privada em texto puro — só a versão cifrada."""
        return {
            "nome": self.nome,
            "endereco": self.endereco,
            "chave_publica": self.chave_publica,
            "sal": self._sal.hex(),
            "chave_privada_cifrada": self._cifrada.hex(),
        }

    @staticmethod
    def from_dict(d):
        """Sempre devolve uma carteira BLOQUEADA — quem precisar assinar deve
        chamar `.desbloquear(senha)` (normalmente via `No.autenticar`).

        Também aceita o formato legado, que armazenava apenas a chave privada em texto
        puro (não criptografado). Esse caso é convertido em um objeto válido o quanto
        antes pela inicialização do nó."""
        if "chave_publica" in d and "sal" in d and "chave_privada_cifrada" in d:
            return Carteira(d["nome"], d["endereco"], d["chave_publica"],
                            bytes.fromhex(d["sal"]), bytes.fromhex(d["chave_privada_cifrada"]))

        if "chave_privada" in d:
            privada = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(d["chave_privada"]))
            publica = privada.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
            return Carteira(d["nome"], d["endereco"], publica, b"", b"")

        raise KeyError("Formato de carteira inválido: faltam campos obrigatórios")


def salvar_carteiras(carteiras, caminho):
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump([c.to_dict() for c in carteiras], f, ensure_ascii=False, indent=2)


def carregar_carteiras_bruto(caminho):
    """Lê os dicionários crus do disco (sem instanciar `Carteira`). O nó usa isso
    para conseguir gerar, a cada tentativa de login, uma cópia nova e isolada da
    carteira — em vez de desbloquear um objeto compartilhado entre sessões."""
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)