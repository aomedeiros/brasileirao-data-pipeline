"""Verificações de qualidade dos dados, por camada (RAW, REFINED e MARTS).

Cada verificação conta violações; o esperado é zero. Há dois tipos:
- "I" (invariante): regra estrutural que vale para qualquer versão dos dados;
- "E" (expectativa): número específico desta versão do dataset, configurado
  em ``config.EXPECTATIVAS``.

As camadas chamam ``exigir_camada`` dentro da própria transação, antes do
COMMIT: uma falha levanta ``FalhaDeQualidadeError`` e a transação é desfeita.

Uso avulso (abre o banco somente para leitura):
    uv run python -m pipeline.qualidade
    uv run python -m pipeline.qualidade --camada refined --db caminho/banco.duckdb
"""

import argparse
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path

import duckdb

from pipeline import config
from pipeline.db import conectar

CAMADAS = ("raw", "refined", "marts")


@dataclass(frozen=True)
class Verificacao:
    camada: str
    tipo: str  # "I" (invariante) ou "E" (expectativa do dataset)
    nome: str
    sql: str | None = None  # consulta que devolve o número de violações
    funcao: Callable[[duckdb.DuckDBPyConnection], int] | None = None


@dataclass(frozen=True)
class Resultado:
    verificacao: Verificacao
    violacoes: int | None
    erro: str | None = None

    @property
    def ok(self) -> bool:
        return self.erro is None and self.violacoes == 0


class FalhaDeQualidadeError(RuntimeError):
    def __init__(self, camada: str, falhas: list[Resultado]):
        self.camada = camada
        self.falhas = falhas
        linhas = [
            f"{len(falhas)} verificação(ões) de qualidade falharam na camada {camada.upper()}:"
        ]
        linhas += [f"  - {descrever(r)}" for r in falhas]
        super().__init__("\n".join(linhas))


def descrever(r: Resultado) -> str:
    v = r.verificacao
    if r.erro:
        return f"[{v.tipo}] {v.nome}: ERRO ({r.erro})"
    return f"[{v.tipo}] {v.nome}: {r.violacoes} violação(ões)"


# --------------------------------------------------------------------- RAW
def _verificacoes_raw() -> list[Verificacao]:
    contrato = ", ".join(
        f"('{t}', '{','.join(f.colunas)}')" for t, f in config.FONTES.items()
    )
    nulos = " + ".join(
        f"(SELECT count(*) FROM raw.{t} WHERE "
        + " OR ".join(f'"{c}" IS NULL' for c in f.colunas)
        + ")"
        for t, f in config.FONTES.items()
    )
    v = [
        Verificacao(
            "raw",
            "I",
            "as quatro tabelas existem com as colunas e a ordem do contrato",
            f"""
            SELECT count(*) FROM (VALUES {contrato}) e(t, colunas)
            LEFT JOIN (SELECT table_name AS t, string_agg(column_name, ',' ORDER BY ordinal_position) AS colunas
                       FROM information_schema.columns WHERE table_schema = 'raw' GROUP BY 1) a USING (t)
            WHERE a.colunas IS DISTINCT FROM e.colunas""",
        ),
        Verificacao(
            "raw",
            "I",
            "todas as colunas são VARCHAR",
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = 'raw' AND data_type <> 'VARCHAR'",
        ),
        Verificacao(
            "raw",
            "I",
            "nenhum NULL (campos vazios preservados como texto vazio)",
            f"SELECT {nulos}",
        ),
    ]
    for t, n in config.EXPECTATIVAS["linhas_raw"].items():
        v.append(
            Verificacao(
                "raw",
                "E",
                f"raw.{t} tem {n} linhas",
                f"SELECT abs(count(*) - {n}) FROM raw.{t}",
            )
        )
    return v


# ----------------------------------------------------------------- REFINED
def _clube_fora_da_partida(tabela: str) -> str:
    return f"""SELECT count(*) FROM refined.{tabela} t JOIN refined.partidas p USING (partida_id)
               WHERE t.clube_id NOT IN (p.mandante_id, p.visitante_id)"""


def _minuto_reconstruido(tabela: str) -> str:
    return f"""SELECT count(*) FROM refined.{tabela}
               WHERE minuto_origem <> minuto::VARCHAR || CASE WHEN acrescimo > 0 THEN '+' || acrescimo ELSE '' END"""


