-- Disciplina por clube e temporada. Granularidade: temporada x clube (todas as
-- temporadas, inclusive as sem dados de cartões).
--
-- Fonte principal: arquivo detalhado de cartões (refined.cartoes).
-- Cobertura: uma temporada é coberta quando a fonte tem ao menos um cartão
-- nela (2014-2024). Dentro da cobertura, clube sem cartão conta 0; fora dela,
-- contadores e médias ficam NULL.
-- Limitação: dentro da cobertura não é possível distinguir "nenhum cartão"
-- de "cartão não registrado".
--
-- Média por jogo: denominador = todos os jogos do clube na temporada.
--
-- JOINs: marts.partida_clube (jogos e cobertura) x refined.clubes
--        x agregado de refined.cartoes x refined.partidas.
CREATE OR REPLACE TABLE marts.disciplina_clubes AS
WITH jogos AS (
    SELECT
        temporada,
        clube_id,
        CAST(count(*) AS INTEGER)       AS jogos,
        bool_and(detalhe_cartoes_disponivel) AS cobertura_cartoes
    FROM marts.partida_clube
    GROUP BY temporada, clube_id
),
cartoes AS (
    SELECT
        p.temporada,
        k.clube_id,
        count(*) FILTER (WHERE k.cartao = 'Amarelo')  AS amarelos,
        count(*) FILTER (WHERE k.cartao = 'Vermelho') AS vermelhos
    FROM refined.cartoes k
    JOIN refined.partidas p ON p.partida_id = k.partida_id
    GROUP BY p.temporada, k.clube_id
)
SELECT
    j.temporada,
    j.clube_id,
    c.clube,
    j.jogos,
    j.cobertura_cartoes,
    CASE WHEN j.cobertura_cartoes THEN CAST(coalesce(k.amarelos, 0) AS INTEGER) END  AS amarelos,
    CASE WHEN j.cobertura_cartoes THEN CAST(coalesce(k.vermelhos, 0) AS INTEGER) END AS vermelhos,
    CASE WHEN j.cobertura_cartoes THEN marts.arredondar_2(coalesce(k.amarelos, 0), j.jogos) END  AS amarelos_por_jogo,
    CASE WHEN j.cobertura_cartoes THEN marts.arredondar_2(coalesce(k.vermelhos, 0), j.jogos) END AS vermelhos_por_jogo
FROM jogos j
JOIN refined.clubes c ON c.clube_id = j.clube_id
LEFT JOIN cartoes k ON k.temporada = j.temporada AND k.clube_id = j.clube_id
ORDER BY j.temporada, c.clube;
