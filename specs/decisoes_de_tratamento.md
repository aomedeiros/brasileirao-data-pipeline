# Decisões de tratamento e regras do pipeline

Registro das decisões técnicas e das regras de negócio implementadas no pipeline
Brasileirão Data Pipeline (RAW → REFINED → MARTS, em DuckDB).

Cada item é classificado como:

- **Implementado** — regra presente no código (Python ou SQL), com o arquivo indicado;
- **Premissa** — suposição adotada sobre a origem dos dados, sobre a qual a regra se apoia;
- **Limitação** — característica da origem ou do pipeline que restringe a interpretação dos resultados.

Os números citados foram medidos em 07/11/2026 sobre a versão do dataset descrita em
`config.EXPECTATIVAS` (seção 11). Se a origem mudar, as verificações de qualidade do tipo
"E" falham até que esses valores sejam revistos.

---

## 1. Arquitetura

| Camada | Schema | Implementação | Papel |
|---|---|---|---|
| RAW | `raw` | `pipeline/ingestao.py` | Cópia fiel dos quatro CSVs, sem conversão |
| REFINED | `refined` | `pipeline/transformacao.py` + `sql/refined/*.sql` | Tipagem, limpeza, chaves e relacionamentos |
| MARTS | `marts` | `pipeline/marts.py` + `sql/marts/*.sql` | Tabelas analíticas |
| Qualidade | — | `pipeline/qualidade.py` | 84 verificações executadas dentro de cada camada |

- **Implementado.** Tudo fica num único arquivo DuckDB (`data/brasileirao.duckdb`), com um schema por camada (`config.DB_PADRAO`).
- **Implementado.** Os scripts SQL de cada pasta são executados em ordem alfabética (`00_`, `01_`, …) numa única transação (`db.executar_scripts`). Todas as tabelas usam `CREATE OR REPLACE`, o que torna cada camada reexecutável sem duplicar dados.
- **Implementado.** Cada camada executa suas verificações de qualidade antes do `COMMIT`; se alguma falhar, a transação é desfeita e a versão anterior da camada é preservada (seção 11).
- **Implementado.** As camadas são executadas por comandos separados, nesta ordem: `pipeline.ingestao`, `pipeline.transformacao`, `pipeline.marts`.
- **Limitação.** Não há orquestrador único: reconstruir a REFINED não reconstrói a MARTS automaticamente.
- **Implementado.** A única dependência de execução é `duckdb`; `pytest`, `pytest-cov` e `ruff` estão no grupo de desenvolvimento (`pyproject.toml`).

## 2. RAW — preservação dos dados originais

Fonte: `pipeline/ingestao.py`, `pipeline/config.py`.

| Arquivo de origem | Tabela | Linhas | Colunas |
|---|---|---:|---:|
| `campeonato-brasileiro-full.csv` | `raw.partidas` | 9.165 | 17 |
| `campeonato-brasileiro-estatisticas-full.csv` | `raw.estatisticas` | 18.330 | 13 |
| `campeonato-brasileiro-gols.csv` | `raw.gols` | 10.820 | 6 |
| `campeonato-brasileiro-cartoes.csv` | `raw.cartoes` | 20.953 | 8 |

- **Implementado.** Os CSVs são apenas lidos; nenhum arquivo de origem é alterado.
- **Implementado.** Antes de abrir o banco, a ingestão confere se os quatro arquivos existem e informa **todos** os ausentes; depois, confere se cada cabeçalho é idêntico ao contrato de `config.FONTES`.
- **Implementado.** Todas as colunas entram como `VARCHAR`, com os nomes originais — inclusive o erro de digitação `rodata` (rodada) e as maiúsculas de `mandante_Placar` e `mandante_Estado`.
- **Implementado (decisão).** Campos vazios permanecem como texto vazio (`''`), e não como `NULL`. Por padrão o DuckDB converteria vazios em `NULL`; a leitura usa `allow_quoted_nulls = false` e um marcador de nulo que não ocorre nos dados. Resultado: a RAW é idêntica ao CSV campo a campo e não contém nenhum `NULL`.
- **Implementado.** Após a carga, o número de linhas de cada tabela é comparado com o número de registros do arquivo, contado pelo leitor de CSV do Python (que respeita campos com quebra de linha).
- **Implementado.** A carga das quatro tabelas ocorre numa única transação.
- **Decisão.** Os CSVs e a `Legenda.txt` não são versionados no Git (`.gitignore`: `data/raw/*`, exceto `.gitkeep`).

