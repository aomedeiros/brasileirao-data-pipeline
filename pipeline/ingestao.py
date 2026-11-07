"""Camada RAW: cópia fiel dos quatro CSVs de origem no schema ``raw`` do DuckDB.

Regras:
- os CSVs são apenas lidos, nunca alterados;
- todas as colunas entram como texto (VARCHAR), com os nomes originais;
- nenhum valor é convertido: campos vazios continuam como texto vazio ('');
- antes de carregar, confere se os quatro arquivos existem e se os cabeçalhos
  batem com o contrato de ``config.FONTES``;
- depois de carregar, confere se o número de linhas é igual ao de registros do arquivo;
- a carga é transacional e substitui as tabelas (``CREATE OR REPLACE``), então
  pode ser reexecutada sem duplicar dados.

Uso:
    uv run python -m pipeline.ingestao
    uv run python -m pipeline.ingestao --db caminho/banco.duckdb --raw pasta/dos/csvs
"""

import argparse
import csv
import sys
from pathlib import Path

import duckdb

from pipeline.config import DB_PADRAO, DIR_RAW, FONTES, Fonte
from pipeline.db import conectar, contar

# O DuckDB trata campos vazios como NULL por padrão. Para manter a RAW idêntica
# ao arquivo, aspas vazias ("") são lidas como texto vazio (allow_quoted_nulls)
# e o marcador de nulo é um texto que não ocorre nos dados, de modo que campos
# vazios sem aspas também permanecem como ''.
_MARCADOR_SEM_NULO = "<<__RAW_SEM_NULO__>>"


class ArquivosAusentesError(FileNotFoundError):
    def __init__(self, ausentes: list[Path]):
        self.ausentes = ausentes
        lista = "\n".join(f"  - {p}" for p in ausentes)
        super().__init__(f"{len(ausentes)} arquivo(s) de origem ausente(s):\n{lista}")


class IngestaoError(ValueError):
    pass


def verificar_arquivos(dir_raw: Path) -> None:
    """Falha antes de qualquer carga se algum dos quatro CSVs não existir."""
    ausentes = [
        Path(dir_raw) / f.arquivo
        for f in FONTES.values()
        if not (Path(dir_raw) / f.arquivo).is_file()
    ]
    if ausentes:
        raise ArquivosAusentesError(ausentes)


def ler_cabecalho(caminho: Path) -> tuple[str, ...]:
    with open(caminho, newline="", encoding="utf-8") as f:
        return tuple(next(csv.reader(f)))


def contar_registros_csv(caminho: Path) -> int:
    """Conta registros (não linhas físicas), respeitando campos com quebra de linha."""
    with open(caminho, newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def verificar_cabecalhos(dir_raw: Path) -> None:
    for fonte in FONTES.values():
        encontrado = ler_cabecalho(Path(dir_raw) / fonte.arquivo)
        if encontrado != fonte.colunas:
            raise IngestaoError(
                f"Cabeçalho inesperado em {fonte.arquivo}.\n  esperado:   {fonte.colunas}\n  encontrado: {encontrado}"
            )


def carregar_tabela(
    con: duckdb.DuckDBPyConnection, tabela: str, fonte: Fonte, dir_raw: Path
) -> int:
    caminho = Path(dir_raw) / fonte.arquivo
    literal = caminho.resolve().as_posix().replace("'", "''")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE raw.{tabela} AS
        SELECT *
        FROM read_csv(
            '{literal}',
            header = true,
            all_varchar = true,
            delim = ',',
            quote = '"',
            escape = '"',
            encoding = 'utf-8',
            allow_quoted_nulls = false,
            nullstr = '{_MARCADOR_SEM_NULO}'
        )
        """
    )
    carregados = contar(con, f"raw.{tabela}")
    esperados = contar_registros_csv(caminho)
    if carregados != esperados:
        raise IngestaoError(
            f"raw.{tabela}: {carregados} linhas carregadas, mas o arquivo tem {esperados} registros"
        )
    return carregados


def ingerir(con: duckdb.DuckDBPyConnection, dir_raw: Path = DIR_RAW) -> dict[str, int]:
    """Carrega os quatro CSVs no schema raw e devolve a contagem por tabela.

    Tudo ocorre em uma transação: se qualquer arquivo falhar, nenhuma tabela
    RAW é alterada.
    """
    verificar_arquivos(dir_raw)
    verificar_cabecalhos(dir_raw)

    con.execute("BEGIN TRANSACTION")
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        contagens = {
            tabela: carregar_tabela(con, tabela, fonte, dir_raw)
            for tabela, fonte in FONTES.items()
        }
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return contagens


def formatar_contagens(contagens: dict[str, int]) -> str:
    def numero(n: int) -> str:
        return f"{n:,}".replace(",", ".")

    linhas = [f"  raw.{tabela:<14} {numero(n):>8}" for tabela, n in contagens.items()]
    linhas.append(f"  {'TOTAL':<18} {numero(sum(contagens.values())):>8}")
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingestão dos CSVs na camada RAW")
    parser.add_argument(
        "--db", default=str(DB_PADRAO), help="arquivo DuckDB de destino"
    )
    parser.add_argument(
        "--raw", default=str(DIR_RAW), help="pasta com os CSVs de origem"
    )
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    try:
        # Verifica os arquivos antes de abrir o banco, para não criar um .duckdb vazio à toa.
        verificar_arquivos(Path(args.raw))
        con = conectar(args.db)
        try:
            contagens = ingerir(con, Path(args.raw))
        finally:
            con.close()
    except (ArquivosAusentesError, IngestaoError) as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 1

    print(f"Banco: {args.db}")
    print("Camada RAW carregada:")
    print(formatar_contagens(contagens))
    return 0


if __name__ == "__main__":
    sys.exit(main())
