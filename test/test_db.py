import duckdb
import pytest

from pipeline.db import conectar, contar, executar_scripts, listar_tabelas


def test_conectar_em_arquivo_cria_a_pasta(tmp_path):
    caminho = tmp_path / "sub" / "pasta" / "banco.duckdb"
    conectar(caminho).close()
    assert caminho.exists()


def test_conexao_somente_leitura_impede_escrita(tmp_path):
    caminho = tmp_path / "banco.duckdb"
    con = conectar(caminho)
    con.execute("CREATE TABLE t AS SELECT 1 AS n")
    con.close()
    leitura = conectar(caminho, somente_leitura=True)
    assert leitura.execute("SELECT n FROM t").fetchall() == [(1,)]
    with pytest.raises(duckdb.Error):
        leitura.execute("INSERT INTO t VALUES (2)")
    leitura.close()


def test_contar_e_listar_tabelas():
    con = conectar()
    con.execute(
        "CREATE SCHEMA s; CREATE TABLE s.b AS SELECT * FROM range(3); CREATE TABLE s.a AS SELECT 1"
    )
    assert listar_tabelas(con, "s") == ["a", "b"]
    assert contar(con, "s.b") == 3


def test_executar_scripts_em_ordem_alfabetica(tmp_path):
    (tmp_path / "02_b.sql").write_text(
        "CREATE TABLE b AS SELECT n + 1 AS n FROM a;", encoding="utf-8"
    )
    (tmp_path / "01_a.sql").write_text(
        "CREATE TABLE a AS SELECT 1 AS n;", encoding="utf-8"
    )
    con = conectar()
    assert executar_scripts(con, tmp_path) == ["01_a.sql", "02_b.sql"]
    assert con.execute("SELECT n FROM b").fetchall() == [(2,)]


def test_executar_scripts_sem_arquivos_falha(tmp_path):
    with pytest.raises(FileNotFoundError):
        executar_scripts(conectar(), tmp_path)


def test_erro_em_um_script_desfaz_todos(tmp_path):
    con = conectar()
    con.execute("CREATE TABLE a AS SELECT 'versao anterior' AS v")
    (tmp_path / "01.sql").write_text(
        "CREATE OR REPLACE TABLE a AS SELECT 'nova' AS v;", encoding="utf-8"
    )
    (tmp_path / "02.sql").write_text(
        "SELECT * FROM tabela_inexistente;", encoding="utf-8"
    )
    with pytest.raises(duckdb.Error):
        executar_scripts(con, tmp_path)
    assert con.execute("SELECT v FROM a").fetchall() == [("versao anterior",)]


def test_falha_na_verificacao_desfaz_a_transacao(tmp_path):
    con = conectar()
    con.execute("CREATE TABLE a AS SELECT 'versao anterior' AS v")
    (tmp_path / "01.sql").write_text(
        "CREATE OR REPLACE TABLE a AS SELECT 'nova' AS v;", encoding="utf-8"
    )
    vistos = []

    def verificar(c):
        vistos.append(
            c.execute("SELECT v FROM a").fetchall()
        )  # enxerga a versão nova, ainda não confirmada
        raise RuntimeError("verificação reprovada")

    with pytest.raises(RuntimeError, match="reprovada"):
        executar_scripts(con, tmp_path, verificar=verificar)
    assert vistos == [[("nova",)]]
    assert con.execute("SELECT v FROM a").fetchall() == [("versao anterior",)]