## 3. REFINED — conversões e limpeza

Fonte: `sql/refined/00_funcoes.sql`. As funções abaixo são utilizadas na limpeza e conversão das colunas de texto e numéricas, conforme o tipo de dado e a necessidade de cada campo.

| Função | Entrada → saída | Observação |
|---|---|---|
| `refined.texto(s)` | troca NBSP (U+00A0) por espaço, remove espaços nas pontas, `''` e `'None'` → `NULL` | `trim` comum não remove NBSP |
| `refined.inteiro(s)` | texto → `INTEGER` | conversão estrita: valor não numérico interrompe a execução |
| `refined.percentual(s)` | `'54%'` → `54.00` (`DECIMAL(5,2)`) | |
| `refined.minuto_base(s)` | `'90+3'` → `90`; `'35'` → `35` | |
| `refined.minuto_acrescimo(s)` | `'90+3'` → `3`; `'35'` → `0` | |

Outras conversões (**Implementado**, `sql/refined/02_partidas.sql`):

- `data` (`dd/mm/aaaa`) → `DATE`; `hora` (`HH:MM`) → `TIME`; `arrecadacao` → `DECIMAL(14,2)`.
- Colunas renomeadas: `rodata` → `rodada`, `mandante_Placar` → `gols_mandante`, `visitante_Placar` → `gols_visitante`, `mandante_Estado` → `uf_mandante`, `visitante_Estado` → `uf_visitante`, `tipo_de_gol` → `tipo_gol`.
- `dia_semana` derivado da data, em português (a legenda da origem cita uma coluna "Dia" que não existe no CSV).

Impacto medido:

- 5.077 nomes de arena começavam com NBSP; após a limpeza continuam 191 arenas distintas (nenhuma fusão indevida).
- `'None'` ocorre apenas em `posse_de_bola` (1.550) e `precisao_passes` (3.854). São colunas percentuais, nas quais `'None'` não pode ser um valor legítimo.

## 4. Valores ausentes

| Camada | Regra | Tipo |
|---|---|---|
| RAW | Ausência é texto vazio (`''`); nenhum `NULL` | Implementado |
| REFINED | `''` e `'None'` viram `NULL`; nenhum valor é inventado ou preenchido | Implementado |
| REFINED | Estatística não coletada: valores originais mantidos e marcação `estatisticas_disponiveis = false` (seção 7) | Implementado |
| MARTS | Fora da cobertura de uma fonte, métricas ficam `NULL`; dentro dela, ausência de evento conta `0` | Implementado |
| MARTS | Em `partida_clube`, as métricas de estatística ficam `NULL` quando a linha não foi coletada | Implementado |
| MARTS | Médias são calculadas apenas sobre valores não nulos; cada média de `estatisticas_por_resultado` traz `n_<métrica>` com a quantidade de valores usados | Implementado |

- **Limitação.** A diferença entre `''` e `'None'` da origem não é preservada na REFINED (ambos viram `NULL`); ela continua disponível na RAW.

## 5. Temporada, resultado e vencedor

Fonte: `sql/refined/02_partidas.sql`.

- **Implementado.** `temporada` = ano da data, exceto jogos de janeiro e fevereiro, que pertencem à temporada anterior.
  - Em 2003–2025 isso afeta apenas 112 jogos (06/01/2021 a 25/02/2021), que completam a temporada 2020, encerrada em fevereiro de 2021 por causa da pandemia. Com a regra, as temporadas 2020 e 2021 têm 380 jogos cada.
  - **Premissa.** Nenhuma temporada começa em janeiro ou fevereiro. A verificação "jogos em janeiro/fevereiro só nos anos esperados" falha se isso deixar de ser verdade.
- **Implementado.** `resultado` (`mandante`, `visitante` ou `empate`) é derivado do placar.
- **Implementado.** `vencedor = '-'` na origem (empate, conforme a legenda) vira `NULL`; nos demais casos o nome do clube é mantido. A coerência entre `vencedor` e o placar é verificada (2.421 empates).

