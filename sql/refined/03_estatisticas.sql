-- Estatísticas de cada clube por partida (duas linhas por partida).
--
-- estatisticas_disponiveis: na origem, jogos sem coleta de estatísticas aparecem
-- com todos os contadores zerados e sem posse de bola. Os valores originais são
-- mantidos; a flag permite que as análises não confundam "não coletado" com zero.
-- A flag é calculada sobre os valores originais (antes do ajuste de passes).
--
-- passes: entre as linhas com estatísticas disponíveis, passes = 0 com
-- precisao_passes ausente indica que os passes não foram registrados (há posse
-- e chutes registrados na mesma linha). Nesses casos, passes vira NULL apenas
-- na REFINED; a RAW mantém o valor original '0'.
CREATE OR REPLACE TABLE refined.estatisticas AS
WITH base AS (
    SELECT
        CAST(partida_id AS INTEGER)          AS partida_id,
        refined.inteiro(rodata)              AS rodada,
        refined.texto(clube)                 AS clube,
        refined.inteiro(chutes)              AS chutes,
        refined.inteiro(chutes_no_alvo)      AS chutes_no_alvo,
        refined.percentual(posse_de_bola)    AS posse_de_bola,
        refined.inteiro(passes)              AS passes,
        refined.percentual(precisao_passes)  AS precisao_passes,
        refined.inteiro(faltas)              AS faltas,
        refined.inteiro(cartao_amarelo)      AS cartao_amarelo,
        refined.inteiro(cartao_vermelho)     AS cartao_vermelho,
        refined.inteiro(impedimentos)        AS impedimentos,
        refined.inteiro(escanteios)          AS escanteios
    FROM raw.estatisticas
),
com_flag AS (
    SELECT
        b.*,
        NOT (
            coalesce(b.chutes, 0) = 0
            AND coalesce(b.chutes_no_alvo, 0) = 0
            AND coalesce(b.passes, 0) = 0
            AND coalesce(b.faltas, 0) = 0
            AND coalesce(b.escanteios, 0) = 0
            AND coalesce(b.impedimentos, 0) = 0
            AND b.posse_de_bola IS NULL
        ) AS estatisticas_disponiveis
    FROM base b
)
SELECT
    f.partida_id,
    c.clube_id,
    f.clube,
    f.rodada,
    f.chutes,
    f.chutes_no_alvo,
    f.posse_de_bola,
    CASE
        WHEN f.estatisticas_disponiveis AND f.passes = 0 AND f.precisao_passes IS NULL
        THEN NULL
        ELSE f.passes
    END AS passes,
    f.precisao_passes,
    f.faltas,
    f.cartao_amarelo,
    f.cartao_vermelho,
    f.impedimentos,
    f.escanteios,
    f.estatisticas_disponiveis
FROM com_flag f
JOIN refined.clubes c ON c.clube = f.clube
ORDER BY f.partida_id, c.clube_id;