def _verificacoes_refined() -> list[Verificacao]:
    e = config.EXPECTATIVAS
    ini, fim = e["primeira_temporada"], e["ultima_temporada"]
    por_temporada = ", ".join(
        f"({t}, {n})" for t, n in e["partidas_por_temporada"].items()
    )
    anos_jan_fev = ", ".join(str(a) for a in e["anos_com_jogos_em_jan_fev"]) or "NULL"
    v = [
        Verificacao(
            "refined",
            "I",
            f"refined.{t} preserva todas as linhas da RAW",
            f"SELECT abs((SELECT count(*) FROM raw.{t}) - (SELECT count(*) FROM refined.{t}))",
        )
        for t in config.FONTES
    ]
    v += [
        Verificacao(
            "refined",
            "I",
            "clube_id e nome do clube únicos",
            "SELECT (count(*) - count(DISTINCT clube_id)) + (count(*) - count(DISTINCT clube)) "
            "FROM refined.clubes",
        ),
        Verificacao(
            "refined",
            "I",
            "cada clube tem uma única UF na origem",
            """
            WITH ufs AS (
                SELECT refined.texto(mandante) AS clube, refined.texto(mandante_Estado) AS uf FROM raw.partidas
                UNION ALL
                SELECT refined.texto(visitante), refined.texto(visitante_Estado) FROM raw.partidas)
            SELECT count(*) FROM (SELECT clube FROM ufs GROUP BY clube HAVING count(DISTINCT uf) <> 1)""",
        ),
        Verificacao(
            "refined",
            "I",
            "partida_id único e não nulo",
            "SELECT count(*) - count(DISTINCT partida_id) + count(*) FILTER (WHERE partida_id IS NULL) "
            "FROM refined.partidas",
        ),
        Verificacao(
            "refined",
            "I",
            "estatística única por (partida_id, clube_id)",
            "SELECT count(*) - count(DISTINCT (partida_id, clube_id)) FROM refined.estatisticas",
        ),
    ]
    v += [
        Verificacao(
            "refined",
            "I",
            f"{t}: nenhuma referência a partida inexistente",
            f"SELECT count(*) FROM refined.{t} ANTI JOIN refined.partidas USING (partida_id)",
        )
        for t in ("estatisticas", "gols", "cartoes")
    ]
    v += [
        Verificacao(
            "refined",
            "I",
            f"{t}: clube é o mandante ou o visitante da partida",
            _clube_fora_da_partida(t),
        )
        for t in ("estatisticas", "gols", "cartoes")
    ]
    v += [
        Verificacao(
            "refined",
            "I",
            "rodada dos eventos igual à rodada da partida",
            """
            SELECT (SELECT count(*) FROM refined.estatisticas t JOIN refined.partidas p USING (partida_id)
                    WHERE t.rodada <> p.rodada)
                 + (SELECT count(*) FROM refined.gols t JOIN refined.partidas p USING (partida_id)
                    WHERE t.rodada <> p.rodada)
                 + (SELECT count(*) FROM refined.cartoes t JOIN refined.partidas p USING (partida_id)
                    WHERE t.rodada <> p.rodada)""",
        ),
        Verificacao(
            "refined",
            "I",
            "exatamente duas linhas de estatísticas por partida",
            """
            SELECT count(*) FROM refined.partidas p
            LEFT JOIN (SELECT partida_id, count(*) AS n FROM refined.estatisticas GROUP BY 1) e USING (partida_id)
            WHERE coalesce(e.n, 0) <> 2""",
        ),
        Verificacao(
            "refined",
            "I",
            "vencedor coerente com o placar",
            """
            SELECT count(*) FROM refined.partidas
            WHERE (resultado = 'empate' AND vencedor IS NOT NULL)
               OR (resultado = 'mandante' AND vencedor IS DISTINCT FROM mandante)
               OR (resultado = 'visitante' AND vencedor IS DISTINCT FROM visitante)""",
        ),
        Verificacao(
            "refined",
            "I",
            "gols detalhados somam o placar de cada clube",
            """
            WITH g AS (
                SELECT g.partida_id,
                       count(*) FILTER (WHERE g.clube_id = p.mandante_id)  AS gm,
                       count(*) FILTER (WHERE g.clube_id = p.visitante_id) AS gv
                FROM refined.gols g JOIN refined.partidas p USING (partida_id) GROUP BY 1)
            SELECT count(*) FROM refined.partidas p JOIN g USING (partida_id)
            WHERE g.gm <> p.gols_mandante OR g.gv <> p.gols_visitante""",
        ),
        Verificacao(
            "refined",
            "I",
            "campos obrigatórios da partida preenchidos",
            """
            SELECT count(*) FROM refined.partidas
            WHERE temporada IS NULL OR rodada IS NULL OR data_partida IS NULL OR hora_partida IS NULL
               OR gols_mandante IS NULL OR gols_visitante IS NULL OR arena IS NULL""",
        ),
        Verificacao(
            "refined",
            "I",
            "gols: minuto e acréscimo reconstroem o texto original",
            _minuto_reconstruido("gols"),
        ),
        Verificacao(
            "refined",
            "I",
            "cartões: minuto e acréscimo reconstroem o texto original",
            _minuto_reconstruido("cartoes"),
        ),
        Verificacao(
            "refined",
            "I",
            "estatística indisponível não tem nenhum valor coletado",
            """
            SELECT count(*) FROM refined.estatisticas
            WHERE NOT estatisticas_disponiveis
              AND (chutes > 0 OR chutes_no_alvo > 0 OR passes > 0 OR faltas > 0 OR escanteios > 0
                   OR impedimentos > 0 OR posse_de_bola IS NOT NULL)""",
        ),
        Verificacao(
            "refined",
            "I",
            "posição padronizada difere da origem só em 'Zagueira' -> 'Zagueiro'",
            """
            SELECT count(*) FROM refined.cartoes
            WHERE posicao IS DISTINCT FROM posicao_origem
              AND NOT (posicao_origem = 'Zagueira' AND posicao = 'Zagueiro')""",
        ),
        Verificacao(
            "refined",
            "I",
            "passes nulo apenas em linha disponível sem precisão de passes (e nenhum 0 restante)",
            """
            SELECT count(*) FILTER (WHERE passes IS NULL
                                     AND NOT (estatisticas_disponiveis AND precisao_passes IS NULL))
                 + count(*) FILTER (WHERE estatisticas_disponiveis AND precisao_passes IS NULL AND passes = 0)
            FROM refined.estatisticas""",
        ),
        # Expectativas do dataset
        Verificacao(
            "refined",
            "E",
            f"{e['clubes']} clubes",
            f"SELECT abs(count(*) - {e['clubes']}) FROM refined.clubes",
        ),
        Verificacao(
            "refined",
            "E",
            f"temporadas de {ini} a {fim}, sem lacunas",
            f"""
            SELECT (min(temporada) <> {ini})::INTEGER + (max(temporada) <> {fim})::INTEGER
                 + (count(DISTINCT temporada) <> {fim - ini + 1})::INTEGER
            FROM refined.partidas""",
        ),
        Verificacao(
            "refined",
            "E",
            f"partidas por temporada: {e['partidas_por_temporada']}",
            f"""
            SELECT coalesce(sum(abs(coalesce(p.n, 0) - x.n)), 0) FROM (VALUES {por_temporada}) x(temporada, n)
            LEFT JOIN (SELECT temporada, count(*) AS n FROM refined.partidas GROUP BY 1) p USING (temporada)""",
        ),
        Verificacao(
            "refined",
            "E",
            f"jogos em janeiro/fevereiro só nos anos {e['anos_com_jogos_em_jan_fev']}",
            f"""
            SELECT count(*) FROM refined.partidas
            WHERE month(data_partida) <= 2 AND year(data_partida) NOT IN ({anos_jan_fev})""",
        ),
        Verificacao(
            "refined",
            "E",
            f"{e['estatisticas_disponiveis']} linhas de estatísticas disponíveis",
            f"SELECT abs(count(*) FILTER (WHERE estatisticas_disponiveis) - {e['estatisticas_disponiveis']}) "
            "FROM refined.estatisticas",
        ),
        Verificacao(
            "refined",
            "E",
            f"{e['passes_convertidos_em_nulo']} valores de passes convertidos em NULL",
            f"SELECT abs(count(*) FILTER (WHERE passes IS NULL) - {e['passes_convertidos_em_nulo']}) "
            "FROM refined.estatisticas",
        ),
    ]
    return v


