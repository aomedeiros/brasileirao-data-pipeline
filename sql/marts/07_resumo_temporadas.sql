-- Visão geral de cada temporada. Granularidade: temporada.
--
-- primeiro_colocado_calculado: posição 1 de marts.classificacao, que é uma
-- classificação calculada (não oficial). Em caso de empate completo na
-- primeira posição, os clubes aparecem juntos, separados por ' / '.
--
-- Cobertura das fontes:
-- - cobertura_gols_detalhados / cobertura_cartoes_detalhados: a temporada tem
--   registros na fonte detalhada; fora da cobertura, os totais ficam NULL;
-- - partidas_com_estatisticas: partidas com estatísticas coletadas (0 = nenhuma);
-- - partidas_com_arrecadacao: partidas com arrecadação informada; o total
--   fica NULL quando não há nenhuma.
--
-- JOINs: refined.partidas x agregados de gols, cartões e estatísticas (LEFT)
--        x marts.classificacao x marts.partida_clube (cobertura e clubes).
CREATE OR REPLACE TABLE marts.resumo_temporadas AS
WITH partidas AS (
    SELECT
        temporada,
        CAST(count(*) AS INTEGER)                                    AS partidas,
        CAST(count(DISTINCT rodada) AS INTEGER)                      AS rodadas,
        CAST(sum(gols_mandante + gols_visitante) AS INTEGER)         AS gols,
        count(*) FILTER (WHERE resultado = 'mandante')               AS vitorias_mandante,
        count(*) FILTER (WHERE resultado = 'empate')                 AS empates,
        count(*) FILTER (WHERE resultado = 'visitante')              AS vitorias_visitante,
        min(data_partida)                                            AS inicio,
        max(data_partida)                                            AS fim,
        CAST(count(arrecadacao) AS INTEGER)                          AS partidas_com_arrecadacao,
        sum(arrecadacao)                                             AS arrecadacao_total
    FROM refined.partidas
    GROUP BY temporada
),
cobertura AS (
    SELECT
        temporada,
        CAST(count(DISTINCT clube_id) AS INTEGER) AS clubes,
        bool_and(detalhe_gols_disponivel)         AS cobertura_gols_detalhados,
        bool_and(detalhe_cartoes_disponivel)      AS cobertura_cartoes_detalhados
    FROM marts.partida_clube
    GROUP BY temporada
),
gols AS (
    SELECT p.temporada, count(*) AS gols_detalhados
    FROM refined.gols g
    JOIN refined.partidas p ON p.partida_id = g.partida_id
    GROUP BY p.temporada
),
cartoes AS (
    SELECT p.temporada,
           count(*) FILTER (WHERE k.cartao = 'Amarelo')  AS cartoes_amarelos,
           count(*) FILTER (WHERE k.cartao = 'Vermelho') AS cartoes_vermelhos
    FROM refined.cartoes k
    JOIN refined.partidas p ON p.partida_id = k.partida_id
    GROUP BY p.temporada
),
estatisticas AS (
    SELECT p.temporada,
           count(DISTINCT e.partida_id) FILTER (WHERE e.estatisticas_disponiveis) AS partidas_com_estatisticas
    FROM refined.estatisticas e
    JOIN refined.partidas p ON p.partida_id = e.partida_id
    GROUP BY p.temporada
),
primeiro AS (
    SELECT temporada,
           string_agg(clube, ' / ' ORDER BY clube) AS primeiro_colocado_calculado,
           any_value(pontos)                       AS pontos_primeiro
    FROM marts.classificacao
    WHERE posicao_calculada = 1
    GROUP BY temporada
)
SELECT
    p.temporada,
    p.inicio,
    p.fim,
    c.clubes,
    p.rodadas,
    p.partidas,
    p.gols,
    marts.arredondar_2(p.gols, p.partidas)                          AS media_gols_por_partida,
    marts.arredondar_1(100 * p.vitorias_mandante, p.partidas)       AS pct_vitorias_mandante,
    marts.arredondar_1(100 * p.empates, p.partidas)                 AS pct_empates,
    marts.arredondar_1(100 * p.vitorias_visitante, p.partidas)      AS pct_vitorias_visitante,
    pr.primeiro_colocado_calculado,
    pr.pontos_primeiro,
    c.cobertura_gols_detalhados,
    CASE WHEN c.cobertura_gols_detalhados THEN CAST(coalesce(g.gols_detalhados, 0) AS INTEGER) END       AS gols_detalhados,
    c.cobertura_cartoes_detalhados,
    CASE WHEN c.cobertura_cartoes_detalhados THEN CAST(coalesce(k.cartoes_amarelos, 0) AS INTEGER) END   AS cartoes_amarelos,
    CASE WHEN c.cobertura_cartoes_detalhados THEN CAST(coalesce(k.cartoes_vermelhos, 0) AS INTEGER) END  AS cartoes_vermelhos,
    CAST(coalesce(e.partidas_com_estatisticas, 0) AS INTEGER)       AS partidas_com_estatisticas,
    p.partidas_com_arrecadacao,
    p.arrecadacao_total
FROM partidas p
JOIN cobertura c      ON c.temporada = p.temporada
JOIN primeiro pr      ON pr.temporada = p.temporada
LEFT JOIN gols g      ON g.temporada = p.temporada
LEFT JOIN cartoes k   ON k.temporada = p.temporada
LEFT JOIN estatisticas e ON e.temporada = p.temporada
ORDER BY p.temporada;
