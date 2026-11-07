"""Fixtures com dados FICTÍCIOS que reproduzem as particularidades da origem.

Clubes: Alfa (SP), Beta (RJ), Gama (MG).

Temporada 2030 (com gols e cartões detalhados):
  1  10/05/2030  Alfa 2 x 1 Beta   arena com NBSP, arrecadação preenchida
  2  17/05/2030  Beta 0 x 0 Gama   empate ('-'), estatísticas não coletadas (zeros)
  3  20/01/2031  Gama 1 x 3 Alfa   jogo de janeiro: pertence à temporada 2030;
                                   Alfa com passes '0' e precisão 'None' (vira NULL)
Temporada 2031 (sem detalhamento de gols e cartões):
  4  10/05/2031  Alfa 2 x 0 Gama
  5  17/05/2031  Beta 2 x 0 Gama   Alfa e Beta empatam em todos os critérios

Os testes nunca usam o banco real do projeto: cada teste recebe uma pasta e
um banco temporários (tmp_path).
"""

import copy
import csv
from pathlib import Path

import pytest

from pipeline import config
from pipeline.db import conectar
from pipeline.ingestao import ingerir
from pipeline.marts import construir_marts
from pipeline.transformacao import transformar

NBSP = chr(0xA0)

# Cópia das expectativas reais, guardada antes de qualquer substituição pelos testes.
EXPECTATIVAS_REAIS = copy.deepcopy(config.EXPECTATIVAS)

# fmt: off
PARTIDAS = [
    ["1", "1", "10/05/2030", "16:00", "Alfa", "Beta", "4-3-3", "4-4-2", "T. Alfa", "T. Beta",
     "Alfa", f"{NBSP}Estádio Alfa", "2", "1", "SP", "RJ", "150000.50"],
    ["2", "2", "17/05/2030", "18:30", "Beta", "Gama", "", "", "", "",
     "-", "Arena Beta ", "0", "0", "RJ", "MG", ""],
    ["3", "3", "20/01/2031", "21:00", "Gama", "Alfa", "4-2-3-1", "4-3-3", "T. Gama", "T. Alfa",
     "Alfa", "Estádio Gama", "1", "3", "MG", "SP", ""],
    ["4", "1", "10/05/2031", "16:00", "Alfa", "Gama", "4-3-3", "4-2-3-1", "T. Alfa", "T. Gama",
     "Alfa", f"{NBSP}Estádio Alfa", "2", "0", "SP", "MG", ""],
    ["5", "2", "17/05/2031", "16:00", "Beta", "Gama", "4-4-2", "4-2-3-1", "T. Beta", "T. Gama",
     "Beta", "Arena Beta", "2", "0", "RJ", "MG", ""],
]

ESTATISTICAS = [
    # partida_id, rodata, clube, chutes, no_alvo, posse, passes, precisao, faltas, ca, cv, imp, esc
    ["1", "1", "Alfa", "10", "4", "55%", "400", "85%", "12", "0", "1", "2", "6"],
    ["1", "1", "Beta", "8", "2", "45%", "350", "80%", "15", "1", "0", "1", "3"],
    ["2", "2", "Beta", "0", "0", "", "0", "", "0", "0", "0", "0", "0"],
    ["2", "2", "Gama", "0", "0", "", "0", "", "0", "0", "0", "0", "0"],
    ["3", "3", "Gama", "9", "3", "None", "300", "70%", "14", "1", "0", "0", "4"],
    ["3", "3", "Alfa", "12", "6", "None", "0", "None", "10", "0", "0", "3", "5"],
    ["4", "1", "Alfa", "11", "5", "60%", "500", "88%", "11", "2", "0", "1", "7"],
    ["4", "1", "Gama", "7", "3", "40%", "320", "78%", "16", "3", "0", "2", "2"],
    ["5", "2", "Beta", "9", "4", "52%", "410", "84%", "13", "1", "0", "0", "5"],
    ["5", "2", "Gama", "6", "2", "48%", "380", "81%", "12", "2", "0", "1", "3"],
]