## 6. Identificação e padronização dos clubes

Fonte: `sql/refined/01_clubes.sql`.

- **Implementado.** Dimensão `refined.clubes` com 46 clubes, derivada dos mandantes e visitantes das partidas. Colunas: `clube_id`, `clube`, `uf`, `total_partidas`.
- **Implementado.** `clube_id` é atribuído por `row_number()` sobre a **ordenação binária** do nome. Exemplo: `CSA` (12) vem antes de `Ceara` (13), porque letras maiúsculas precedem minúsculas.
- **Implementado.** A UF do clube vem de `mandante_Estado`/`visitante_Estado`; a unicidade da UF por clube é conferida na qualidade, a partir da RAW.
- **Implementado.** Partidas, estatísticas, gols e cartões recebem `clube_id` por `JOIN` com a dimensão.
- **Limitação.** O `clube_id` depende do conjunto de nomes: a inclusão ou a renomeação de um clube em outra versão do dataset pode mudar os identificadores de outros clubes.

## 7. Estatísticas, gols e cartões

### Estatísticas (`sql/refined/03_estatisticas.sql`)

- **Implementado.** `estatisticas_disponiveis = false` quando chutes, chutes no alvo, passes, faltas, escanteios e impedimentos são todos zero **e** a posse de bola está ausente. Os valores originais são mantidos.
  - 10.750 linhas indisponíveis e 7.580 disponíveis.
  - **Premissa.** Uma linha com todos esses contadores zerados e sem posse representa ausência de coleta, e não um jogo real com zeros.
- **Implementado (decisão).** Entre as linhas disponíveis, `passes = 0` com `precisao_passes` ausente vira `NULL` apenas na REFINED (7 linhas, todas de 2025, com posse entre 31% e 66% e chutes registrados). A RAW mantém `'0'`. A marcação de disponibilidade é calculada antes desse ajuste.

### Gols (`sql/refined/04_gols.sql`)

- **Implementado.** `gol_id` atribuído por `row_number()` na ordem partida, minuto, acréscimo, clube e atleta.
- **Implementado.** `tipo_gol` permanece `NULL` para gol comum; as marcações `penalti` e `gol_contra` tornam a classificação explícita sem inventar a categoria "normal".
- **Premissa (verificada).** `clube` é o clube que recebeu o gol no placar; em gol contra, o atleta é do adversário. Em todas as partidas com gols detalhados, a soma por clube é igual ao placar.

### Cartões (`sql/refined/05_cartoes.sql`)

- **Implementado (decisão).** `posicao_origem` preserva a posição como veio da origem (só com a limpeza de texto); `posicao` é a versão padronizada. Os 22 registros com `Zagueira` — todos do atleta Douglas Grolli — passam a `Zagueiro` em `posicao`.
- **Implementado.** `cartao_id` atribuído por `row_number()` na ordem partida, minuto, acréscimo, clube, atleta e cartão.

### Cobertura das fontes

| Fonte | Temporadas com dados | Tipo |
|---|---|---|
| Partidas e placar | 2003–2025 | Limitação da origem |
| Gols detalhados | 2014–2025 | Limitação da origem |
| Cartões detalhados | 2014–2024 (nenhum em 2025) | Limitação da origem |
| Estatísticas disponíveis | nenhuma em 2003–2013 e em 2024; 16 jogos em 2014; casos isolados indisponíveis nas demais | Limitação da origem |
| Precisão de passes | ausente em todas as linhas disponíveis de 2014 a 2017 | Limitação da origem |
| Arrecadação | apenas 2025 (380 jogos) | Limitação da origem |

- **Implementado.** Na MARTS, a cobertura de gols e de cartões é definida **por temporada a partir dos próprios dados**: uma temporada é coberta quando a fonte tem ao menos um registro nela.

## 8. Arredondamento

Fonte: `sql/marts/00_funcoes.sql`.

- **Implementado (decisão).** Regra de arredondamento adotada pelo projeto: **ROUND_HALF_UP** (meio para cima), calculada com aritmética inteira exata pelas funções `marts.arredondar_2` e `marts.arredondar_1`:

  ```
  q = (2 · numerador · 10^c + denominador) // (2 · denominador)
  resultado = q · 10^(−c)        → DECIMAL(10,2) ou DECIMAL(10,1)
  ```

