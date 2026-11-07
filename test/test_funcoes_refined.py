"""Funções de limpeza e conversão da REFINED (sql/refined/00_funcoes.sql)."""

from decimal import Decimal

import duckdb
import pytest

from pipeline.config import DIR_SQL
from test.conftest import NBSP


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect()
    c.execute("CREATE SCHEMA refined")
    c.execute((DIR_SQL / "refined" / "00_funcoes.sql").read_text(encoding="utf-8"))
    yield c
    c.close()


def f(con, expr):
    return con.execute(f"SELECT {expr}").fetchall()[0][0]


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("'Maracanã'", "Maracanã"),
        ("'  Maracanã  '", "Maracanã"),
        (f"'{NBSP}Brinco de Ouro'", "Brinco de Ouro"),
        ("'Arena da Baixada '", "Arena da Baixada"),
        ("''", None),
        ("'   '", None),
        ("'None'", None),
        ("NULL", None),
    ],
)
def test_texto(con, entrada, esperado):
    assert f(con, f"refined.texto({entrada})") == esperado


def test_texto_nao_altera_none_dentro_de_outro_texto(con):
    assert f(con, "refined.texto('Nonea')") == "Nonea"


def test_inteiro(con):
    assert f(con, "refined.inteiro('12')") == 12
    assert f(con, "refined.inteiro(' 7 ')") == 7
    assert f(con, "refined.inteiro('')") is None


def test_inteiro_falha_com_valor_nao_numerico(con):
    with pytest.raises(duckdb.ConversionException):
        f(con, "refined.inteiro('doze')")


def test_percentual(con):
    assert f(con, "refined.percentual('54%')") == Decimal("54.00")
    assert f(con, "refined.percentual('100%')") == Decimal("100.00")
    assert f(con, "refined.percentual('None')") is None
    assert f(con, "refined.percentual('')") is None


@pytest.mark.parametrize(
    ("minuto", "base", "acrescimo"),
    [("35", 35, 0), ("0", 0, 0), ("45+2", 45, 2), ("90+10", 90, 10), ("90", 90, 0)],
)
def test_minuto_e_acrescimo(con, minuto, base, acrescimo):
    assert f(con, f"refined.minuto_base('{minuto}')") == base
    assert f(con, f"refined.minuto_acrescimo('{minuto}')") == acrescimo


def test_minuto_vazio(con):
    assert f(con, "refined.minuto_base('')") is None
    assert f(con, "refined.minuto_acrescimo('')") == 0
