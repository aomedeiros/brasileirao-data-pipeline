-- Gols detalhados (a origem os traz a partir da temporada 2014).
--
-- clube: clube que recebeu o gol no placar; em gol contra, o atleta é do
-- adversário. tipo_gol fica NULL quando a origem está vazia (gol "normal");
-- as flags penalti e gol_contra tornam a análise explícita.
CREATE OR REPLACE TABLE refined.gols AS
SELECT
    CAST(row_number() OVER (
        ORDER BY CAST(g.partida_id AS INTEGER),
                 refined.minuto_base(g.minuto),
                 refined.minuto_acrescimo(g.minuto),
                 g.clube, g.atleta
    ) AS INTEGER)                                                AS gol_id,
    CAST(g.partida_id AS INTEGER)                                AS partida_id,
    c.clube_id,
    refined.texto(g.clube)                                       AS clube,
    refined.inteiro(g.rodata)                                    AS rodada,
    refined.texto(g.atleta)                                      AS atleta,
    refined.texto(g.minuto)                                      AS minuto_origem,
    refined.minuto_base(g.minuto)                                AS minuto,
    refined.minuto_acrescimo(g.minuto)                           AS acrescimo,
    refined.texto(g.tipo_de_gol)                                 AS tipo_gol,
    coalesce(refined.texto(g.tipo_de_gol) = 'Penalty', false)    AS penalti,
    coalesce(refined.texto(g.tipo_de_gol) = 'Gol Contra', false) AS gol_contra
FROM raw.gols g
JOIN refined.clubes c ON c.clube = refined.texto(g.clube)
ORDER BY gol_id;
