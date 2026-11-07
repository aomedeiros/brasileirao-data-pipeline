# Brasileirão Data Pipeline

Pipeline de dados que transforma o histórico do Campeonato Brasileiro de futebol
(temporadas 2003 a 2025) em estruturas analíticas, organizadas em três camadas —
**RAW → REFINED → MARTS** — sobre um banco [DuckDB](https://duckdb.org/) local.

Partindo de quatro arquivos CSV públicos, o pipeline preserva uma cópia fiel da origem,
trata, tipa e relaciona os dados, e publica sete tabelas analíticas. Cada etapa é
validada por verificações de qualidade executadas dentro da própria transação: se
alguma falhar, a etapa é desfeita e os dados anteriores são preservados.

## Contexto acadêmico

Trabalho acadêmico de engenharia de dados desenvolvido na pós-graduação em
**Engenharia de Dados e Inteligência Artificial**. O desenvolvimento foi realizado por
etapas, cada uma validada e registrada em um commit próprio no Git.

## Fonte dos dados

Dataset público **Campeonato Brasileiro de Futebol**, disponível no Kaggle:
<https://www.kaggle.com/datasets/adaoduque/campeonato-brasileiro-de-futebol>

Para obter os dados:

1. Acesse a página do dataset no Kaggle, no endereço acima.
2. Baixe os arquivos do dataset e extraia o conteúdo.
3. Copie os quatro arquivos CSV listados na tabela abaixo para a pasta `data/raw/` do projeto.
4. Confira se os nomes dos arquivos correspondem exatamente aos da tabela; a ingestão
   procura cada arquivo pelo nome.

Os arquivos CSV **não fazem parte deste repositório**: devem ser obtidos separadamente
e colocados em `data/raw/`. O pipeline espera exatamente estes quatro arquivos:

| Arquivo | Conteúdo | Registros esperados |
|---|---|---:|
| `campeonato-brasileiro-full.csv` | Partidas: data, clubes, placar, arena, técnicos | 9.165 |
| `campeonato-brasileiro-estatisticas-full.csv` | Estatísticas por clube em cada partida | 18.330 |
| `campeonato-brasileiro-gols.csv` | Gols: autor, minuto, tipo | 10.820 |
| `campeonato-brasileiro-cartoes.csv` | Cartões: atleta, posição, minuto | 20.953 |

O dataset também traz uma `Legenda.txt` com a descrição das colunas. Ela é apenas uma
referência opcional: não é necessária para executar o pipeline, não é lida pelo código
e não é versionada.

A ingestão confere se os quatro arquivos existem e se os cabeçalhos correspondem ao
esperado; caso contrário, interrompe a execução indicando o problema. As contagens
acima correspondem à versão do dataset utilizada no projeto e são conferidas pelas
verificações de qualidade.

## Arquitetura

```
data/raw/*.csv ──► RAW ──► REFINED ──► MARTS
                   │         │           │
                   └─────────┴───────────┴──► verificações de qualidade
                                               (antes do COMMIT de cada camada)
```

| Camada | Schema | Responsabilidade |
|---|---|---|
| **RAW** | `raw` | Ingestão e preservação dos dados de origem: cópia fiel dos CSVs, todas as colunas como texto, sem conversões |
| **REFINED** | `refined` | Limpeza, padronização, conversão de tipos, dimensão de clubes e relacionamento por chaves entre partidas, estatísticas, gols e cartões |
| **MARTS** | `marts` | Tabelas analíticas preparadas para consultas e análises |

Todas as camadas ficam no arquivo `data/brasileirao.duckdb`, gerado pelo pipeline e
não versionado. As transformações das camadas REFINED e MARTS estão em scripts SQL,
executados em ordem; o Python orquestra a execução de cada etapa e as verificações.

## Estrutura do projeto

```
brasileirao-data-pipeline/
├── data/
│   └── raw/                  # CSVs de origem (não versionados; obtidos no Kaggle)
├── pipeline/
│   ├── config.py             # caminhos, contrato dos CSVs e expectativas do dataset
│   ├── db.py                 # conexão DuckDB e execução transacional dos scripts SQL
│   ├── ingestao.py           # camada RAW
│   ├── transformacao.py      # camada REFINED
│   ├── marts.py              # camada MARTS
│   └── qualidade.py          # verificações de qualidade
├── sql/
│   ├── refined/              # 00_funcoes.sql … 05_cartoes.sql
│   └── marts/                # 00_funcoes.sql … 07_resumo_temporadas.sql
├── specs/
│   └── decisoes_de_tratamento.md
├── test/                     # testes automatizados (pytest)
├── pyproject.toml
├── uv.lock
└── README.md
```

## Tabelas analíticas

| Tabela | Granularidade | Descrição |
|---|---|---|
| `partida_clube` | Partida × clube | Base analítica: resultado, pontos, estatísticas, gols e cartões de cada clube em cada partida |
| `classificacao` | Temporada × clube | Classificação **calculada** a partir dos resultados (não oficial) |
| `artilharia` | Temporada × atleta × clube | Artilheiros por temporada, sem gols contra |
| `disciplina_clubes` | Temporada × clube | Cartões amarelos e vermelhos, totais e por jogo |
| `estatisticas_por_resultado` | Temporada × resultado × mando | Médias de chutes, posse, passes e outras estatísticas |
| `gols_por_faixa_minuto` | Faixa de minuto | Distribuição dos gols em oito faixas, incluindo acréscimos |
| `resumo_temporadas` | Temporada | Visão geral: jogos, gols, médias, primeiro colocado calculado e cobertura das fontes |

A camada REFINED contém as tabelas `clubes`, `partidas`, `estatisticas`, `gols` e
`cartoes`, relacionadas pelas chaves `partida_id` e `clube_id`.

## Decisões de tratamento

As principais decisões adotadas no projeto:

- **RAW fiel à origem:** os CSVs são lidos sem alteração; campos vazios permanecem como
  texto vazio.
- **Ausência não vira zero:** na REFINED, valores vazios passam a `NULL`; estatísticas
  não coletadas são sinalizadas, e não tratadas como zero; nas MARTS, métricas ficam
  `NULL` fora da cobertura de cada fonte.
- **Temporada:** jogos de janeiro e fevereiro pertencem à temporada anterior (caso da
  temporada 2020, encerrada em 2021).
- **Classificação calculada:** pontos, vitórias, saldo de gols e gols pró; clubes
  empatados em todos os critérios mantêm a mesma posição. Não considera punições nem
  critérios oficiais de desempate.
- **Arredondamento:** ROUND_HALF_UP (meio para cima), calculado com aritmética inteira
  exata e armazenado como `DECIMAL`.

O documento [`specs/decisoes_de_tratamento.md`](specs/decisoes_de_tratamento.md) contém o
detalhamento das premissas, regras de transformação, limitações conhecidas e decisões
metodológicas, com a indicação do arquivo em que cada regra está implementada.

## Qualidade dos dados

O pipeline executa **84 verificações de qualidade** — **72 invariantes** (regras
estruturais, como chaves únicas, ausência de registros órfãos e conservação de totais
entre camadas) e **12 expectativas** (valores específicos desta versão do dataset,
configurados em `pipeline/config.py`).

As verificações rodam dentro da transação de cada camada, antes do `COMMIT`. Se alguma
falhar, a transação é desfeita (rollback), a versão anterior da camada é preservada e o
comando termina com código de saída 1, informando quais verificações falharam.

Também é possível executá-las de forma avulsa, com o banco aberto somente para leitura:

```powershell
uv run python -m pipeline.qualidade --camada todas
```

A opção `--camada` aceita `raw`, `refined`, `marts` ou `todas`.

## Instalação e execução

### Pré-requisitos

- [uv](https://docs.astral.sh/uv/), para gerenciar o Python e as dependências.
- Python 3.14 ou superior (`requires-python = ">=3.14"`); o uv pode instalá-lo
  automaticamente.
- Os quatro arquivos CSV do dataset, colocados em `data/raw/` (veja
  [Fonte dos dados](#fonte-dos-dados)).

A única dependência de execução é o `duckdb`; `pytest`, `pytest-cov` e `ruff` fazem parte
do grupo de desenvolvimento. As versões estão travadas em `uv.lock`.

### Execução do pipeline

Na raiz do projeto:

```powershell
uv sync
uv run python -m pipeline.ingestao
uv run python -m pipeline.transformacao
uv run python -m pipeline.marts
uv run python -m pipeline.qualidade --camada todas
```

As etapas devem ser executadas **nessa ordem**: cada uma depende da camada anterior.
Não há um orquestrador automático — ao reprocessar a REFINED, por exemplo, é preciso
executar novamente a etapa MARTS. Cada etapa pode ser reexecutada sem duplicar dados.

Por padrão, os CSVs são lidos de `data/raw/` e o banco é gravado em
`data/brasileirao.duckdb`. Os comandos aceitam `--db` para usar outro arquivo de banco,
e a ingestão aceita `--raw` para indicar outra pasta de CSVs.

### Testes e verificação de estilo

```powershell
uv run pytest --cov
uv run pytest -m "not integracao"
uv run pytest -m integracao
uv run ruff check .
uv run ruff format --check .
```

| Comando | O que executa |
|---|---|
| `uv run pytest --cov` | Todos os testes, com relatório de cobertura |
| `uv run pytest -m "not integracao"` | Apenas os testes com dados fictícios |
| `uv run pytest -m integracao` | Apenas os testes de integração com os CSVs reais |
| `uv run ruff check .` | Análise estática do código |
| `uv run ruff format --check .` | Conferência da formatação |

Os testes de integração dependem dos arquivos CSV originais em `data/raw/`; sem eles,
são ignorados automaticamente.

## Testes automatizados

Resultados da execução validada em **07/11/2026** — valores observados naquela data, e
não garantias permanentes:

| Indicador | Resultado |
|---|---|
| Testes aprovados | 101 de 101 |
| Testes unitários (dados fictícios) | 97 |
| Testes de integração (CSVs reais) | 4 |
| Cobertura observada do pacote `pipeline` | 98,84% |
| Cobertura mínima configurada | 80% |

Os testes unitários utilizam um conjunto de dados fictícios que reproduz as
particularidades da origem e são executados em bancos temporários. Os testes de
integração processam os CSVs reais, também em banco temporário. Nenhum teste modifica o
banco do projeto (`data/brasileirao.duckdb`) nem os arquivos CSV.

Os testes não repetem as 84 verificações de qualidade: eles conferem os resultados
esperados das regras de transformação, do arredondamento, da classificação e das faixas
de minuto, além do comportamento de falha e rollback das verificações.

## Limitações conhecidas

Resumo das limitações registradas em
[`specs/decisoes_de_tratamento.md`](specs/decisoes_de_tratamento.md), que traz os
detalhes e os números de cada caso:

- **Classificação calculada, não oficial.** A tabela `classificacao` é calculada pelo
  projeto a partir dos resultados de campo e não representa necessariamente a
  classificação oficial: não considera punições aplicadas fora de campo nem todos os
  critérios oficiais de desempate.
- **Cobertura desigual das fontes.** A disponibilidade de estatísticas, gols e cartões
  varia entre temporadas: não há estatísticas coletadas em 2003–2013 nem em 2024; os gols
  detalhados começam em 2014; os cartões detalhados vão de 2014 a 2024; a precisão de
  passes não está disponível em 2014–2017. Fora da cobertura de cada fonte, as métricas
  ficam `NULL`.
- **Atletas homônimos.** A origem não traz identificação individual dos atletas; por
  isso, homônimos no mesmo clube e temporada podem ser consolidados na artilharia.
- **Anomalias nas estatísticas.** Entre as linhas com estatísticas disponíveis,
  `chutes_no_alvo` é zero em quase todas as linhas das temporadas de 2014 a 2016. Os
  valores foram mantidos como estão na origem, e a causa não foi identificada.
- **Partidas sem cartões registrados.** Dentro da cobertura dos cartões (2014–2024), há
  partidas sem nenhum cartão registrado. Elas contam como zero, o que não permite
  distinguir a ausência real de cartões da ausência de registro.

## Uso de inteligência artificial

O Claude Code, assistente de programação da Anthropic, foi utilizado como ferramenta de
apoio no desenvolvimento, na implementação, na revisão e na validação deste projeto.

A definição dos objetivos, as decisões metodológicas e de tratamento dos dados, o
acompanhamento de cada etapa e a validação dos resultados fizeram parte do trabalho
acadêmico do autor. Cada etapa foi revisada e aprovada antes de ser registrada no Git.
