-- Dimensão de clubes: um registro por clube, com chave substituta clube_id
-- (atribuída pela ordenação binária do nome; ex.: 'CSA' antes de 'Ceara').
-- A UF vem das colunas mandante_Estado / visitante_Estado das partidas; a
-- unicidade da UF por clube é conferida em pipeline/qualidade.py.
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
    CAST(count(*) AS INTEGER)                           AS total_partidas
FROM aparicoes
GROUP BY clube
ORDER BY clube_id;
