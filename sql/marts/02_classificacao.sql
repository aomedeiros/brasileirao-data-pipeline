-- Classificação CALCULADA de cada temporada (não é a classificação oficial).
--
-- Considera apenas resultados de campo: vitória = 3 pontos, empate = 1.
-- Punições aplicadas fora de campo (perda de pontos) não constam na origem.
--
-- Ordenação: pontos, vitórias, saldo de gols e gols pró (nessa ordem).
-- Nenhum outro critério de desempate é aplicado: clubes empatados em todos os
-- quatro critérios recebem a mesma posicao_calculada (rank()).
--
-- JOINs: marts.partida_clube x refined.clubes.
CREATE OR REPLACE TABLE marts.classificacao AS
WITH totais AS (
    SELECT
        temporada,
        clube_id,
        CAST(count(*) AS INTEGER)                               AS jogos,
        CAST(sum(pontos) AS INTEGER)                            AS pontos,
        CAST(count(*) FILTER (WHERE resultado = 'vitoria') AS INTEGER) AS vitorias,
        CAST(count(*) FILTER (WHERE resultado = 'empate') AS INTEGER)  AS empates,
        CAST(count(*) FILTER (WHERE resultado = 'derrota') AS INTEGER) AS derrotas,
        CAST(sum(gols_pro) AS INTEGER)                          AS gols_pro,
        CAST(sum(gols_contra) AS INTEGER)                       AS gols_contra,
        CAST(sum(saldo_gols) AS INTEGER)                        AS saldo_gols
    FROM marts.partida_clube
    GROUP BY temporada, clube_id
)
SELECT
    t.temporada,
    CAST(rank() OVER (
        PARTITION BY t.temporada
        ORDER BY t.pontos DESC, t.vitorias DESC, t.saldo_gols DESC, t.gols_pro DESC
    ) AS INTEGER)                                               AS posicao_calculada,
    t.clube_id,
    c.clube,
    c.uf,
    t.jogos,
    t.pontos,
    t.vitorias,
    t.empates,
    t.derrotas,
    t.gols_pro,
    t.gols_contra,
    t.saldo_gols,
    marts.arredondar_1(100 * t.pontos, 3 * t.jogos)             AS aproveitamento_pct
FROM totais t
JOIN refined.clubes c ON c.clube_id = t.clube_id
ORDER BY t.temporada, posicao_calculada, c.clube;
