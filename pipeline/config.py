"""Configuração central: caminhos do projeto e contrato dos arquivos de origem."""

from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_RAW = RAIZ / "data" / "raw"
DB_PADRAO = RAIZ / "data" / "brasileirao.duckdb"
DIR_SQL = RAIZ / "sql"


@dataclass(frozen=True)
class Fonte:
    """Um CSV de origem e o cabeçalho exato esperado nele."""

    arquivo: str
    colunas: tuple[str, ...]


# Tabela da camada RAW -> arquivo de origem.
# Os nomes de coluna são os do CSV, sem correções (inclusive "rodata").
FONTES: dict[str, Fonte] = {
    "partidas": Fonte(
        "campeonato-brasileiro-full.csv",
        (
            "ID", "rodata", "data", "hora", "mandante", "visitante",
            "formacao_mandante", "formacao_visitante", "tecnico_mandante", "tecnico_visitante",
            "vencedor", "arena", "mandante_Placar", "visitante_Placar",
            "mandante_Estado", "visitante_Estado", "arrecadacao",
        ),
    ),
    "estatisticas": Fonte(
        "campeonato-brasileiro-estatisticas-full.csv",
        (
            "partida_id", "rodata", "clube", "chutes", "chutes_no_alvo", "posse_de_bola",
            "passes", "precisao_passes", "faltas", "cartao_amarelo", "cartao_vermelho",
            "impedimentos", "escanteios",
        ),
    ),
    "gols": Fonte(
        "campeonato-brasileiro-gols.csv",
        ("partida_id", "rodata", "clube", "atleta", "minuto", "tipo_de_gol"),
    ),
    "cartoes": Fonte(
        "campeonato-brasileiro-cartoes.csv",
        ("partida_id", "rodata", "clube", "cartao", "atleta", "num_camisa", "posicao", "minuto"),
    ),
}  # fmt: skip
