"""Integração com os CSVs reais de data/raw/, em banco temporário.

Ignorado automaticamente se os arquivos não estiverem presentes (por exemplo,
num clone do repositório, já que os CSVs não são versionados).
"""

from decimal import Decimal

import pytest

from pipeline import config
from pipeline.db import conectar
from pipeline.ingestao import ingerir
from pipeline.marts import construir_marts
from pipeline.qualidade import verificar_camada
from pipeline.transformacao import transformar
from test.conftest import EXPECTATIVAS_REAIS, escalar

pytestmark = [
    pytest.mark.integracao,
    pytest.mark.skipif(
        not all((config.DIR_RAW / f.arquivo).is_file() for f in config.FONTES.values()),
        reason="CSVs reais ausentes em data/raw/",
    ),
]


@pytest.fixture(scope="module")
def banco_real(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "EXPECTATIVAS", EXPECTATIVAS_REAIS)
        con = conectar(tmp_path_factory.mktemp("real") / "brasileirao.duckdb")
        contagens = ingerir(con, config.DIR_RAW)
        transformar(con)
        construir_marts(con)
        resultados = {c: verificar_camada(con, c) for c in ("raw", "refined", "marts")}
        yield con, contagens, resultados
        con.close()


def test_contagens_validadas_no_enunciado(banco_real):
    _, contagens, _ = banco_real
    assert contagens == {
        "partidas": 9165,
        "estatisticas": 18330,
        "gols": 10820,
        "cartoes": 20953,
    }


def test_as_84_verificacoes_passam_nos_dados_reais(banco_real):
    _, _, resultados = banco_real
    assert {c: len(r) for c, r in resultados.items()} == {
        "raw": 7,
        "refined": 30,
        "marts": 47,
    }
    assert [
        r.verificacao.nome for rs in resultados.values() for r in rs if not r.ok
    ] == []


def test_temporada_2020_terminou_em_2021(banco_real):
    con, _, _ = banco_real
    assert con.execute(
        "SELECT temporada, count(*), max(data_partida)::VARCHAR FROM refined.partidas "
        "WHERE temporada IN (2020, 2021) GROUP BY 1 ORDER BY 1"
    ).fetchall() == [(2020, 380, "2021-02-25"), (2021, 380, "2021-12-09")]


def test_caso_de_arredondamento_corrigido(banco_real):
    con, _, _ = banco_real
    assert escalar(
        con,
        "SELECT media_chutes_no_alvo FROM marts.estatisticas_por_resultado "
        "WHERE temporada = 2015 AND resultado = 'derrota' AND mando = 'visitante'",
    ) == Decimal("0.15")
