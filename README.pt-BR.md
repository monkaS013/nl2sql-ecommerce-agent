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

## Como rodar

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
