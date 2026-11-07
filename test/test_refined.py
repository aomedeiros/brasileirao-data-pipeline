"""Regras de transformação da REFINED, sobre os dados fictícios."""

from datetime import date, time
from decimal import Decimal

from pipeline import config
from pipeline.db import conectar
from pipeline.transformacao import main, transformar
from test.conftest import escalar, linhas_dict


def partida(con, partida_id):
    return linhas_dict(
        con, "SELECT * FROM refined.partidas WHERE partida_id = ?", [partida_id]
    )[0]


def test_dimensao_de_clubes(con_refined):
    assert linhas_dict(
        con_refined,
        "SELECT clube_id, clube, uf, total_partidas FROM refined.clubes ORDER BY 1",
    ) == [
        {
            "clube_id": 1,
            "clube": "Alfa",
            "uf": "SP",
            "total_partidas": 3,
        },  # partidas 1, 3, 4
        {
            "clube_id": 2,
            "clube": "Beta",
            "uf": "RJ",
            "total_partidas": 3,
        },  # partidas 1, 2, 5
        {
            "clube_id": 3,
            "clube": "Gama",
            "uf": "MG",
            "total_partidas": 4,
        },  # partidas 2, 3, 4, 5
    ]


def test_tipos_e_chaves_da_partida(con_refined):
    p = partida(con_refined, 1)
    assert p["data_partida"] == date(2030, 5, 10)
    assert p["hora_partida"] == time(16, 0)
    assert (p["gols_mandante"], p["gols_visitante"]) == (2, 1)
    assert p["arrecadacao"] == Decimal("150000.50")
    assert (p["mandante_id"], p["visitante_id"]) == (1, 2)


def test_temporada_de_jogo_em_janeiro_e_a_anterior(con_refined):
    assert partida(con_refined, 3)["data_partida"] == date(2031, 1, 20)
    assert partida(con_refined, 3)["temporada"] == 2030
    assert partida(con_refined, 4)["temporada"] == 2031


def test_dia_da_semana_em_portugues(con_refined):
    nomes = [
        "Segunda-feira",
        "Terça-feira",
        "Quarta-feira",
        "Quinta-feira",
        "Sexta-feira",
        "Sábado",
        "Domingo",
    ]
    for pid, data in [(1, date(2030, 5, 10)), (3, date(2031, 1, 20))]:
        assert partida(con_refined, pid)["dia_semana"] == nomes[data.weekday()]


def test_empate_vira_vencedor_nulo_e_resultado_empate(con_refined):
    assert (
        partida(con_refined, 2)["vencedor"],
        partida(con_refined, 2)["resultado"],
    ) == (None, "empate")
    assert (
        partida(con_refined, 3)["vencedor"],
        partida(con_refined, 3)["resultado"],
    ) == ("Alfa", "visitante")


def test_limpeza_de_texto_e_ausencias(con_refined):
    assert partida(con_refined, 1)["arena"] == "Estádio Alfa"  # NBSP removido
    assert partida(con_refined, 2)["arena"] == "Arena Beta"  # espaço final removido
    assert (
        partida(con_refined, 2)["formacao_mandante"] is None
    )  # '' -> NULL, sem inventar valor
    assert partida(con_refined, 2)["arrecadacao"] is None


def test_estatisticas_disponiveis_distingue_nao_coletado(con_refined):
    flags = dict(
        con_refined.execute(
            "SELECT partida_id, bool_and(estatisticas_disponiveis) FROM refined.estatisticas GROUP BY 1"
        ).fetchall()
    )
    assert flags == {1: True, 2: False, 3: True, 4: True, 5: True}
    # valores originais preservados na linha indisponível
    assert (
        escalar(
            con_refined,
            "SELECT sum(chutes) FROM refined.estatisticas WHERE partida_id = 2",
        )
        == 0
    )


def test_percentuais_e_none(con_refined):
    gama = linhas_dict(
        con_refined,
        "SELECT * FROM refined.estatisticas WHERE partida_id = 3 AND clube = 'Gama'",
    )[0]
    assert gama["posse_de_bola"] is None and gama["precisao_passes"] == Decimal("70.00")


def test_passes_zero_sem_precisao_vira_nulo_so_em_linha_disponivel(con_refined):
    alfa = linhas_dict(
        con_refined,
        "SELECT * FROM refined.estatisticas WHERE partida_id = 3 AND clube = 'Alfa'",
    )[0]
    assert alfa["passes"] is None and alfa["estatisticas_disponiveis"]
    # na linha não coletada (partida 2), passes = 0 é mantido
    assert escalar(
        con_refined,
        "SELECT list(passes ORDER BY clube) FROM refined.estatisticas WHERE partida_id = 2",
    ) == [
        0,
        0,
    ]


def test_gols_minuto_acrescimo_e_flags(con_refined):
    gols = linhas_dict(
        con_refined,
        "SELECT gol_id, minuto_origem, minuto, acrescimo, tipo_gol, penalti, gol_contra FROM refined.gols",
    )
    assert [g["gol_id"] for g in gols] == list(range(1, 8))
    por_minuto = {g["minuto_origem"]: g for g in gols}
    assert (
        por_minuto["45+2"]["minuto"],
        por_minuto["45+2"]["acrescimo"],
        por_minuto["45+2"]["penalti"],
    ) == (45, 2, True)
    assert (por_minuto["90"]["gol_contra"], por_minuto["90"]["tipo_gol"]) == (
        True,
        "Gol Contra",
    )
    assert (
        por_minuto["10"]["tipo_gol"],
        por_minuto["10"]["penalti"],
        por_minuto["10"]["gol_contra"],
    ) == (
        None,
        False,
        False,
    )


def test_cartoes_preservam_posicao_original_e_padronizam(con_refined):
    cartoes = {
        c["clube"]: c for c in linhas_dict(con_refined, "SELECT * FROM refined.cartoes")
    }
    assert (cartoes["Beta"]["posicao_origem"], cartoes["Beta"]["posicao"]) == (
        "Zagueira",
        "Zagueiro",
    )
    assert cartoes["Beta"]["num_camisa"] == 5
    assert (cartoes["Alfa"]["posicao_origem"], cartoes["Alfa"]["posicao"]) == (
        None,
        None,
    )
    assert (cartoes["Alfa"]["minuto"], cartoes["Alfa"]["acrescimo"]) == (90, 1)
    assert cartoes["Gama"]["num_camisa"] is None


def test_reexecucao_e_deterministica(con_refined):
    def conteudo():
        return {t: con_refined.execute(f"SELECT * FROM refined.{t} ORDER BY ALL").fetchall()
                for t in ("clubes", "partidas", "estatisticas", "gols", "cartoes")}  # fmt: skip

    antes = conteudo()
    transformar(con_refined)
    assert conteudo() == antes


def test_main_exige_banco_e_camada_raw(tmp_path, capsys):
    assert main(["--db", str(tmp_path / "inexistente.duckdb")]) == 1
    vazio = tmp_path / "vazio.duckdb"
    conectar(vazio).close()
    assert main(["--db", str(vazio)]) == 1
    assert "Camada RAW incompleta" in capsys.readouterr().err


def test_main_sucesso_e_falha_de_qualidade(con_raw, caminho_db, monkeypatch, capsys):
    con_raw.close()
    assert main(["--db", str(caminho_db)]) == 0
    assert "REFINED aprovadas" in capsys.readouterr().out
    monkeypatch.setitem(config.EXPECTATIVAS, "clubes", 4)
    assert main(["--db", str(caminho_db)]) == 1
    assert "4 clubes" in capsys.readouterr().err