- **Motivo.** No DuckDB 2.x, `avg()` e a divisão de `DECIMAL` devolvem `DOUBLE`, e `round()` sobre `DOUBLE` decide os casos exatamente no meio de forma inconsistente, porque depende da representação binária: 10,635 → 10,64, mas 0,145 → 0,14 e 1,005 → 1,00. Com a regra atual, `media_chutes_no_alvo` de 2015/derrota/visitante (29 ÷ 200 = 0,145) é armazenada como 0,15.
- **Implementado.** Premissas validadas dentro das funções: numerador e denominador devem ser não negativos e inteiros. Se violadas, a execução falha com mensagem explícita. Numerador ou denominador `NULL`, ou denominador zero, devolvem `NULL`.
- **Implementado.** Métricas com casas decimais (posse e precisão de passes) são somadas em centésimos, com o denominador multiplicado por 100.
- **Implementado.** Aplicada às 17 colunas arredondadas das MARTS: 12 em `DECIMAL(10,2)` e 5 em `DECIMAL(10,1)` (`media_passes`, `aproveitamento_pct` e os três percentuais de resultado de `resumo_temporadas`).

## 9. Classificação calculada

Fonte: `sql/marts/02_classificacao.sql`.

> A tabela `marts.classificacao` é uma **classificação calculada** a partir dos resultados
> de campo. **Não é a classificação oficial** do campeonato.

- **Implementado.** Vitória = 3 pontos; empate = 1; derrota = 0.
- **Implementado (decisão).** Ordenação por pontos, vitórias, saldo de gols e gols pró, nessa ordem. Nenhum outro critério de desempate é aplicado.
- **Implementado (decisão).** Clubes empatados nos quatro critérios recebem a mesma `posicao_calculada` (`rank()`). Não há empates completos nos dados atuais; a regra é exercitada pelos testes com dados fictícios.
- **Implementado.** `resumo_temporadas.primeiro_colocado_calculado` lista a posição 1 da classificação calculada; em caso de empate completo, os clubes aparecem separados por ` / `.
- **Limitação.** Punições aplicadas fora de campo (perda de pontos) não constam na origem e não são consideradas.
- **Limitação.** A classificação oficial usa critérios de desempate que não foram implementados. Por isso, posições — inclusive o primeiro colocado — podem divergir da tabela oficial, e o projeto não contém uma fonte para essa comparação.

## 10. Tabelas MARTS

| Tabela | Grão | Linhas | Objetivo | Origem (JOINs) |
|---|---|---:|---|---|
| `partida_clube` | partida × clube | 18.330 | Tabela base: partida, clube, adversário, resultado, pontos, estatísticas, gols e cartões detalhados | `refined.partidas` (desdobrada em mandante/visitante) ⋈ `clubes` (2×) ⟕ `estatisticas` ⟕ agregados de `gols` e `cartoes` |
| `classificacao` | temporada × clube | 470 | Classificação calculada (seção 9) | `partida_clube` ⋈ `clubes` |
| `artilharia` | temporada × atleta × clube | 3.656 | Artilheiros, sem gols contra, com ranking por gols (`rank()`) | `gols` ⋈ `partidas` ⋈ `clubes` |
| `disciplina_clubes` | temporada × clube | 470 | Cartões amarelos e vermelhos, totais e por jogo | `partida_clube` ⋈ `clubes` ⟕ agregado de `cartoes` ⋈ `partidas` |
| `estatisticas_por_resultado` | temporada × resultado × mando | 66 | Médias de estatísticas, com `n_<métrica>` por média | `partida_clube` (só linhas disponíveis) |
| `gols_por_faixa_minuto` | faixa | 8 | Distribuição dos gols detalhados por faixa de minuto | `gols` ⋈ `partidas` |
| `resumo_temporadas` | temporada | 23 | Visão geral: jogos, gols, médias, mando, primeiro colocado calculado e cobertura das fontes | `partidas` ⟕ agregados ⋈ `classificacao` ⋈ `partida_clube` |

Regras específicas (**Implementado**):

