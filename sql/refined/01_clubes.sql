-- Dimensão de clubes: um registro por clube, com chave substituta clube_id
-- (atribuída em ordem alfabética do nome). A UF vem das colunas
-- mandante_Estado / visitante_Estado das partidas.
CREATE OR REPLACE TABLE refined.clubes AS
WITH aparicoes AS (
    SELECT refined.texto(mandante) AS clube, refined.texto(mandante_Estado) AS uf
    FROM raw.partidas
    UNION ALL
    SELECT refined.texto(visitante), refined.texto(visitante_Estado)
    FROM raw.partidas
)
SELECT
    CAST(row_number() OVER (ORDER BY clube) AS INTEGER) AS clube_id,
    clube,
    mode(uf)                                            AS uf,
    CAST(count(DISTINCT uf) AS INTEGER)                 AS qtd_ufs_na_origem,
    CAST(count(*) AS INTEGER)                           AS total_partidas
FROM aparicoes
GROUP BY clube
ORDER BY clube_id;