GOLS = [
    # minutos escolhidos nas fronteiras das faixas: 10, 45+2, 90, 30, 45, 46, 90+4
    ["1", "1", "Alfa", "Jogador A", "10", ""],
    ["1", "1", "Alfa", "Jogador A", "45+2", "Penalty"],
    ["1", "1", "Beta", "Defensor Alfa", "90", "Gol Contra"],
    ["3", "3", "Gama", "Jogador G", "30", ""],
    ["3", "3", "Alfa", "Jogador A", "45", ""],
    ["3", "3", "Alfa", "Jogador B", "46", ""],
    ["3", "3", "Alfa", "Jogador B", "90+4", ""],
]

CARTOES = [
    ["1", "1", "Beta", "Amarelo", "Jogador Y", "5", "Zagueira", "30"],
    ["1", "1", "Alfa", "Vermelho", "Jogador A", "9", "", "90+1"],
    ["3", "3", "Gama", "Amarelo", "Jogador G", "", "Atacante", "12"],
]
# fmt: on

LINHAS = {
    "partidas": PARTIDAS,
    "estatisticas": ESTATISTICAS,
    "gols": GOLS,
    "cartoes": CARTOES,
}

EXPECTATIVAS_FICTICIAS = {
    "linhas_raw": {t: len(v) for t, v in LINHAS.items()},
    "clubes": 3,
    "primeira_temporada": 2030,
    "ultima_temporada": 2031,
    "partidas_por_temporada": {2030: 3, 2031: 2},
    "anos_com_jogos_em_jan_fev": (2031,),
    "estatisticas_disponiveis": 8,
    "passes_convertidos_em_nulo": 1,
    "cobertura_gols_detalhados": (2030, 2030),
    "cobertura_cartoes_detalhados": (2030, 2030),
}


def escrever_csv(caminho: Path, cabecalho, linhas) -> None:
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f, quoting=csv.QUOTE_ALL)
        escritor.writerow(cabecalho)
        escritor.writerows(linhas)


def linhas_dict(con, sql: str, params=None) -> list[dict]:
    cursor = con.execute(sql, params or [])
    nomes = [d[0] for d in cursor.description]
    return [dict(zip(nomes, linha, strict=True)) for linha in cursor.fetchall()]


def escalar(con, sql: str, params=None):
    return con.execute(sql, params or []).fetchall()[0][0]


def assinatura(con, schema: str) -> dict[str, str]:
    """Conteúdo de cada tabela do schema (contagem + soma de hashes das linhas)."""
    tabelas = [
        t
        for (t,) in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ? ORDER BY 1",
            [schema],
        ).fetchall()
    ]
    return {
        t: escalar(
            con,
            f"SELECT count(*)::VARCHAR || ':' || coalesce(sum(hash(x))::VARCHAR, '0') FROM {schema}.{t} x",
        )
        for t in tabelas
    }


@pytest.fixture(autouse=True)
def expectativas_ficticias(monkeypatch):
    """As expectativas do dataset real não valem para os dados fictícios."""
    monkeypatch.setattr(config, "EXPECTATIVAS", copy.deepcopy(EXPECTATIVAS_FICTICIAS))


@pytest.fixture
def dir_raw(tmp_path: Path) -> Path:
    pasta = tmp_path / "raw"
    pasta.mkdir()
    for tabela, fonte in config.FONTES.items():
        escrever_csv(pasta / fonte.arquivo, fonte.colunas, LINHAS[tabela])
    return pasta


@pytest.fixture
def caminho_db(tmp_path: Path) -> Path:
    return tmp_path / "banco" / "teste.duckdb"


@pytest.fixture
def con_raw(dir_raw, caminho_db):
    con = conectar(caminho_db)
    ingerir(con, dir_raw)
    yield con
    con.close()


@pytest.fixture
def con_refined(con_raw):
    transformar(con_raw)
    return con_raw


@pytest.fixture
def con(con_refined):
    """Banco temporário com RAW, REFINED e MARTS construídas sobre os dados fictícios."""
    construir_marts(con_refined)
    return con_refined
