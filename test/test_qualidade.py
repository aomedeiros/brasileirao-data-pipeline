"""Comportamento do módulo de qualidade: detecção, interrupção, ROLLBACK e execução avulsa.

Não reproduz as 84 verificações uma a uma; testa o mecanismo, provocando
falhas apenas em bancos temporários.
"""

import pytest

from pipeline import config
from pipeline.db import conectar
from pipeline.marts import construir_marts
from pipeline.qualidade import (
    FalhaDeQualidadeError,
    exigir_camada,
    main,
    verificacoes,
    verificar_camada,
)
from pipeline.transformacao import transformar
from test.conftest import assinatura


def test_catalogo_por_camada_e_tipo():
    contagem = {
        c: [v.tipo for v in verificacoes(c)] for c in ("raw", "refined", "marts")
    }
    assert {c: len(t) for c, t in contagem.items()} == {
        "raw": 7,
        "refined": 30,
        "marts": 47,
    }
    assert all(set(t) == {"I", "E"} for t in contagem.values())


def test_dados_ficticios_passam_em_todas_as_camadas(con):
    for camada in ("raw", "refined", "marts"):
        assert [
            r.verificacao.nome for r in verificar_camada(con, camada) if not r.ok
        ] == []


def test_violacao_de_invariante_e_detectada_e_descrita(con):
    con.execute(
        "INSERT INTO refined.gols (gol_id, partida_id, clube_id, gol_contra) VALUES (99, 999, 1, false)"
    )
    with pytest.raises(FalhaDeQualidadeError) as erro:
        exigir_camada(con, "refined")
    assert erro.value.camada == "refined"
    assert "gols: nenhuma referência a partida inexistente" in str(erro.value)
    assert all(not r.ok for r in erro.value.falhas)


def test_erro_de_sql_e_registrado_como_falha_e_nao_derruba_o_processo(con_refined):
    # a camada MARTS ainda não existe: as consultas sobre ela falham e viram resultados com erro
    resultados = verificar_camada(con_refined, "marts")
    com_erro = [r for r in resultados if r.erro]
    assert len(resultados) == 47 and com_erro and all(not r.ok for r in com_erro)
    assert all("marts" in r.erro for r in com_erro)
    with pytest.raises(FalhaDeQualidadeError, match="ERRO"):
        exigir_camada(con_refined, "marts")


def test_rollback_preserva_refined_anterior_quando_a_regra_falha(con_refined):
    antes = assinatura(con_refined, "refined")
    # origem passa a ter um gol de partida inexistente: a nova REFINED seria inválida
    con_refined.execute(
        "INSERT INTO raw.gols VALUES ('999', '1', 'Alfa', 'Atleta X', '10', '')"
    )
    with pytest.raises(FalhaDeQualidadeError, match="partida inexistente"):
        transformar(con_refined)
    assert assinatura(con_refined, "refined") == antes


def test_rollback_preserva_marts_anterior_quando_a_expectativa_falha(con, monkeypatch):
    antes = assinatura(con, "marts")
    monkeypatch.setitem(config.EXPECTATIVAS, "cobertura_gols_detalhados", (2029, 2031))
    with pytest.raises(FalhaDeQualidadeError, match="cobertura de gols"):
        construir_marts(con)
    assert assinatura(con, "marts") == antes


def test_execucao_avulsa_aprova_e_nao_altera_o_banco(con, caminho_db, capsys):
    con.close()
    leitura = conectar(caminho_db, somente_leitura=True)
    antes = {s: assinatura(leitura, s) for s in ("raw", "refined", "marts")}
    leitura.close()
    assert main(["--db", str(caminho_db)]) == 0
    saida = capsys.readouterr().out
    assert (
        "RAW        7/7" in saida
        and "REFINED   30/30" in saida
        and "MARTS     47/47" in saida
    )
    leitura = conectar(caminho_db, somente_leitura=True)
    assert {s: assinatura(leitura, s) for s in ("raw", "refined", "marts")} == antes
    leitura.close()


def test_execucao_avulsa_por_camada_aponta_a_falha(con, caminho_db, capsys):
    con.execute(
        "UPDATE marts.estatisticas_por_resultado SET media_chutes = media_chutes + 0.01 "
        "WHERE temporada = 2031 AND resultado = 'vitoria' AND mando = 'mandante'"
    )
    con.close()
    assert main(["--db", str(caminho_db), "--camada", "marts"]) == 1
    saida = capsys.readouterr().out
    assert "media_chutes: ROUND_HALF_UP exato" in saida and "RAW" not in saida


def test_execucao_avulsa_com_banco_inexistente(tmp_path):
    assert main(["--db", str(tmp_path / "nao_existe.duckdb")]) == 1
