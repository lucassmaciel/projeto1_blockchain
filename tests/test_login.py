from pathlib import Path
import json

import no
from carteira import Carteira, salvar_carteiras
from no import No


def test_listar_usuarios_do_sistema_e_autenticar(tmp_path):
    pasta = tmp_path / "demo"
    no_obj = No(str(pasta), dificuldade=1)

    usuarios = no_obj.listar_usuarios()
    assert len(usuarios) >= 4

    papels = {u["papel"] for u in usuarios}
    assert {"ADMINISTRADOR", "EMISSOR", "SEM PERMISSÃO"}.issubset(papels)

    admin = next(u for u in usuarios if u["papel"] == "ADMINISTRADOR")
    carteira = no_obj.autenticar(admin["endereco"], admin["senha"])

    assert carteira is not None
    assert carteira.endereco == admin["endereco"]


def test_recria_carteiras_demo_quando_arquivo_legacy_esta_malformado(tmp_path):
    pasta = tmp_path / "demo"
    pasta.mkdir()

    (pasta / "carteiras.json").write_text(json.dumps([
        {
            "nome": "Reitoria UEA (administrador)",
            "endereco": "0xabc",
            "chave_privada": "00" * 32,
        }
    ]), encoding="utf-8")

    no_obj = No(str(pasta), dificuldade=1)

    assert no_obj.listar_usuarios()
    assert {u["nome"] for u in no_obj.listar_usuarios()} >= {
        "Reitoria UEA (administrador)",
        "Secretaria Acadêmica EST/UEA",
    }


def test_recria_carteiras_quando_senha_foi_alterada_e_arquivo_stale_persistiu(tmp_path, monkeypatch):
    pasta = tmp_path / "demo"
    pasta.mkdir()

    contas_antigas = [
        ("Reitoria UEA (administrador)", "reitoria123"),
        ("Secretaria Acadêmica EST/UEA", "est-2026"),
        ("Secretaria Acadêmica ESA/UEA", "esa-2026"),
        ("Carlos — aluno (sem permissão)", "carlos123"),
    ]
    salvar_carteiras([Carteira.criar(nome, senha) for nome, senha in contas_antigas], str(pasta / "carteiras.json"))

    senhas_novas = [
        ("Reitoria UEA (administrador)", "nova-reitoria-2026"),
        ("Secretaria Acadêmica EST/UEA", "nova-est-2026"),
        ("Secretaria Acadêmica ESA/UEA", "nova-esa-2026"),
        ("Carlos — aluno (sem permissão)", "nova-carlos-2026"),
    ]
    monkeypatch.setattr(no, "CONTAS_PADRAO", senhas_novas)

    no_obj = No(str(pasta), dificuldade=1)

    admin = next(u for u in no_obj.listar_usuarios() if u["nome"] == "Reitoria UEA (administrador)")
    assert no_obj.autenticar(admin["endereco"], "nova-reitoria-2026") is not None
    assert no_obj.autenticar(admin["endereco"], "reitoria123") is None


def test_registra_novo_aluno_com_matricula_e_login(tmp_path):
    pasta = tmp_path / "demo"
    no_obj = No(str(pasta), dificuldade=1)

    cadastro = no_obj.registrar_usuario("Carlos Santos", "2026001", "carlos123")

    assert cadastro is not None
    assert cadastro["matricula"] == "2026001"

    usuario = next(u for u in no_obj.listar_usuarios() if u["nome"] == "Carlos Santos")
    assert usuario["matricula"] == "2026001"
    assert no_obj.autenticar(cadastro["endereco"], "carlos123") is not None


def test_admin_autentica_com_senha_fixa_conhecida(tmp_path):
    pasta = tmp_path / "demo"
    no_obj = No(str(pasta), dificuldade=1)

    admin = next(u for u in no_obj.listar_usuarios() if u["papel"] == "ADMINISTRADOR")
    assert no_obj.autenticar(admin["endereco"], "reitoria123") is not None
    assert no_obj.autenticar(admin["endereco"], "senha-errada") is None


def test_contas_padrao_usam_senhas_fixas():
    senhas = {nome: senha for nome, senha in no.CONTAS_PADRAO}
    assert senhas["Reitoria UEA (administrador)"] == "reitoria123"
    assert senhas["Secretaria Acadêmica EST/UEA"] == "est-2026"
    assert senhas["Secretaria Acadêmica ESA/UEA"] == "esa-2026"
    assert senhas["Carlos — aluno (sem permissão)"] == "carlos123"