# ------------------------------------------------------------------- MARTS
# Colunas arredondadas: (tabela, coluna, casas, consulta chave+numerador+denominador, colunas-chave)
_K5 = "temporada, resultado, mando"
_COLUNAS_ARREDONDADAS: list[tuple[str, str, int, str, str]] = [
    *[
        ("estatisticas_por_resultado", f"media_{m}", casas,
         (f"SELECT {_K5}, sum({col}{escala}), count({col}){escala} FROM marts.partida_clube "
          "WHERE estatisticas_disponiveis GROUP BY ALL"), _K5)
        for m, col, casas, escala in [
            ("gols", "gols_pro", 2, ""), ("chutes", "chutes", 2, ""), ("chutes_no_alvo", "chutes_no_alvo", 2, ""),
            ("posse_de_bola", "posse_de_bola", 2, " * 100"), ("passes", "passes", 1, ""),
            ("precisao_passes", "precisao_passes", 2, " * 100"), ("faltas", "faltas", 2, ""),
            ("escanteios", "escanteios", 2, ""), ("impedimentos", "impedimentos", 2, ""),
        ]
    ],
    ("classificacao", "aproveitamento_pct", 1,
     "SELECT temporada, clube_id, 100 * pontos, 3 * jogos FROM marts.classificacao", "temporada, clube_id"),
    ("disciplina_clubes", "amarelos_por_jogo", 2,
     "SELECT temporada, clube_id, amarelos, CASE WHEN cobertura_cartoes THEN jogos END FROM marts.disciplina_clubes",
     "temporada, clube_id"),
    ("disciplina_clubes", "vermelhos_por_jogo", 2,
     "SELECT temporada, clube_id, vermelhos, CASE WHEN cobertura_cartoes THEN jogos END FROM marts.disciplina_clubes",
     "temporada, clube_id"),
    ("gols_por_faixa_minuto", "pct_gols", 2,
     "SELECT faixa, 100 * gols, sum(gols) OVER () FROM marts.gols_por_faixa_minuto", "faixa"),
    ("resumo_temporadas", "media_gols_por_partida", 2,
     "SELECT temporada, gols, partidas FROM marts.resumo_temporadas", "temporada"),
    *[
        ("resumo_temporadas", col, 1,
         f"SELECT temporada, 100 * count(*) FILTER (WHERE resultado = '{r}'), count(*) FROM refined.partidas GROUP BY 1",
         "temporada")
        for col, r in (("pct_vitorias_mandante", "mandante"), ("pct_empates", "empate"),
                       ("pct_vitorias_visitante", "visitante"))
    ],
]  # fmt: skip


