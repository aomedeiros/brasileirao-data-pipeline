"""Acesso ao DuckDB.

Observação sobre o DuckDB 2.x: ``execute(...).fetchone()`` deixa um resultado
pendente na conexão e bloqueia o comando seguinte. Por isso as leituras deste
projeto usam ``fetchall()``.
"""

from collections.abc import Callable
from pathlib import Path

import duckdb


def conectar(
    caminho: str | Path = ":memory:", somente_leitura: bool = False
) -> duckdb.DuckDBPyConnection:
    """Abre (ou cria) o banco DuckDB, criando a pasta de destino se necessário."""
    if somente_leitura:
        return duckdb.connect(str(caminho), read_only=True)
    if str(caminho) != ":memory:":
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(caminho))


def contar(con: duckdb.DuckDBPyConnection, tabela: str) -> int:
    return con.execute(f"SELECT count(*) FROM {tabela}").fetchall()[0][0]


def listar_tabelas(con: duckdb.DuckDBPyConnection, schema: str) -> list[str]:
    linhas = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = ? ORDER BY table_name",
        [schema],
    ).fetchall()
    return [nome for (nome,) in linhas]


def executar_scripts(
    con: duckdb.DuckDBPyConnection,
    pasta: Path,
    verificar: Callable[[duckdb.DuckDBPyConnection], object] | None = None,
) -> list[str]:
    """Executa, em ordem alfabética, todos os ``*.sql`` de uma pasta.

    Os scripts rodam em uma única transação. Se ``verificar`` for informado,
    ele é chamado antes do COMMIT; qualquer exceção (de um script ou da
    verificação) desfaz a transação inteira, preservando a versão anterior.
    """
    scripts = sorted(Path(pasta).glob("*.sql"))
    if not scripts:
        raise FileNotFoundError(f"Nenhum script SQL encontrado em {pasta}")
    con.execute("BEGIN TRANSACTION")
    try:
        for script in scripts:
            con.execute(script.read_text(encoding="utf-8"))
        if verificar is not None:
            verificar(con)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return [s.name for s in scripts]
