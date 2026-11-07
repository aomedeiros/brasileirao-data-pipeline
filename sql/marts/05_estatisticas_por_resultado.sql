-- Médias das estatísticas de jogo por temporada, resultado e mando de campo.
-- Granularidade: temporada x resultado x mando.
--
-- Considera apenas linhas com estatísticas coletadas (estatisticas_disponiveis);
-- temporadas sem nenhuma coleta não geram linhas.
-- Cada média vem acompanhada de n_<métrica>: quantidade de valores válidos
-- (não nulos) que a compõem. As bases podem diferir entre métricas, pois
-- posse, passes e precisão de passes têm valores ausentes na origem.
--
-- JOINs: herdados de marts.partida_clube (partidas x clubes x estatísticas).
CREATE OR REPLACE TABLE marts.estatisticas_por_resultado AS
SELECT
    temporada,
    resultado,
    mando,
    CAST(count(*) AS INTEGER)               AS registros,
    marts.arredondar_2(sum(gols_pro), count(gols_pro))                 AS media_gols,
    marts.arredondar_2(sum(chutes), count(chutes))                     AS media_chutes,
    CAST(count(chutes) AS INTEGER)                                     AS n_chutes,
    marts.arredondar_2(sum(chutes_no_alvo), count(chutes_no_alvo))     AS media_chutes_no_alvo,
    CAST(count(chutes_no_alvo) AS INTEGER)                             AS n_chutes_no_alvo,
    -- posse e precisão têm 2 casas: soma em centésimos, denominador x 100.
    marts.arredondar_2(sum(posse_de_bola * 100), count(posse_de_bola) * 100)     AS media_posse_de_bola,
    CAST(count(posse_de_bola) AS INTEGER)                              AS n_posse_de_bola,
    marts.arredondar_1(sum(passes), count(passes))                     AS media_passes,
    CAST(count(passes) AS INTEGER)                                     AS n_passes,
    marts.arredondar_2(sum(precisao_passes * 100), count(precisao_passes) * 100) AS media_precisao_passes,
    CAST(count(precisao_passes) AS INTEGER)                            AS n_precisao_passes,
    marts.arredondar_2(sum(faltas), count(faltas))                     AS media_faltas,
    CAST(count(faltas) AS INTEGER)                                     AS n_faltas,
    marts.arredondar_2(sum(escanteios), count(escanteios))             AS media_escanteios,
    CAST(count(escanteios) AS INTEGER)                                 AS n_escanteios,
    marts.arredondar_2(sum(impedimentos), count(impedimentos))         AS media_impedimentos,
    CAST(count(impedimentos) AS INTEGER)                               AS n_impedimentos
FROM marts.partida_clube
WHERE estatisticas_disponiveis
GROUP BY temporada, resultado, mando
ORDER BY temporada,
         CASE resultado WHEN 'vitoria' THEN 1 WHEN 'empate' THEN 2 ELSE 3 END,
         mando;
