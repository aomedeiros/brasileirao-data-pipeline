"""Regras das tabelas analíticas (MARTS), com valores calculados à mão sobre os dados fictícios."""

from decimal import Decimal

from pipeline import config
from pipeline.db import conectar, listar_tabelas
from pipeline.marts import construir_marts, main
from test.conftest import escalar, linhas_dict


def test_sete_tabelas_criadas(con):
    assert listar_tabelas(con, "marts") == [
        "artilharia", "classificacao", "disciplina_clubes", "estatisticas_por_resultado",
        "gols_por_faixa_minuto", "partida_clube", "resumo_temporadas",
    ]  # fmt: skip


def test_partida_clube_junta_as_fontes(con):
    alfa = linhas_dict(
        con, "SELECT * FROM marts.partida_clube WHERE partida_id = 1 AND clube = 'Alfa'"
    )[0]
    assert (alfa["mando"], alfa["adversario"], alfa["resultado"], alfa["pontos"]) == (
        "mandante",
        "Beta",
        "vitoria",
        3,
    )
    assert (
        alfa["chutes"],
        alfa["gols_penalti"],
        alfa["cartoes_vermelhos"],
        alfa["cartoes_amarelos"],
    ) == (10, 1, 1, 0)


def test_partida_clube_nulo_fora_da_cobertura_e_zero_dentro(con):
    dentro = linhas_dict(
        con, "SELECT * FROM marts.partida_clube WHERE partida_id = 2 AND clube = 'Gama'"
    )[0]
    assert (dentro["gols_penalti"], dentro["cartoes_amarelos"]) == (0, 0)
    fora = linhas_dict(
        con, "SELECT * FROM marts.partida_clube WHERE partida_id = 4 AND clube = 'Alfa'"
    )[0]
    assert (
        fora["detalhe_gols_disponivel"],
        fora["gols_penalti"],
        fora["cartoes_amarelos"],
    ) == (False, None, None)


def test_partida_clube_metricas_nulas_sem_coleta(con):
    linha = linhas_dict(
        con, "SELECT * FROM marts.partida_clube WHERE partida_id = 2 AND clube = 'Beta'"
    )[0]
    assert linha["estatisticas_disponiveis"] is False
    assert (linha["chutes"], linha["passes"], linha["faltas"]) == (None, None, None)


def test_classificacao_ordem_e_aproveitamento(con):
    tabela = linhas_dict(
        con,
        "SELECT posicao_calculada, clube, jogos, pontos, vitorias, empates, derrotas, saldo_gols, aproveitamento_pct "
        "FROM marts.classificacao WHERE temporada = 2030 ORDER BY posicao_calculada",
    )
    assert [
        (t["posicao_calculada"], t["clube"], t["pontos"], t["saldo_gols"])
        for t in tabela
    ] == [
        (1, "Alfa", 6, 3),
        (2, "Beta", 1, -1),
        (3, "Gama", 1, -2),
    ]
    assert [t["aproveitamento_pct"] for t in tabela] == [
        Decimal("100.0"),
        Decimal("16.7"),
        Decimal("16.7"),
    ]


def test_classificacao_empate_completo_mantem_a_mesma_posicao(con):
    tabela = con.execute(
        "SELECT clube, posicao_calculada, pontos, vitorias, saldo_gols, gols_pro "
        "FROM marts.classificacao WHERE temporada = 2031 ORDER BY clube"
    ).fetchall()
    # Alfa e Beta empatam em pontos, vitórias, saldo e gols pró: mesma posição, sem desempate inventado
    assert tabela == [
        ("Alfa", 1, 3, 1, 2, 2),
        ("Beta", 1, 3, 1, 2, 2),
        ("Gama", 3, 0, 0, -4, 0),
    ]


def test_resumo_lista_empatados_no_primeiro_lugar(con):
    resumo = dict(
        con.execute(
            "SELECT temporada, primeiro_colocado_calculado FROM marts.resumo_temporadas"
        ).fetchall()
    )
    assert resumo == {2030: "Alfa", 2031: "Alfa / Beta"}


def test_resumo_cobertura_e_medias(con):
    r = {
        x["temporada"]: x
        for x in linhas_dict(con, "SELECT * FROM marts.resumo_temporadas")
    }
    assert (
        r[2030]["partidas"],
        r[2030]["gols"],
        r[2030]["media_gols_por_partida"],
    ) == (3, 7, Decimal("2.33"))
    assert (
        r[2030]["gols_detalhados"],
        r[2030]["cartoes_amarelos"],
        r[2030]["partidas_com_estatisticas"],
    ) == (7, 2, 2)
    assert (
        r[2031]["cobertura_gols_detalhados"],
        r[2031]["gols_detalhados"],
        r[2031]["cartoes_amarelos"],
    ) == (
        False,
        None,
        None,
    )
    assert (
        r[2030]["pct_vitorias_mandante"],
        r[2030]["pct_empates"],
        r[2030]["pct_vitorias_visitante"],
    ) == (
        Decimal("33.3"),
        Decimal("33.3"),
        Decimal("33.3"),
    )