- `partida_clube`: duas linhas por partida; `pontos` e `resultado` (`vitoria`, `empate`, `derrota`) do ponto de vista de cada clube.
- `artilharia`: um atleta que atuou por mais de um clube na temporada aparece uma vez por clube.
- `disciplina_clubes`: média por jogo usa como denominador todos os jogos do clube na temporada; fonte = arquivo detalhado de cartões (decisão).
- `estatisticas_por_resultado`: temporadas sem nenhuma coleta não geram linhas.
- `gols_por_faixa_minuto` (decisão): oito faixas sem sobreposição — `0-15`, `16-30`, `31-45`, `45+`, `46-60`, `61-75`, `76-90`, `90+`. Gol com acréscimo e minuto ≤ 45 vai para `45+`; com acréscimo e minuto > 45, para `90+`; os minutos 45 e 90 sem acréscimo ficam em `31-45` e `76-90`. Faixas sem gols permanecem na tabela com zero.
  - **Premissa (verificada).** Acréscimos ocorrem apenas nos minutos 45 e 90, e não há minuto acima de 90 sem acréscimo.

## 11. Verificações de qualidade

Fonte: `pipeline/qualidade.py`, `pipeline/config.py`.

| Camada | Invariantes (I) | Expectativas (E) | Total |
|---|---:|---:|---:|
| RAW | 3 | 4 | 7 |
| REFINED | 24 | 6 | 30 |
| MARTS | 45 | 2 | 47 |
| **Total** | **72** | **12** | **84** |

- **I — invariante:** regra estrutural que deve valer para qualquer versão dos dados (chaves únicas, ausência de órfãos, conservação de totais entre camadas, coerência de regras, `NULL` fora da cobertura, arredondamento exato).
- **E — expectativa:** número específico desta versão do dataset, configurado em `config.EXPECTATIVAS`:

| Expectativa | Valor |
|---|---|
| Linhas da RAW | partidas 9.165 · estatísticas 18.330 · gols 10.820 · cartões 20.953 |
| Clubes | 46 |
| Temporadas | 2003 a 2025, sem lacunas |
| Partidas por temporada | 2020: 380 · 2021: 380 |
| Anos com jogos em janeiro/fevereiro | 2021 |
| Linhas de estatísticas disponíveis | 7.580 |
| Passes convertidos em `NULL` | 7 |
| Cobertura de gols detalhados | 2014–2025 |
| Cobertura de cartões detalhados | 2014–2024 |

Comportamento (**Implementado**):

- Cada verificação é uma consulta que conta violações; o esperado é zero.
- As verificações rodam **dentro da transação de cada camada, antes do `COMMIT`**. Qualquer falha levanta `FalhaDeQualidadeError`, a transação é desfeita (`ROLLBACK`) — preservando a versão anterior da camada — e o comando termina com código de saída 1, listando as verificações que falharam e o número de violações.
- Expectativas são bloqueantes (decisão): se a origem mudar, o pipeline falha até que `config.EXPECTATIVAS` seja revisto.
- A validação do arredondamento das 17 colunas compara cada valor armazenado, por igualdade e sem tolerância, com o ROUND_HALF_UP exato calculado em Python (`fractions.Fraction` e `decimal`), de forma independente do DuckDB. Também confere o tipo `DECIMAL` armazenado.
- Erro de SQL numa verificação é registrado como falha, sem interromper as demais.
- Execução avulsa: `uv run python -m pipeline.qualidade [--camada raw|refined|marts|todas]` abre o banco **somente para leitura** e termina com código 0 (aprovado) ou 1 (falha).
- **Decisão.** A comparação integral RAW × CSV não faz parte da rotina; a ingestão já confere cabeçalhos e contagens.

Relação com os testes automatizados (`test/`): os testes não repetem as 84 verificações. Eles conferem, com dados fictícios e bancos temporários, os valores esperados das regras (funções de limpeza, temporada, passes, posição, arredondamento, classificação com empate completo, faixas de minuto, cobertura) e o mecanismo de qualidade (detecção, mensagem, `ROLLBACK` e código de saída). Os testes marcados como `integracao` executam o pipeline sobre os CSVs reais num banco temporário e são ignorados quando os CSVs não estão presentes.

