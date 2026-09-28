import pytest

from contrato import hash_arquivo, hash_titular
from no import No


@pytest.fixture
def no(tmp_path):
    """Nó novo, com dados em pasta temporária e dificuldade baixa para os testes rodarem rápido.

    Atalho de teste: `no.enviar(usuario, tipo, payload)` recebe o nome do usuário.
    No app real, quem chama é a conta que fez login.
    """
    n = No(str(tmp_path / "dados"), dificuldade=2)
    enviar_original = n.enviar
    n.enviar = lambda usuario, tipo, payload: enviar_original(n.conta(usuario), tipo, payload)
    return n


@pytest.fixture
def contas():
    """Reitoria (admin), secretarias EST e ESA (emissores no gênesis) e Caio (aluno, sem permissão no contrato)."""
    return {"admin": "reitoria", "est": "sec_est", "esa": "sec_esa", "aluno": "caio"}


@pytest.fixture
def cert():
    return {
        "codigo": "UEA-2026-0001",
        "documento_hash": hash_arquivo(b"PDF do diploma da Ana"),
        "titular_hash": hash_titular("Ana Souza", "2021001"),
        "curso": "Sistemas de Informação",
        "carga_horaria": 3200,
        "data_conclusao": "2026-07-15",
    }
