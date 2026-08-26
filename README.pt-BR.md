# Agente NL→SQL sobre dados de e-commerce (Olist)

*[English](README.md)*

Faça perguntas em linguagem natural a um dataset público de e-commerce e receba a resposta, o SQL por trás dela e o raciocínio do modelo. A parte interessante não é a chamada ao LLM — é a camada de segurança e o loop de auto-reparo em volta dela.

## O que faz

Você digita "quais categorias de produto vendem mais?"; o agente lê o schema do banco ao vivo, escreve uma query DuckDB, confere que é um SELECT read-only, executa e mostra a tabela mais o SQL usado. Se a query dá erro, o erro do banco volta para o modelo corrigir o próprio SQL.

## Por que é construído assim

- **Prompt ciente do schema.** As tabelas e colunas reais são introspectadas do banco e colocadas no prompt, então o modelo escreve SQL contra tabelas que existem, em vez de chutar nomes.
- **Uma camada de segurança de SQL em que eu confio.** A saída do LLM nunca é confiável. Duas linhas de defesa: um validador que rejeita qualquer coisa que não seja um único SELECT/CTE read-only (e força um teto de linhas), e uma conexão DuckDB aberta com `read_only=True`, para que mesmo uma instrução que passe pelo validador não consiga escrever. As regras são funções puras — toda a segurança é testada sem banco e sem API key.
- **Loop de auto-reparo.** Uma query que falha (validação ou erro do banco) volta ao modelo com o erro, até um número definido de tentativas. O agente informa quantas tentativas levou.
- **Uma fronteira de provedor.** Toda chamada ao modelo vive em `nl2sql/llm.py`. Trocar a Anthropic por outro provedor é uma mudança nesse único arquivo; o SDK é importado de forma preguiçosa, então o resto do pacote importa sem ele.

## Arquitetura

```
pergunta
   │
   ▼
describe_schema(con) ──▶ llm.generate_sql() ──▶ safety.validate_sql()
                                                      │  ok             │ erro
                                                      ▼                 ▼
                                              con.execute()      devolve o erro (reparo)
                                                      │
                                                      ▼
                                                   Answer(sql, rows, attempts)
```

## Modo analista — computa o número, não só escreve SQL

Text-to-SQL te devolve linhas. Mas quando a pergunta real é *"qual o ticket médio dos pedidos?"*, a resposta é um **número** — e um modelo de linguagem recitando um número é um número em que você não pode confiar.

O modo analista fecha essa lacuna com **tool-calling sobre um sandbox**. O agente tem duas tools — `run_sql` (um SELECT read-only pela mesma camada de segurança) e `run_python` (um trecho curto rodado num sandbox trancado) — e precisa *computar* o valor chamando-as. Todo número que ele reporta tem que aparecer num resultado de tool executada; se não aparecer, a resposta é marcada `grounded=False` em vez de ser confiada. O SQL executado, o código executado e as linhas-fonte viajam junto com a resposta.

O sandbox é baseado em allow-list: o trecho é parseado para AST, e qualquer coisa fora de uma whitelist pequena — `import`, acesso a atributo (então não há escape via `__class__`/`__globals__`), `lambda`, laços `for`/`while`, chamadas a qualquer coisa fora de um conjunto fixo de builtins seguros — é rejeitada antes de uma linha rodar, sob `{"__builtins__": {}}` e com um timeout de parede como rede de segurança. É puro e totalmente coberto por testes (`tests/test_sandbox.py`).

### Demo offline (sem API key, sem download)

Um dataset **sintético** minúsculo vem em `sample_data/`, então dá para ver tudo rodar com um driver determinístico:

```bash
pip install -r requirements.txt
python -m nl2sql.cli build-sample     # monta um DuckDB a partir de sample_data/
python -m nl2sql.cli analyze          # a pergunta-demo embutida
```

```
Answer:   The average order value is the mean of the per-order item totals computed above.
Value:    159.0
Grounded: True   (steps: 3)

Trace (every number came from one of these executed steps):
  [1] run_sql     SELECT order_id, SUM(price) AS order_total FROM order_items GROUP BY order_id ...
  [2] run_python  result = round(sum(r['order_total'] for r in rows) / len(rows), 2)
```

Passe `--live` (com `ANTHROPIC_API_KEY` definida) para o Claude dirigir as tools e responder perguntas quaisquer.

## Como rodar (o app Streamlit NL→SQL)

```bash
pip install -r requirements.txt
cp .env.example .env        # coloque sua ANTHROPIC_API_KEY
# baixe os CSVs do Olist para data/ — veja data/README.md
streamlit run app.py        # monte o banco pela sidebar e pergunte
```

## Testes

O núcleo (regras de safety, introspecção de schema, garantia read-only, o loop de reparo com um modelo fake injetado) roda sem API key:

```bash
python -m pytest -q
```

## Stack

Python · DuckDB · Anthropic (Claude) · Streamlit · pytest.

## Dataset

Brazilian E-Commerce Public Dataset da Olist (público, ~100k pedidos). Não versionado — veja [data/README.md](data/README.md).