def test_artilharia_exclui_gol_contra(con):
    assert con.execute(
        "SELECT ranking, atleta, gols, gols_penalti, partidas_com_gol FROM marts.artilharia ORDER BY ranking"
    ).fetchall() == [
        (1, "Jogador A", 3, 1, 2),
        (2, "Jogador B", 2, 0, 1),
        (3, "Jogador G", 1, 0, 1),
    ]


def test_faixas_de_minuto_nas_fronteiras(con):
    faixas = {f: (g, m, v) for f, g, m, v in con.execute(
        "SELECT faixa, gols, gols_mandante, gols_visitante FROM marts.gols_por_faixa_minuto").fetchall()}  # fmt: skip
    assert faixas == {
        "0-15": (1, 1, 0),  # 10'
        "16-30": (1, 1, 0),  # 30'
        "31-45": (1, 0, 1),  # 45' sem acréscimo
        "45+": (1, 1, 0),  # 45+2
        "46-60": (1, 0, 1),  # 46'
        "61-75": (0, 0, 0),  # faixa sem gols continua presente
        "76-90": (1, 0, 1),  # 90' sem acréscimo (gol contra a favor do visitante)
        "90+": (1, 0, 1),  # 90+4
    }
    assert escalar(
        con, "SELECT pct_gols FROM marts.gols_por_faixa_minuto WHERE faixa = '0-15'"
    ) == Decimal("14.29")


def test_disciplina_nulo_fora_da_cobertura(con):
    d = {(t, c): r for t, c, *r in con.execute(
        "SELECT temporada, clube, cobertura_cartoes, amarelos, vermelhos, amarelos_por_jogo, vermelhos_por_jogo "
        "FROM marts.disciplina_clubes").fetchall()}  # fmt: skip
    assert d[(2030, "Alfa")] == [True, 0, 1, Decimal("0.00"), Decimal("0.50")]
    assert d[(2030, "Beta")] == [True, 1, 0, Decimal("0.50"), Decimal("0.00")]
    assert d[(2031, "Alfa")] == [False, None, None, None, None]


def test_estatisticas_por_resultado_medias_e_bases(con):
    linhas = {(x["temporada"], x["resultado"], x["mando"]): x for x in linhas_dict(
        con, "SELECT * FROM marts.estatisticas_por_resultado")}  # fmt: skip
    assert len(linhas) == 6  # partida 2 (sem coleta) não entra
    v = linhas[(2031, "vitoria", "mandante")]  # Alfa (partida 4) e Beta (partida 5)
    assert (
        v["registros"],
        v["media_chutes"],
        v["media_posse_de_bola"],
        v["media_passes"],
    ) == (
        2,
        Decimal("10.00"),
        Decimal("56.00"),
        Decimal("455.0"),
    )
    assert v["media_impedimentos"] == Decimal("0.50")
    sem_passes = linhas[
        (2030, "vitoria", "visitante")
    ]  # Alfa na partida 3: passes e posse nulos
    assert (
        sem_passes["n_passes"],
        sem_passes["media_passes"],
        sem_passes["n_posse_de_bola"],
    ) == (0, None, 0)
    assert (sem_passes["n_chutes"], sem_passes["media_chutes"]) == (1, Decimal("12.00"))


def test_reexecucao_e_deterministica(con):
    def conteudo():
        return {
            t: con.execute(f"SELECT * FROM marts.{t} ORDER BY ALL").fetchall()
            for t in listar_tabelas(con, "marts")
        }

    antes = conteudo()
    construir_marts(con)
    assert conteudo() == antes


def test_main_exige_banco_e_camada_refined(tmp_path, con_raw, caminho_db, capsys):
    assert main(["--db", str(tmp_path / "inexistente.duckdb")]) == 1
    con_raw.close()
    assert main(["--db", str(caminho_db)]) == 1
    assert "Camada REFINED incompleta" in capsys.readouterr().err


def test_main_sucesso_e_falha_de_qualidade(
    con_refined, caminho_db, monkeypatch, capsys
):
    con_refined.close()
    assert main(["--db", str(caminho_db)]) == 0
    assert "MARTS aprovadas" in capsys.readouterr().out
    monkeypatch.setitem(
        config.EXPECTATIVAS, "cobertura_cartoes_detalhados", (2030, 2031)
    )
    assert main(["--db", str(caminho_db)]) == 1
    assert "cobertura de cartões" in capsys.readouterr().err
    leitura = conectar(caminho_db, somente_leitura=True)
    assert (
        escalar(leitura, "SELECT count(*) FROM marts.partida_clube") == 10
    )  # versão anterior preservada
    leitura.close()