def meio_para_cima(numerador, denominador, casas: int) -> Decimal | None:
    """ROUND_HALF_UP exato da fração numerador/denominador (referência independente do DuckDB)."""
    if numerador is None or denominador is None or denominador == 0:
        return None
    f = Fraction(Decimal(str(numerador))) / Fraction(Decimal(str(denominador)))
    return (Decimal(f.numerator) / Decimal(f.denominator)).quantize(
        Decimal(1).scaleb(-casas), ROUND_HALF_UP
    )


def _arredondamento_exato(
    tabela: str, coluna: str, casas: int, sql_ref: str, chave: str
) -> Callable:
    def verificar(con: duckdb.DuckDBPyConnection) -> int:
        tipo = con.execute(
            "SELECT data_type FROM information_schema.columns WHERE table_schema = 'marts' "
            "AND table_name = ? AND column_name = ?",
            [tabela, coluna],
        ).fetchall()
        violacoes = 0 if tipo == [(f"DECIMAL(10,{casas})",)] else 1
        referencia = {
            tuple(r[:-2]): (r[-2], r[-1]) for r in con.execute(sql_ref).fetchall()
        }
        armazenado = con.execute(
            f"SELECT {chave}, {coluna} FROM marts.{tabela}"
        ).fetchall()
        violacoes += abs(len(referencia) - len(armazenado))
        for *k, valor in armazenado:
            numerador, denominador = referencia.get(tuple(k), (None, None))
            if valor != meio_para_cima(numerador, denominador, casas):
                violacoes += 1
        return violacoes

    return verificar


