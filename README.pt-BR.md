# Agente NL→SQL sobre dados de e-commerce (Olist)

*[English](README.md)*

Faça perguntas em linguagem natural a um dataset público de e-commerce. Você recebe a resposta, junto com o SQL por trás dela e o raciocínio do modelo. A chamada ao LLM é a parte fácil; o trabalho está na camada de segurança e no loop de auto-reparo em volta dela.

## O que faz

Você digita "quais categorias de produto vendem mais?". O agente lê o schema do banco ao vivo, escreve uma query DuckDB, confere que é um SELECT read-only, executa e mostra a tabela junto com o SQL usado. Se a query dá erro, o erro do banco volta para o modelo corrigir o próprio SQL.

## Por que é construído assim

- **Prompt ciente do schema.** As tabelas e colunas reais são introspectadas do banco e entram no prompt, então o modelo escreve SQL contra nomes que ele realmente consegue ver.
- **Camada de segurança de SQL.** Trato a saída do LLM como não-confiável, então há duas linhas de defesa. Um validador rejeita qualquer coisa que não seja um único SELECT/CTE read-only, e força um teto de linhas. Abaixo dele, a conexão DuckDB é aberta com `read_only=True`, então uma instrução que passe pelo validador ainda assim não consegue escrever por essa conexão. As duas regras são funções puras, e é por isso que os testes de segurança rodam sem banco e sem API key.
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

## Modo analista

Text-to-SQL te devolve linhas. Mas quando a pergunta real é *"qual o ticket médio dos pedidos?"*, o que você quer de volta é um número só, e um modelo de linguagem consegue recitar um número sem nunca tê-lo calculado.

O modo analista fecha essa lacuna com tool-calling sobre um sandbox. O agente tem duas tools. `run_sql` roda um SELECT read-only pela mesma camada de segurança; `run_python` roda um trecho curto num sandbox de AST restrito. Ele precisa *computar* o valor chamando-as. Todo número da resposta final tem que aparecer num resultado de tool executada, e se não aparecer, a resposta volta marcada `grounded=False`. O SQL executado e o código executado viajam junto com a resposta, e as linhas-fonte também.

O sandbox funciona por allow-list. O trecho é parseado para AST, e a whitelist rejeita `import`, acesso a atributo (o que fecha o caminho usual do `__class__`/`__globals__`), `lambda`, laços `for`/`while` e chamadas a qualquer coisa fora de um conjunto fixo de builtins seguros, tudo antes de uma linha rodar. A execução acontece sob `{"__builtins__": {}}`, com um timeout de parede como rede de segurança. É uma função pura, com testes próprios em `tests/test_sandbox.py`. É uma allow-list, não uma fronteira de segurança: eu não rodaria código de usuário não-confiável atrás dela.

### Demo offline (sem API key, sem download)

Um dataset sintético minúsculo vem em `sample_data/`, então dá para ver tudo rodar com um driver determinístico:

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
# baixe os CSVs do Olist para data/ (veja data/README.md)
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

Brazilian E-Commerce Public Dataset da Olist (público, ~100k pedidos). Não versionado no repo; veja [data/README.md](data/README.md).
