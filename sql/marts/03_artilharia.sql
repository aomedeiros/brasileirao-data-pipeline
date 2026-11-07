-- Artilharia por temporada (gols detalhados existem a partir de 2014).
-- Granularidade: temporada x atleta x clube.
--
-- Regras:
-- - gols contra são excluídos (não contam para o atleta);
-- - um atleta que atuou por mais de um clube na temporada aparece uma vez por clube;
-- - ranking por gols na temporada, com empates na mesma posição (rank()).
--
-- Limitação: a origem não tem identificador individual de atleta; atletas
-- homônimos no mesmo clube e temporada são agrupados na mesma linha.
--
-- JOINs: refined.gols x refined.partidas (temporada) x refined.clubes.
CREATE OR REPLACE TABLE marts.artilharia AS
WITH gols_atleta AS (
    SELECT
        p.temporada,
        g.atleta,
        g.clube_id,
        c.clube,
        CAST(count(*) AS INTEGER)                          AS gols,
        CAST(count(*) FILTER (WHERE g.penalti) AS INTEGER) AS gols_penalti,
        CAST(count(DISTINCT g.partida_id) AS INTEGER)      AS partidas_com_gol
    FROM refined.gols g
    JOIN refined.partidas p ON p.partida_id = g.partida_id
    JOIN refined.clubes c   ON c.clube_id = g.clube_id
    WHERE NOT g.gol_contra
    GROUP BY p.temporada, g.atleta, g.clube_id, c.clube
)
SELECT
    temporada,
    CAST(rank() OVER (PARTITION BY temporada ORDER BY gols DESC) AS INTEGER) AS ranking,
    atleta,
    clube_id,
    clube,
    gols,
    gols_penalti,
    partidas_com_gol
FROM gols_atleta
ORDER BY temporada, ranking, atleta, clube;