def _verificacoes_marts() -> list[Verificacao]:
    e = config.EXPECTATIVAS
    gi, gf = e["cobertura_gols_detalhados"]
    ci, cf = e["cobertura_cartoes_detalhados"]
    pc = "marts.partida_clube"
    v = [
        # partida_clube
        Verificacao(
            "marts",
            "I",
            "partida_clube: duas linhas por partida",
            f"SELECT abs((SELECT count(*) FROM {pc}) - 2 * (SELECT count(*) FROM refined.partidas))",
        ),
        Verificacao(
            "marts",
            "I",
            "partida_clube: chave (partida_id, clube_id) única",
            f"SELECT count(*) - count(DISTINCT (partida_id, clube_id)) FROM {pc}",
        ),
        Verificacao(
            "marts",
            "I",
            "partida_clube: um mandante e um visitante por partida",
            f"""
            SELECT count(*) FROM (SELECT partida_id FROM {pc} GROUP BY 1
                HAVING count(*) FILTER (WHERE mando = 'mandante') <> 1
                    OR count(*) FILTER (WHERE mando = 'visitante') <> 1)""",
        ),
        Verificacao(
            "marts",
            "I",
            "partida_clube: gols, pênaltis, gols contra, cartões e chutes conservados",
            f"""
            SELECT abs((SELECT sum(gols_pro) FROM {pc})
                       - (SELECT sum(gols_mandante + gols_visitante) FROM refined.partidas))
                 + abs((SELECT sum(gols_penalti) FROM {pc}) - (SELECT count(*) FROM refined.gols WHERE penalti))
                 + abs((SELECT sum(gols_contra_a_favor) FROM {pc})
                       - (SELECT count(*) FROM refined.gols WHERE gol_contra))
                 + abs((SELECT sum(cartoes_amarelos) FROM {pc})
                       - (SELECT count(*) FROM refined.cartoes WHERE cartao = 'Amarelo'))
                 + abs((SELECT sum(cartoes_vermelhos) FROM {pc})
                       - (SELECT count(*) FROM refined.cartoes WHERE cartao = 'Vermelho'))
                 + abs((SELECT sum(chutes) FROM {pc})
                       - (SELECT sum(chutes) FROM refined.estatisticas WHERE estatisticas_disponiveis))""",
        ),
        Verificacao(
            "marts",
            "I",
            "partida_clube: linhas disponíveis iguais às da REFINED",
            f"SELECT abs((SELECT count(*) FROM {pc} WHERE estatisticas_disponiveis) - "
            "(SELECT count(*) FROM refined.estatisticas WHERE estatisticas_disponiveis))",
        ),
        Verificacao(
            "marts",
            "I",
            "partida_clube: métricas nulas quando a estatística não foi coletada",
            f"""
            SELECT count(*) FROM {pc} WHERE NOT estatisticas_disponiveis AND (
                chutes IS NOT NULL OR chutes_no_alvo IS NOT NULL OR posse_de_bola IS NOT NULL OR passes IS NOT NULL
                OR precisao_passes IS NOT NULL OR faltas IS NOT NULL OR impedimentos IS NOT NULL
                OR escanteios IS NOT NULL)""",
        ),
        Verificacao(
            "marts",
            "I",
            "partida_clube: gols e cartões NULL fora e preenchidos dentro da cobertura",
            f"""
            SELECT count(*) FROM {pc}
            WHERE (detalhe_gols_disponivel AND (gols_penalti IS NULL OR gols_contra_a_favor IS NULL))
               OR (NOT detalhe_gols_disponivel AND (gols_penalti IS NOT NULL OR gols_contra_a_favor IS NOT NULL))
               OR (detalhe_cartoes_disponivel AND (cartoes_amarelos IS NULL OR cartoes_vermelhos IS NULL))
               OR (NOT detalhe_cartoes_disponivel
                   AND (cartoes_amarelos IS NOT NULL OR cartoes_vermelhos IS NOT NULL))""",
        ),
        # classificacao
        Verificacao(
            "marts",
            "I",
            "classificacao: chave (temporada, clube_id) única",
            "SELECT count(*) - count(DISTINCT (temporada, clube_id)) FROM marts.classificacao",
        ),
        Verificacao(
            "marts",
            "I",
            "classificacao: jogos = 2 x partidas em cada temporada",
            """
            SELECT count(*) FROM (SELECT temporada, sum(jogos) AS j FROM marts.classificacao GROUP BY 1) c
            FULL JOIN (SELECT temporada, count(*) AS n FROM refined.partidas GROUP BY 1) p USING (temporada)
            WHERE c.j IS DISTINCT FROM 2 * p.n""",
        ),
        Verificacao(
            "marts",
            "I",
            "classificacao: V+E+D = jogos, pontos = 3V+E e saldo = pró - contra",
            """
            SELECT count(*) FROM marts.classificacao
            WHERE vitorias + empates + derrotas <> jogos OR pontos <> 3 * vitorias + empates
               OR saldo_gols <> gols_pro - gols_contra""",
        ),
        Verificacao(
            "marts",
            "I",
            "classificacao: gols pró conservados em relação ao placar",
            "SELECT abs((SELECT sum(gols_pro) FROM marts.classificacao) - "
            "(SELECT sum(gols_mandante + gols_visitante) FROM refined.partidas))",
        ),
        Verificacao(
            "marts",
            "I",
            "classificacao: posição respeita pontos, vitórias, saldo e gols pró",
            """
            SELECT count(*) FROM marts.classificacao a JOIN marts.classificacao b ON a.temporada = b.temporada
             AND (a.pontos, a.vitorias, a.saldo_gols, a.gols_pro) > (b.pontos, b.vitorias, b.saldo_gols, b.gols_pro)
            WHERE a.posicao_calculada >= b.posicao_calculada""",
        ),
        Verificacao(
            "marts",
            "I",
            "classificacao: empatados em todos os critérios têm a mesma posição",
            """
            SELECT count(*) FROM marts.classificacao a JOIN marts.classificacao b ON a.temporada = b.temporada
             AND a.clube_id < b.clube_id
             AND (a.pontos, a.vitorias, a.saldo_gols, a.gols_pro) = (b.pontos, b.vitorias, b.saldo_gols, b.gols_pro)
            WHERE a.posicao_calculada <> b.posicao_calculada""",
        ),
        # artilharia
        Verificacao(
            "marts",
            "I",
            "artilharia: chave (temporada, atleta, clube_id) única",
            "SELECT count(*) - count(DISTINCT (temporada, atleta, clube_id)) FROM marts.artilharia",
        ),
        Verificacao(
            "marts",
            "I",
            "artilharia: gols e pênaltis conservados (sem gols contra)",
            """
            SELECT abs((SELECT sum(gols) FROM marts.artilharia)
                       - (SELECT count(*) FROM refined.gols WHERE NOT gol_contra))
                 + abs((SELECT sum(gols_penalti) FROM marts.artilharia)
                       - (SELECT count(*) FROM refined.gols WHERE penalti AND NOT gol_contra))""",
        ),
        Verificacao(
            "marts",
            "I",
            "artilharia: ranking coerente com os gols",
            """
            SELECT count(*) FROM marts.artilharia a JOIN marts.artilharia b
              ON a.temporada = b.temporada AND a.gols > b.gols
            WHERE a.ranking >= b.ranking""",
        ),
        # disciplina_clubes
        Verificacao(
            "marts",
            "I",
            "disciplina_clubes: uma linha por clube e temporada da classificação",
            """
            SELECT (SELECT count(*) - count(DISTINCT (temporada, clube_id)) FROM marts.disciplina_clubes)
                 + (SELECT count(*) FROM marts.disciplina_clubes d
                    FULL JOIN marts.classificacao c USING (temporada, clube_id)
                    WHERE d.jogos IS DISTINCT FROM c.jogos)""",
        ),
        Verificacao(
            "marts",
            "I",
            "disciplina_clubes: cartões conservados",
            "SELECT abs((SELECT coalesce(sum(amarelos) + sum(vermelhos), 0) FROM marts.disciplina_clubes) "
            "- (SELECT count(*) FROM refined.cartoes))",
        ),
        Verificacao(
            "marts",
            "I",
            "disciplina_clubes: NULL fora e preenchido dentro da cobertura",
            """
            SELECT count(*) FROM marts.disciplina_clubes
            WHERE (cobertura_cartoes AND (amarelos IS NULL OR vermelhos IS NULL))
               OR (NOT cobertura_cartoes AND (amarelos IS NOT NULL OR vermelhos IS NOT NULL
                                              OR amarelos_por_jogo IS NOT NULL OR vermelhos_por_jogo IS NOT NULL))""",
        ),
        # estatisticas_por_resultado
        Verificacao(
            "marts",
            "I",
            "estatisticas_por_resultado: chave (temporada, resultado, mando) única",
            "SELECT count(*) - count(DISTINCT (temporada, resultado, mando)) "
            "FROM marts.estatisticas_por_resultado",
        ),
        Verificacao(
            "marts",
            "I",
            "estatisticas_por_resultado: registros e n_* iguais aos valores válidos",
            f"""
            SELECT abs((SELECT sum(registros) FROM marts.estatisticas_por_resultado)
                       - (SELECT count(*) FROM {pc} WHERE estatisticas_disponiveis))
                 + """
            + " + ".join(
                f"abs((SELECT sum(n_{m}) FROM marts.estatisticas_por_resultado) "
                f"- (SELECT count({m}) FROM {pc} WHERE estatisticas_disponiveis))"
                for m in (
                    "chutes",
                    "chutes_no_alvo",
                    "posse_de_bola",
                    "passes",
                    "precisao_passes",
                    "faltas",
                    "escanteios",
                    "impedimentos",
                )
            ),
        ),
        # gols_por_faixa_minuto
        Verificacao(
            "marts",
            "I",
            "gols_por_faixa_minuto: exatamente as oito faixas aprovadas",
            """
            SELECT abs(count(*) - 8) + count(*) FILTER (WHERE faixa NOT IN
                   ('0-15', '16-30', '31-45', '45+', '46-60', '61-75', '76-90', '90+'))
                 + count(*) - count(DISTINCT faixa)
            FROM marts.gols_por_faixa_minuto""",
        ),
        Verificacao(
            "marts",
            "I",
            "gols_por_faixa_minuto: totais conservados",
            """
            SELECT abs((SELECT sum(gols) FROM marts.gols_por_faixa_minuto) - (SELECT count(*) FROM refined.gols))
                 + abs((SELECT sum(gols_penalti) FROM marts.gols_por_faixa_minuto)
                       - (SELECT count(*) FROM refined.gols WHERE penalti))
                 + abs((SELECT sum(gols_contra) FROM marts.gols_por_faixa_minuto)
                       - (SELECT count(*) FROM refined.gols WHERE gol_contra))
                 + (SELECT count(*) FROM marts.gols_por_faixa_minuto WHERE gols_mandante + gols_visitante <> gols)""",
        ),
        Verificacao(
            "marts",
            "I",
            "gols_por_faixa_minuto: acréscimo só nos minutos 45/90 e nenhum minuto > 90",
            """
            SELECT count(*) FROM refined.gols
            WHERE (acrescimo > 0 AND minuto NOT IN (45, 90)) OR (acrescimo = 0 AND minuto > 90)""",
        ),
        # resumo_temporadas
        Verificacao(
            "marts",
            "I",
            "resumo_temporadas: uma linha por temporada da REFINED",
            """
            SELECT (SELECT count(*) - count(DISTINCT temporada) FROM marts.resumo_temporadas)
                 + abs((SELECT count(*) FROM marts.resumo_temporadas)
                       - (SELECT count(DISTINCT temporada) FROM refined.partidas))""",
        ),
        Verificacao(
            "marts",
            "I",
            "resumo_temporadas: partidas, gols, cartões e estatísticas conservados",
            """
            SELECT abs((SELECT sum(partidas) FROM marts.resumo_temporadas) - (SELECT count(*) FROM refined.partidas))
                 + abs((SELECT sum(gols) FROM marts.resumo_temporadas)
                       - (SELECT sum(gols_mandante + gols_visitante) FROM refined.partidas))
                 + abs((SELECT coalesce(sum(gols_detalhados), 0) FROM marts.resumo_temporadas)
                       - (SELECT count(*) FROM refined.gols))
                 + abs((SELECT coalesce(sum(cartoes_amarelos) + sum(cartoes_vermelhos), 0)
                        FROM marts.resumo_temporadas) - (SELECT count(*) FROM refined.cartoes))
                 + abs((SELECT sum(partidas_com_estatisticas) FROM marts.resumo_temporadas)
                       - (SELECT count(DISTINCT partida_id) FROM refined.estatisticas
                          WHERE estatisticas_disponiveis))""",
        ),
        Verificacao(
            "marts",
            "I",
            "resumo_temporadas: primeiro colocado igual à posição 1 da classificação",
            """
            SELECT count(*) FROM marts.resumo_temporadas r
            WHERE primeiro_colocado_calculado IS DISTINCT FROM (
                SELECT string_agg(clube, ' / ' ORDER BY clube) FROM marts.classificacao c
                WHERE c.temporada = r.temporada AND c.posicao_calculada = 1)""",
        ),
        Verificacao(
            "marts",
            "I",
            "resumo_temporadas: totais detalhados NULL fora da cobertura",
            """
            SELECT count(*) FROM marts.resumo_temporadas
            WHERE cobertura_gols_detalhados <> (gols_detalhados IS NOT NULL)
               OR cobertura_cartoes_detalhados <> (cartoes_amarelos IS NOT NULL)""",
        ),
        # Expectativas do dataset
        Verificacao(
            "marts",
            "E",
            f"cobertura de gols detalhados nas temporadas {gi}-{gf}",
            f"SELECT count(*) FROM {pc} WHERE detalhe_gols_disponivel <> (temporada BETWEEN {gi} AND {gf})",
        ),
        Verificacao(
            "marts",
            "E",
            f"cobertura de cartões detalhados nas temporadas {ci}-{cf}",
            f"SELECT count(*) FROM {pc} WHERE detalhe_cartoes_disponivel <> (temporada BETWEEN {ci} AND {cf})",
        ),
    ]
    v += [
        Verificacao(
            "marts",
            "I",
            f"{t}.{col}: ROUND_HALF_UP exato com {casas} casa(s), tipo DECIMAL(10,{casas})",
            funcao=_arredondamento_exato(t, col, casas, sql, chave),
        )
        for t, col, casas, sql, chave in _COLUNAS_ARREDONDADAS
    ]
    return v


