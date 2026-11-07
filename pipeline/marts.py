"""Camada MARTS: tabelas analíticas construídas a partir da camada REFINED.

A lógica fica nos scripts ``sql/marts/*.sql``, executados em ordem alfabética
dentro de uma transação (``01_partida_clube`` é a base das demais).

Uso (requer a camada REFINED já construída):
    uv run python -m pipeline.marts
    uv run python -m pipeline.marts --db caminho/banco.duckdb
"""

import argparse
import sys
from pathlib import Path

import duckdb

from pipeline.config import DB_PADRAO, DIR_SQL
from pipeline.db import conectar, contar, executar_scripts, listar_tabelas

TABELAS_REFINED = ("clubes", "partidas", "estatisticas", "gols", "cartoes")


class CamadaRefinedAusenteError(RuntimeError):
    pass


def verificar_refined(con: duckdb.DuckDBPyConnection) -> None:
    faltando = sorted(set(TABELAS_REFINED) - set(listar_tabelas(con, "refined")))
    if faltando:
        tabelas = ", ".join(f"refined.{t}" for t in faltando)
        raise CamadaRefinedAusenteError(
            f"Camada REFINED incompleta (faltam: {tabelas}). "
            "Execute antes: uv run python -m pipeline.transformacao"
        )


def construir_marts(
    con: duckdb.DuckDBPyConnection, dir_sql: Path = DIR_SQL / "marts"
) -> dict[str, int]:
    """Constrói o schema marts e devolve a contagem por tabela."""
    verificar_refined(con)
    con.execute("CREATE SCHEMA IF NOT EXISTS marts")
    executar_scripts(con, dir_sql)
    return {t: contar(con, f"marts.{t}") for t in listar_tabelas(con, "marts")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Construção da camada MARTS")
    parser.add_argument("--db", default=str(DB_PADRAO), help="arquivo DuckDB")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if not Path(args.db).is_file():
        print(f"ERRO: banco não encontrado: {args.db}", file=sys.stderr)
        print("Execute antes: ingestao e transformacao", file=sys.stderr)
        return 1

    con = conectar(args.db)
    try:
        contagens = construir_marts(con)
    except CamadaRefinedAusenteError as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 1
    finally:
        con.close()

    print(f"Banco: {args.db}")
    print("Camada MARTS construída:")
    for tabela, n in contagens.items():
        print(f"  marts.{tabela:<28} {n:>8,}".replace(",", "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
