"""Acesso ao DuckDB.

Observação sobre o DuckDB 2.x: ``execute(...).fetchone()`` deixa um resultado
pendente na conexão e bloqueia o comando seguinte. Por isso as leituras deste
projeto usam ``fetchall()``.
"""

from pathlib import Path

import duckdb


def conectar(caminho: str | Path = ":memory:") -> duckdb.DuckDBPyConnection:
    """Abre (ou cria) o banco DuckDB, criando a pasta de destino se necessário."""
    if str(caminho) != ":memory:":
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(caminho))


def contar(con: duckdb.DuckDBPyConnection, tabela: str) -> int:
    return con.execute(f"SELECT count(*) FROM {tabela}").fetchall()[0][0]