_CONSTRUTORES = {
    "raw": _verificacoes_raw,
    "refined": _verificacoes_refined,
    "marts": _verificacoes_marts,
}


def verificacoes(camada: str) -> list[Verificacao]:
    return _CONSTRUTORES[camada]()


def verificar_camada(con: duckdb.DuckDBPyConnection, camada: str) -> list[Resultado]:
    resultados = []
    for v in verificacoes(camada):
        try:
            if v.funcao is not None:
                violacoes = int(v.funcao(con))
            else:
                violacoes = int(con.execute(v.sql).fetchall()[0][0] or 0)
            resultados.append(Resultado(v, violacoes))
        except duckdb.Error as erro:
            resultados.append(Resultado(v, None, str(erro).splitlines()[0]))
    return resultados


def exigir_camada(con: duckdb.DuckDBPyConnection, camada: str) -> list[Resultado]:
    """Executa as verificações da camada e levanta FalhaDeQualidadeError se alguma falhar."""
    resultados = verificar_camada(con, camada)
    falhas = [r for r in resultados if not r.ok]
    if falhas:
        raise FalhaDeQualidadeError(camada, falhas)
    return resultados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verificações de qualidade do pipeline (somente leitura)"
    )
    parser.add_argument("--db", default=str(config.DB_PADRAO), help="arquivo DuckDB")
    parser.add_argument("--camada", choices=[*CAMADAS, "todas"], default="todas")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if not Path(args.db).is_file():
        print(f"ERRO: banco não encontrado: {args.db}", file=sys.stderr)
        return 1

    inicio = time.perf_counter()
    camadas = CAMADAS if args.camada == "todas" else (args.camada,)
    con = conectar(args.db, somente_leitura=True)
    try:
        resultados = {camada: verificar_camada(con, camada) for camada in camadas}
    finally:
        con.close()

    total_falhas = 0
    for camada, rs in resultados.items():
        falhas = [r for r in rs if not r.ok]
        total_falhas += len(falhas)
        print(f"{camada.upper():<8} {len(rs) - len(falhas):>3}/{len(rs):<3} aprovadas")
        for r in falhas:
            print(f"  FALHA {descrever(r)}")
    print(f"Tempo: {time.perf_counter() - inicio:.2f}s")
    return 1 if total_falhas else 0


if __name__ == "__main__":
    sys.exit(main())
