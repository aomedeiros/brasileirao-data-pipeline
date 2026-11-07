"""Camada REFINED: tipagem, limpeza e relacionamentos a partir da camada RAW.

A lógica fica nos scripts ``sql/refined/*.sql``, executados em ordem alfabética
dentro de uma transação. Este módulo verifica os pré-requisitos, executa os
scripts e devolve as contagens resultantes.

Uso (requer a camada RAW já carregada):
    uv run python -m pipeline.transformacao
    uv run python -m pipeline.transformacao --db caminho/banco.duckdb
"""

import argparse
import sys
from pathlib import Path

import duckdb

from pipeline.config import DB_PADRAO, DIR_SQL, FONTES
from pipeline.db import conectar, contar, executar_scripts, listar_tabelas


class CamadaRawAusenteError(RuntimeError):
    pass


def verificar_raw(con: duckdb.DuckDBPyConnection) -> None:
    faltando = sorted(set(FONTES) - set(listar_tabelas(con, "raw")))
    if faltando:
        tabelas = ", ".join(f"raw.{t}" for t in faltando)
        raise CamadaRawAusenteError(
            f"Camada RAW incompleta (faltam: {tabelas}). "
            "Execute antes: uv run python -m pipeline.ingestao"
        )


def transformar(
    con: duckdb.DuckDBPyConnection, dir_sql: Path = DIR_SQL / "refined"
) -> dict[str, int]:
    """Constrói o schema refined e devolve a contagem por tabela."""
    verificar_raw(con)
    con.execute("CREATE SCHEMA IF NOT EXISTS refined")
    executar_scripts(con, dir_sql)
    return {t: contar(con, f"refined.{t}") for t in listar_tabelas(con, "refined")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Construção da camada REFINED")
    parser.add_argument("--db", default=str(DB_PADRAO), help="arquivo DuckDB")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if not Path(args.db).is_file():
        print(f"ERRO: banco não encontrado: {args.db}", file=sys.stderr)
        print("Execute antes: uv run python -m pipeline.ingestao", file=sys.stderr)
        return 1

    con = conectar(args.db)
    try:
        contagens = transformar(con)
    except CamadaRawAusenteError as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 1
    finally:
        con.close()

    print(f"Banco: {args.db}")
    print("Camada REFINED construída:")
    for tabela, n in contagens.items():
        print(f"  refined.{tabela:<14} {n:>8,}".replace(",", "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
