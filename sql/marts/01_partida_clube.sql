-- Tabela analítica base: uma linha por clube em cada partida (2 por partida).
--
-- JOINs: refined.partidas (desdobrada em mandante e visitante)
--        x refined.clubes (clube e adversário)
--        x refined.estatisticas (LEFT, por partida_id + clube_id)
--        x agregados de refined.gols e refined.cartoes (LEFT)
--
-- Cobertura (NULL = dado não disponível, 0 = nenhum evento registrado):
-- - estatísticas: por linha, conforme refined.estatisticas.estatisticas_disponiveis;
--   fora da cobertura, todas as métricas ficam NULL;
-- - gols e cartões detalhados: por temporada; uma temporada é coberta quando a
--   fonte tem ao menos um registro nela (gols: 2014-2025; cartões: 2014-2024).
--   Dentro da cobertura, ausência de evento conta 0; fora dela, NULL.
--   Limitação: dentro da cobertura não é possível distinguir "nenhum cartão"
--   de "cartão não registrado".
CREATE OR REPLACE TABLE marts.partida_clube AS
WITH lados AS (
    SELECT partida_id, temporada, rodada, data_partida, arena,
           'mandante' AS mando,
           mandante_id AS clube_id, visitante_id AS adversario_id,
           gols_mandante AS gols_pro, gols_visitante AS gols_contra,
           tecnico_mandante AS tecnico, formacao_mandante AS formacao
    FROM refined.partidas
    UNION ALL
    SELECT partida_id, temporada, rodada, data_partida, arena,
           'visitante',
           visitante_id, mandante_id,
           gols_visitante, gols_mandante,
           tecnico_visitante, formacao_visitante
    FROM refined.partidas
),
cobertura_gols AS (
    SELECT DISTINCT p.temporada
    FROM refined.gols g
    JOIN refined.partidas p ON p.partida_id = g.partida_id
),
cobertura_cartoes AS (
    SELECT DISTINCT p.temporada
    FROM refined.cartoes k
    JOIN refined.partidas p ON p.partida_id = k.partida_id
),
gols_agg AS (
    SELECT partida_id, clube_id,
           count(*) FILTER (WHERE penalti)    AS gols_penalti,
           count(*) FILTER (WHERE gol_contra) AS gols_contra_a_favor
    FROM refined.gols
    GROUP BY partida_id, clube_id
),
cartoes_agg AS (
    SELECT partida_id, clube_id,
           count(*) FILTER (WHERE cartao = 'Amarelo')  AS cartoes_amarelos,
           count(*) FILTER (WHERE cartao = 'Vermelho') AS cartoes_vermelhos
    FROM refined.cartoes
    GROUP BY partida_id, clube_id
)
SELECT
    l.partida_id,
    l.temporada,
    l.rodada,
    l.data_partida,
    l.arena,
    l.mando,
    l.clube_id,
    c.clube,
    c.uf,
    l.adversario_id,
    a.clube                                       AS adversario,
    l.tecnico,
    l.formacao,
    l.gols_pro,
    l.gols_contra,
    l.gols_pro - l.gols_contra                    AS saldo_gols,
    CASE WHEN l.gols_pro > l.gols_contra THEN 'vitoria'
         WHEN l.gols_pro = l.gols_contra THEN 'empate'
         ELSE 'derrota'
    END                                           AS resultado,
    CASE WHEN l.gols_pro > l.gols_contra THEN 3
         WHEN l.gols_pro = l.gols_contra THEN 1
         ELSE 0
    END                                           AS pontos,
    -- Estatísticas: NULL quando não coletadas.
    e.estatisticas_disponiveis,
    CASE WHEN e.estatisticas_disponiveis THEN e.chutes END          AS chutes,
    CASE WHEN e.estatisticas_disponiveis THEN e.chutes_no_alvo END  AS chutes_no_alvo,
    CASE WHEN e.estatisticas_disponiveis THEN e.posse_de_bola END   AS posse_de_bola,
    CASE WHEN e.estatisticas_disponiveis THEN e.passes END          AS passes,
    CASE WHEN e.estatisticas_disponiveis THEN e.precisao_passes END AS precisao_passes,
    CASE WHEN e.estatisticas_disponiveis THEN e.faltas END          AS faltas,
    CASE WHEN e.estatisticas_disponiveis THEN e.impedimentos END    AS impedimentos,
    CASE WHEN e.estatisticas_disponiveis THEN e.escanteios END      AS escanteios,
    -- Gols detalhados: 0 dentro da cobertura, NULL fora dela.
    cg.temporada IS NOT NULL                      AS detalhe_gols_disponivel,
    CASE WHEN cg.temporada IS NOT NULL THEN coalesce(g.gols_penalti, 0) END        AS gols_penalti,
    CASE WHEN cg.temporada IS NOT NULL THEN coalesce(g.gols_contra_a_favor, 0) END AS gols_contra_a_favor,
    -- Cartões detalhados: 0 dentro da cobertura, NULL fora dela.
    ck.temporada IS NOT NULL                      AS detalhe_cartoes_disponivel,
    CASE WHEN ck.temporada IS NOT NULL THEN coalesce(k.cartoes_amarelos, 0) END    AS cartoes_amarelos,
    CASE WHEN ck.temporada IS NOT NULL THEN coalesce(k.cartoes_vermelhos, 0) END   AS cartoes_vermelhos
FROM lados l
JOIN refined.clubes c ON c.clube_id = l.clube_id
JOIN refined.clubes a ON a.clube_id = l.adversario_id
LEFT JOIN refined.estatisticas e ON e.partida_id = l.partida_id AND e.clube_id = l.clube_id
LEFT JOIN gols_agg g             ON g.partida_id = l.partida_id AND g.clube_id = l.clube_id
LEFT JOIN cartoes_agg k          ON k.partida_id = l.partida_id AND k.clube_id = l.clube_id
LEFT JOIN cobertura_gols cg      ON cg.temporada = l.temporada
LEFT JOIN cobertura_cartoes ck   ON ck.temporada = l.temporada
ORDER BY l.partida_id, l.mando;
