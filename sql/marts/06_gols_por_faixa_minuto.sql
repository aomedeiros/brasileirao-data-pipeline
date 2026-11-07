-- Distribuição dos gols detalhados (2014-2025) por faixa de minuto.
-- Granularidade: faixa (8 faixas, sem sobreposição).
--
-- A faixa considera minuto e acréscimo em conjunto:
--   0-15, 16-30, 31-45  : primeiro tempo, sem acréscimo (minuto 45 entra em 31-45)
--   45+                 : acréscimos do primeiro tempo (minuto <= 45 com acréscimo)
--   46-60, 61-75, 76-90 : segundo tempo, sem acréscimo (minuto 90 entra em 76-90)
--   90+                 : acréscimos do segundo tempo (minuto > 45 com acréscimo)
--
-- JOINs: refined.gols x refined.partidas (para separar mandante e visitante).
CREATE OR REPLACE TABLE marts.gols_por_faixa_minuto AS
WITH faixas AS (
    SELECT * FROM (VALUES
        (1, '0-15'), (2, '16-30'), (3, '31-45'), (4, '45+'),
        (5, '46-60'), (6, '61-75'), (7, '76-90'), (8, '90+')
    ) AS f(ordem, faixa)
),
gols AS (
    SELECT
        g.penalti,
        g.gol_contra,
        g.clube_id = p.mandante_id AS gol_do_mandante,
        CASE
            WHEN g.acrescimo > 0 AND g.minuto <= 45 THEN '45+'
            WHEN g.acrescimo > 0                    THEN '90+'
            WHEN g.minuto <= 15 THEN '0-15'
            WHEN g.minuto <= 30 THEN '16-30'
            WHEN g.minuto <= 45 THEN '31-45'
            WHEN g.minuto <= 60 THEN '46-60'
            WHEN g.minuto <= 75 THEN '61-75'
            ELSE '76-90'
        END AS faixa
    FROM refined.gols g
    JOIN refined.partidas p ON p.partida_id = g.partida_id
)
SELECT
    f.ordem,
    f.faixa,
    CAST(count(g.faixa) AS INTEGER)                                        AS gols,
    marts.arredondar_2(100 * count(g.faixa), sum(count(g.faixa)) OVER ())  AS pct_gols,
    CAST(count(g.faixa) FILTER (WHERE g.gol_do_mandante) AS INTEGER)       AS gols_mandante,
    CAST(count(g.faixa) FILTER (WHERE NOT g.gol_do_mandante) AS INTEGER)   AS gols_visitante,
    CAST(count(g.faixa) FILTER (WHERE g.penalti) AS INTEGER)               AS gols_penalti,
    CAST(count(g.faixa) FILTER (WHERE g.gol_contra) AS INTEGER)            AS gols_contra
FROM faixas f
LEFT JOIN gols g ON g.faixa = f.faixa
GROUP BY f.ordem, f.faixa
ORDER BY f.ordem;
