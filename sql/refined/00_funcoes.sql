-- Funções de limpeza usadas pelos scripts da camada REFINED.
-- A RAW guarda os campos exatamente como no CSV (vazios como '');
-- a conversão de ausências para NULL acontece aqui, de forma explícita.

-- Texto limpo: troca o espaço não separável (NBSP, U+00A0) por espaço comum,
-- remove espaços nas pontas e converte '' e 'None' em NULL.
CREATE OR REPLACE MACRO refined.texto(s) AS
    nullif(nullif(trim(replace(s, chr(160), ' ')), ''), 'None');

-- Inteiro a partir de texto. Falha (em vez de silenciar) se o valor não for numérico.
CREATE OR REPLACE MACRO refined.inteiro(s) AS
    CAST(refined.texto(s) AS INTEGER);

-- Percentual '54%' -> 54.00.
CREATE OR REPLACE MACRO refined.percentual(s) AS
    CAST(replace(refined.texto(s), '%', '') AS DECIMAL(5, 2));

-- Minuto '90+3' -> minuto regulamentar 90 e acréscimo 3 ('35' -> 35 e 0).
CREATE OR REPLACE MACRO refined.minuto_base(s) AS
    CAST(split_part(refined.texto(s), '+', 1) AS INTEGER);

CREATE OR REPLACE MACRO refined.minuto_acrescimo(s) AS
    CASE WHEN contains(refined.texto(s), '+')
         THEN CAST(split_part(refined.texto(s), '+', 2) AS INTEGER)
         ELSE 0
    END;