## 12. Premissas adotadas

| # | Premissa | Onde é usada | Como é protegida |
|---|---|---|---|
| P1 | Jogos de janeiro/fevereiro pertencem à temporada anterior; nenhuma temporada começa nesses meses | `02_partidas.sql` | Expectativa "anos com jogos em jan/fev" |
| P2 | Linha de estatísticas com todos os contadores zerados e sem posse = não coletada | `03_estatisticas.sql` | Invariante "estatística indisponível não tem nenhum valor coletado" e expectativa de 7.580 linhas disponíveis |
| P3 | `passes = 0` com precisão ausente, numa linha disponível, = passes não registrados | `03_estatisticas.sql` | Invariante da regra dos passes e expectativa de 7 conversões |
| P4 | Em gols, `clube` é o clube favorecido no placar (inclusive em gol contra) | `04_gols.sql`, MARTS | Invariante "gols detalhados somam o placar de cada clube" |
| P5 | `Zagueira` é variação de grafia de `Zagueiro` | `05_cartoes.sql` | Invariante "posição padronizada difere da origem só em Zagueira → Zagueiro"; valor original preservado em `posicao_origem` |
| P6 | Uma temporada é coberta por gols/cartões detalhados se tiver ao menos um registro | `01_partida_clube.sql` | Expectativas de cobertura 2014–2025 e 2014–2024 |
| P7 | Acréscimos só nos minutos 45 e 90 | `06_gols_por_faixa_minuto.sql` | Invariante correspondente |
| P8 | Métricas arredondadas são não negativas e inteiras na unidade mínima | `00_funcoes.sql` (MARTS) | Validação dentro das funções (erro explícito) |
| P9 | Cada clube tem uma única UF na origem | `01_clubes.sql` | Invariante "cada clube tem uma única UF na origem" |

## 13. Limitações conhecidas

1. **Classificação não oficial.** Não considera punições nem os critérios oficiais de desempate (seção 9).
2. **Cobertura desigual das fontes** (seção 7): sem estatísticas em 2003–2013 e em 2024; gols detalhados só a partir de 2014; cartões detalhados só até 2024; arrecadação só em 2025.
3. **Chutes no alvo em 2014–2016.** Entre as linhas com estatísticas disponíveis, `chutes_no_alvo` é zero em quase todas (2014: 32 de 32; 2015: 720 de 760; 2016: 728 de 758; a partir de 2017, entre 12 e 20 por temporada). Por decisão, os zeros são mantidos em todas as camadas; as médias de chutes no alvo dessas temporadas devem ser lidas com essa ressalva. A causa não é conhecida.
4. **Precisão de passes** ausente em 2014–2017; nesses anos `n_precisao_passes = 0` e a média é `NULL`.
5. **Zero cartões dentro da cobertura.** 63 partidas das temporadas 2014–2024 não têm nenhum cartão registrado; elas contam como zero, sem distinguir "nenhum cartão" de "cartão não registrado".
6. **Duas fontes de cartões.** As colunas de cartões das estatísticas e o arquivo detalhado de cartões coincidem em 94,7% dos amarelos (6.458 de 6.820 pares partida/clube com estatísticas disponíveis em 2014–2024) e em 100% dos vermelhos; quando divergem, o arquivo detalhado tem mais amarelos. As MARTS usam o arquivo detalhado; as duas fontes são mantidas na REFINED.
7. **Homônimos.** Não há identificador individual de atleta: homônimos no mesmo clube e temporada são agrupados na artilharia.
8. **Estabilidade do `clube_id`** depende do conjunto de nomes de clubes (seção 6).
9. **Temporadas com número diferente de jogos.** 2003 e 2004 têm 552 jogos, 2005 tem 462 e 2016 tem 379; as demais têm 380.
10. **Horário `00:00`.** Uma partida (ID 2206, Náutico × Botafogo-RJ, 09/09/2007) tem hora `00:00`. O valor é mantido como está na origem; o dataset não permite confirmar se é um horário real ou ausência de informação.
11. **Diferença entre `''` e `'None'`** da origem não é preservada após a RAW (seção 4).
12. **Execução por etapas.** Não há orquestrador único; as camadas devem ser executadas na ordem RAW → REFINED → MARTS.
