import json

from contas import hash_senha
from no import No


def test_login_com_senha_certa(tmp_path):
    no = No(str(tmp_path / "dados"), dificuldade=1)
    conta = no.autenticar("reitoria", "reitoria123")
    assert conta is not None and conta.usuario == "reitoria"


def test_login_com_senha_errada_ou_usuario_inexistente(tmp_path):
    no = No(str(tmp_path / "dados"), dificuldade=1)
    assert no.autenticar("reitoria", "errada") is None
    assert no.autenticar("ninguem", "reitoria123") is None


def test_caio_e_lucas_sao_alunos(tmp_path):
    no = No(str(tmp_path / "dados"), dificuldade=1)
    assert {c.nome for c in no.listar_alunos()} == {"Caio", "Lucas"}
    assert no.papel_exibicao("caio") == "ALUNO"
    assert no.papel_exibicao("sec_est") == "EMISSOR"
    assert no.papel_exibicao("reitoria") == "ADMINISTRADOR"


def test_cadastro_de_aluno(tmp_path):
    no = No(str(tmp_path / "dados"), dificuldade=1)
    nova = no.registrar_aluno("Ana Souza", "2021001", "ana123")
    assert nova.usuario == "aluno_2021001"
    assert no.autenticar("aluno_2021001", "ana123") is not None
    assert no.registrar_aluno("Outra Ana", "2021001", "x") is None   # matrícula repetida
    assert no.registrar_aluno("", "2021002", "x") is None            # campo vazio


def test_conta_cadastrada_continua_depois_de_reiniciar(tmp_path):
    pasta = str(tmp_path / "dados")
    No(pasta, dificuldade=1).registrar_aluno("Ana Souza", "2021001", "ana123")
    assert No(pasta, dificuldade=1).autenticar("aluno_2021001", "ana123") is not None


def test_senha_fica_salva_so_como_hash(tmp_path):
    no = No(str(tmp_path / "dados"), dificuldade=1)
    with open(no.arq_contas, encoding="utf-8") as f:
        texto = f.read()
    assert "reitoria123" not in texto
    assert hash_senha("reitoria123") in texto
    assert json.loads(texto)[0]["usuario"] == "reitoria"
