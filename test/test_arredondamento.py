"""Arredondamento oficial ROUND_HALF_UP (sql/marts/00_funcoes.sql) e a referência em Python."""

import random
from decimal import Decimal

import duckdb
import pytest

from pipeline.config import DIR_SQL
from pipeline.qualidade import meio_para_cima


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect()
    c.execute("CREATE SCHEMA marts")
    c.execute((DIR_SQL / "marts" / "00_funcoes.sql").read_text(encoding="utf-8"))
    yield c
    c.close()


def arred(con, casas, numerador, denominador):
    return con.execute(
        f"SELECT marts.arredondar_{casas}({numerador}, {denominador})"
    ).fetchall()[0][0]


@pytest.mark.parametrize(
    ("numerador", "denominador", "esperado"),
    [
        (2127, 200, "10.64"),  # 10,635: meio exato
        (29, 200, "0.15"),  # 0,145: round(DOUBLE) do DuckDB dava 0,14
        (201, 200, "1.01"),  # 1,005
        (125, 1000, "0.13"),  # 0,125
        (10, 2, "5.00"),  # inteiro
        (1, 3, "0.33"),  # fração periódica
        (2, 3, "0.67"),
        (0, 5, "0.00"),  # zero
    ],
)
def test_duas_casas(con, numerador, denominador, esperado):
    valor = arred(con, 2, numerador, denominador)
    assert isinstance(valor, Decimal) and str(valor) == esperado


@pytest.mark.parametrize(
    ("numerador", "denominador", "esperado"),
    [
        (105, 100, "1.1"),
        (1015, 1000, "1.0"),
        (25, 100, "0.3"),
        (4182, 10, "418.2"),
        (0, 9, "0.0"),
    ],
)
def test_uma_casa(con, numerador, denominador, esperado):
    assert str(arred(con, 1, numerador, denominador)) == esperado


def test_tipos_decimais(con):
    tipos = con.execute(
        "SELECT typeof(marts.arredondar_2(1, 3)), typeof(marts.arredondar_1(1, 3))"
    ).fetchall()[0]
    assert tipos == ("DECIMAL(10,2)", "DECIMAL(10,1)")


@pytest.mark.parametrize("args", ["NULL, 5", "5, NULL", "5, 0"])
def test_nulo_ou_denominador_zero_devolve_nulo(con, args):
    assert con.execute(f"SELECT marts.arredondar_2({args})").fetchall()[0][0] is None


@pytest.mark.parametrize(
    ("args", "mensagem"),
    [
        ("-1, 5", "não negativos"),
        ("1, -5", "não negativos"),
        ("CAST(1.5 AS DECIMAL(3,1)), 2", "inteiros"),
    ],
)
def test_premissas_violadas_interrompem(con, args, mensagem):
    with pytest.raises(duckdb.Error, match=mensagem):
        con.execute(f"SELECT marts.arredondar_2({args})").fetchall()


def test_funcao_sql_igual_a_referencia_python_em_casos_aleatorios(con):
    gerador = random.Random(2026)  # semente fixa: reproduzível
    pares = [(gerador.randint(0, 50_000), gerador.randint(1, 900)) for _ in range(2000)]
    valores = ", ".join(f"({n}, {d})" for n, d in pares)
    linhas = con.execute(
        f"SELECT n, d, marts.arredondar_2(n, d), marts.arredondar_1(n, d) FROM (VALUES {valores}) t(n, d)"
    ).fetchall()
    divergentes = [
        r
        for r in linhas
        if r[2] != meio_para_cima(r[0], r[1], 2)
        or r[3] != meio_para_cima(r[0], r[1], 1)
    ]
    assert len(linhas) == 2000 and divergentes == []


def test_referencia_python():
    assert meio_para_cima(2127, 200, 2) == Decimal("10.64")
    assert meio_para_cima(29, 200, 2) == Decimal("0.15")
    assert meio_para_cima(Decimal("10521.00"), 200, 2) == Decimal("52.61")
    assert meio_para_cima(None, 5, 2) is None
    assert meio_para_cima(5, 0, 2) is None
