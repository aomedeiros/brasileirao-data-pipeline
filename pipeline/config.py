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

# Expectativas específicas desta versão do dataset, conferidas pelas
# verificações de qualidade (tipo "E"). São bloqueantes: se a origem mudar,
# o pipeline falha até que estes valores sejam revistos explicitamente.
EXPECTATIVAS: dict = {
    "linhas_raw": {
        "partidas": 9165,
        "estatisticas": 18330,
        "gols": 10820,
        "cartoes": 20953,
    },
    "clubes": 46,
    "primeira_temporada": 2003,
    "ultima_temporada": 2025,
    "partidas_por_temporada": {2020: 380, 2021: 380},
    "anos_com_jogos_em_jan_fev": (2021,),
    "estatisticas_disponiveis": 7580,
    "passes_convertidos_em_nulo": 7,
    "cobertura_gols_detalhados": (2014, 2025),
    "cobertura_cartoes_detalhados": (2014, 2024),
}
