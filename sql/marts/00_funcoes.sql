-- Funções de arredondamento da camada MARTS.
--
-- Regra oficial: ROUND_HALF_UP (meio para cima), calculada com aritmética
-- inteira exata. O resultado é a fração numerador / denominador arredondada
-- para a escala da função, devolvida como DECIMAL exato.
--
-- Por que não usar round(avg(x), n):
--   avg() e a divisão de DECIMAL devolvem DOUBLE no DuckDB 2.x, e round() sobre
--   DOUBLE decide os casos de meio de forma inconsistente (0,145 -> 0,14, mas
--   10,635 -> 10,64), porque depende da representação binária do valor.
--
-- Algoritmo, para escala c (2 ou 1 casas):
--   q = (2 * numerador * 10^c + denominador) // (2 * denominador)
--   resultado = q * 10^(-c)
-- A divisão inteira (//) trunca; somar meio denominador antes de dividir
-- implementa o meio para cima. Todas as operações são inteiras (HUGEINT),
-- e a conversão final multiplica por um DECIMAL, o que mantém o valor exato.
--
-- Premissas (validadas explicitamente; se violadas, a execução falha):
--   - numerador e denominador são não negativos (todas as métricas atuais são
--     contagens, somas de contagens ou percentuais);
--   - numerador e denominador são inteiros. Para métricas com casas decimais
--     (posse e precisão de passes), passe a soma em centésimos e multiplique o
--     denominador por 100.
-- NULL: numerador ou denominador NULL, ou denominador 0, devolve NULL (média
-- sobre nenhum valor válido, como avg()).

CREATE OR REPLACE MACRO marts.arredondar_2(numerador, denominador) AS
    CASE
        WHEN numerador IS NULL OR denominador IS NULL OR denominador = 0 THEN NULL
        WHEN numerador < 0 OR denominador < 0 THEN
            error('marts.arredondar_2: numerador e denominador devem ser não negativos')
        WHEN numerador <> CAST(numerador AS HUGEINT) OR denominador <> CAST(denominador AS HUGEINT) THEN
            error('marts.arredondar_2: numerador e denominador devem ser inteiros')
        ELSE CAST(
            CAST((200 * CAST(numerador AS HUGEINT) + CAST(denominador AS HUGEINT))
                 // (2 * CAST(denominador AS HUGEINT)) AS DECIMAL(38, 0))
            * CAST(0.01 AS DECIMAL(3, 2))
            AS DECIMAL(10, 2))
    END;

CREATE OR REPLACE MACRO marts.arredondar_1(numerador, denominador) AS
    CASE
        WHEN numerador IS NULL OR denominador IS NULL OR denominador = 0 THEN NULL
        WHEN numerador < 0 OR denominador < 0 THEN
            error('marts.arredondar_1: numerador e denominador devem ser não negativos')
        WHEN numerador <> CAST(numerador AS HUGEINT) OR denominador <> CAST(denominador AS HUGEINT) THEN
            error('marts.arredondar_1: numerador e denominador devem ser inteiros')
        ELSE CAST(
            CAST((20 * CAST(numerador AS HUGEINT) + CAST(denominador AS HUGEINT))
                 // (2 * CAST(denominador AS HUGEINT)) AS DECIMAL(38, 0))
            * CAST(0.1 AS DECIMAL(2, 1))
            AS DECIMAL(10, 1))
    END;
