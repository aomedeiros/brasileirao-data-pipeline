import hashlib

import pytest

from pipeline import config
from pipeline.db import conectar
from pipeline.ingestao import (
    ArquivosAusentesError,
    IngestaoError,
    contar_registros_csv,
    ingerir,
    main,
)
from pipeline.qualidade import FalhaDeQualidadeError
from test.conftest import LINHAS, NBSP, assinatura, escalar, escrever_csv


def test_carrega_as_quatro_tabelas(con_raw):
    for tabela, linhas in LINHAS.items():
        assert escalar(con_raw, f"SELECT count(*) FROM raw.{tabela}") == len(linhas)


def test_raw_e_copia_fiel_sem_conversao(con_raw):
    # texto vazio continua texto vazio, NBSP e espaços preservados, nada vira NULL
    assert (
        escalar(con_raw, "SELECT formacao_mandante FROM raw.partidas WHERE ID = '2'")
        == ""
    )
    assert (
        escalar(con_raw, "SELECT arena FROM raw.partidas WHERE ID = '1'")
        == f"{NBSP}Estádio Alfa"
    )
    assert (
        escalar(con_raw, "SELECT arena FROM raw.partidas WHERE ID = '2'")
        == "Arena Beta "
    )
    assert escalar(
        con_raw,
        "SELECT posse_de_bola FROM raw.estatisticas WHERE partida_id = '3' AND clube = 'Alfa'",
    ) == ("None")
    assert (
        escalar(con_raw, "SELECT minuto FROM raw.gols WHERE tipo_de_gol = 'Penalty'")
        == "45+2"
    )


def test_raw_preserva_nomes_originais_das_colunas(con_raw):
    for tabela, fonte in config.FONTES.items():
        colunas = con_raw.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'raw' AND table_name = ? ORDER BY ordinal_position",
            [tabela],
        ).fetchall()
        assert tuple(c for (c,) in colunas) == fonte.colunas


def test_ingestao_nao_altera_os_csvs(dir_raw, caminho_db):
    def hashes():
        return {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in dir_raw.iterdir()
        }

    antes = hashes()
    ingerir(conectar(caminho_db), dir_raw)
    assert hashes() == antes


def test_reexecucao_substitui_sem_duplicar(con_raw, dir_raw):
    ingerir(con_raw, dir_raw)
    assert escalar(con_raw, "SELECT count(*) FROM raw.partidas") == len(
        LINHAS["partidas"]
    )


def test_arquivos_ausentes_sao_todos_informados(tmp_path):
    escrever_csv(
        tmp_path / config.FONTES["gols"].arquivo, config.FONTES["gols"].colunas, []
    )
    with pytest.raises(ArquivosAusentesError) as erro:
        ingerir(conectar(), tmp_path)
    assert {p.name for p in erro.value.ausentes} == {
        config.FONTES[t].arquivo for t in ("partidas", "estatisticas", "cartoes")
    }


def test_main_com_arquivo_ausente_nao_cria_banco(tmp_path, capsys):
    db = tmp_path / "nao_deve_existir.duckdb"
    assert main(["--raw", str(tmp_path), "--db", str(db)]) == 1
    assert "ausente" in capsys.readouterr().err
    assert not db.exists()


def test_cabecalho_divergente_e_rejeitado(dir_raw):
    fonte = config.FONTES["gols"]
    escrever_csv(
        dir_raw / fonte.arquivo,
        ("partida_id", "rodada", *fonte.colunas[2:]),
        LINHAS["gols"],
    )
    with pytest.raises(IngestaoError, match="Cabeçalho inesperado"):
        ingerir(conectar(), dir_raw)


def test_divergencia_de_contagem_desfaz_a_carga(con_raw, dir_raw, monkeypatch):
    antes = assinatura(con_raw, "raw")
    monkeypatch.setattr("pipeline.ingestao.contar_registros_csv", lambda _caminho: 999)
    with pytest.raises(IngestaoError, match="999 registros"):
        ingerir(con_raw, dir_raw)
    assert assinatura(con_raw, "raw") == antes


def test_contagem_respeita_campo_com_quebra_de_linha(tmp_path):
    arquivo = tmp_path / "x.csv"
    escrever_csv(arquivo, ["a", "b"], [["1", "texto com\nquebra"], ["2", "ok"]])
    assert contar_registros_csv(arquivo) == 2


def test_falha_de_qualidade_na_raw_preserva_a_versao_anterior(
    con_raw, dir_raw, monkeypatch
):
    antes = assinatura(con_raw, "raw")
    monkeypatch.setitem(
        config.EXPECTATIVAS,
        "linhas_raw",
        {**config.EXPECTATIVAS["linhas_raw"], "partidas": 99},
    )
    with pytest.raises(FalhaDeQualidadeError, match="raw.partidas tem 99 linhas"):
        ingerir(con_raw, dir_raw)
    assert assinatura(con_raw, "raw") == antes


def test_main_sucesso_e_falha_de_qualidade(dir_raw, caminho_db, monkeypatch, capsys):
    assert main(["--raw", str(dir_raw), "--db", str(caminho_db)]) == 0
    saida = capsys.readouterr().out
    assert "TOTAL" in saida and "aprovadas" in saida
    monkeypatch.setitem(
        config.EXPECTATIVAS,
        "linhas_raw",
        {**config.EXPECTATIVAS["linhas_raw"], "gols": 0},
    )
    assert main(["--raw", str(dir_raw), "--db", str(caminho_db)]) == 1
    assert "raw.gols tem 0 linhas" in capsys.readouterr().err
