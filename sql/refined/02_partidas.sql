-- Partidas tipadas, limpas e ligadas à dimensão de clubes.
--
-- temporada: ano da data, exceto jogos de janeiro e fevereiro, que pertencem à
-- temporada anterior. Em 2003-2025 isso só ocorre na temporada 2020, que por
-- causa da pandemia terminou em fevereiro de 2021.
CREATE OR REPLACE TABLE refined.partidas AS
WITH base AS (
    SELECT
        CAST(ID AS INTEGER)                                 AS partida_id,
        refined.inteiro(rodata)                             AS rodada,
        CAST(strptime(data, '%d/%m/%Y') AS DATE)            AS data_partida,
        CAST(refined.texto(hora) AS TIME)                   AS hora_partida,
        refined.texto(mandante)                             AS mandante,
        refined.texto(visitante)                            AS visitante,
        refined.texto(formacao_mandante)                    AS formacao_mandante,
        refined.texto(formacao_visitante)                   AS formacao_visitante,
        refined.texto(tecnico_mandante)                     AS tecnico_mandante,
        refined.texto(tecnico_visitante)                    AS tecnico_visitante,
        refined.texto(vencedor)                             AS vencedor_origem,
        refined.texto(arena)                                AS arena,
        refined.inteiro(mandante_Placar)                    AS gols_mandante,
        refined.inteiro(visitante_Placar)                   AS gols_visitante,
        refined.texto(mandante_Estado)                      AS uf_mandante,
        refined.texto(visitante_Estado)                     AS uf_visitante,
        CAST(refined.texto(arrecadacao) AS DECIMAL(14, 2))  AS arrecadacao
    FROM raw.partidas
)
SELECT
    b.partida_id,
    CAST(CASE WHEN month(b.data_partida) <= 2
              THEN year(b.data_partida) - 1
              ELSE year(b.data_partida)
         END AS INTEGER)                                    AS temporada,
    b.rodada,
    b.data_partida,
    b.hora_partida,
    ['Domingo', 'Segunda-feira', 'Terça-feira', 'Quarta-feira',
     'Quinta-feira', 'Sexta-feira', 'Sábado'][dayofweek(b.data_partida) + 1] AS dia_semana,
    m.clube_id                                              AS mandante_id,
    b.mandante,
    v.clube_id                                              AS visitante_id,
    b.visitante,
    b.gols_mandante,
    b.gols_visitante,
    CASE WHEN b.gols_mandante > b.gols_visitante THEN 'mandante'
         WHEN b.gols_mandante < b.gols_visitante THEN 'visitante'
         ELSE 'empate'
    END                                                     AS resultado,
    -- Na origem, empate aparece como '-'; aqui fica NULL.
    CASE WHEN b.vencedor_origem = '-' THEN NULL ELSE b.vencedor_origem END AS vencedor,
    b.formacao_mandante,
    b.formacao_visitante,
    b.tecnico_mandante,
    b.tecnico_visitante,
    b.arena,
    b.uf_mandante,
    b.uf_visitante,
    b.arrecadacao
FROM base b
JOIN refined.clubes m ON m.clube = b.mandante
JOIN refined.clubes v ON v.clube = b.visitante
ORDER BY b.partida_id;
