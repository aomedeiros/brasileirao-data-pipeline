-- Cartões detalhados (a origem os traz nas temporadas 2014 a 2024).
--
-- posicao_origem: posição como veio da origem (apenas limpeza de texto).
-- posicao: valor padronizado. Os 22 registros com 'Zagueira' (todos do mesmo
-- atleta) passam a 'Zagueiro'. Ausências continuam NULL nas duas colunas.
CREATE OR REPLACE TABLE refined.cartoes AS
SELECT
    CAST(row_number() OVER (
        ORDER BY CAST(k.partida_id AS INTEGER),
                 refined.minuto_base(k.minuto),
                 refined.minuto_acrescimo(k.minuto),
                 k.clube, k.atleta, k.cartao
    ) AS INTEGER)                           AS cartao_id,
    CAST(k.partida_id AS INTEGER)           AS partida_id,
    c.clube_id,
    refined.texto(k.clube)                  AS clube,
    refined.inteiro(k.rodata)               AS rodada,
    refined.texto(k.cartao)                 AS cartao,
    refined.texto(k.atleta)                 AS atleta,
    refined.inteiro(k.num_camisa)           AS num_camisa,
    refined.texto(k.posicao)                AS posicao_origem,
    CASE refined.texto(k.posicao)
        WHEN 'Zagueira' THEN 'Zagueiro'
        ELSE refined.texto(k.posicao)
    END                                     AS posicao,
    refined.texto(k.minuto)                 AS minuto_origem,
    refined.minuto_base(k.minuto)           AS minuto,
    refined.minuto_acrescimo(k.minuto)      AS acrescimo
FROM raw.cartoes k
JOIN refined.clubes c ON c.clube = refined.texto(k.clube)
ORDER BY cartao_id;
