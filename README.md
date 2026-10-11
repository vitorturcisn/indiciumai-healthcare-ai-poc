# Indicium HealthCare SRAG PoC - pacote de remediação v2

Este pacote contém uma refatoração modular e testável da PoC de monitoramento epidemiológico de SRAG, preparada para endereçar os feedbacks da validação. **Ele ainda não foi enviado ao repositório GitHub original**: a conexão disponível nesta sessão permitiu leitura, mas recusou a criação de branch. A ideia é revisar e incorporar os arquivos em uma branch local antes de abrir um Pull Request; não sobrescreva `main` sem revisar o diff.

## O que muda em relação à implementação monolítica

- **Modularização:** ingestão/limpeza, datas, métricas, gráficos, notícias, guardrails, auditoria, agente e CLI ficam em módulos separados em `src/srag_poc/`.
- **Limpeza aplicada:** códigos fora do domínio são convertidos em nulos e contabilizados; código `9` continua explicitamente desconhecido; `EVOLUCAO=3` é reconhecido e tratado como óbito por outras causas.
- **Datas explícitas:** `dd/mm/aaaa` é interpretado como formato brasileiro; ISO é aceito como alternativa. `DT_SIN_PRI` é a data epidemiológica de referência quando válida, com fallback documentado para `DT_NOTIFIC`.
- **Atraso de notificação:** estima-se o percentil 90 do atraso `DT_NOTIFIC - DT_SIN_PRI`, usando notificações dos últimos 180 dias e pelo menos 30 observações válidas. A variação de casos usa um corte que exclui esse intervalo estimado; se não houver amostra suficiente, a variação fica `N/A`, em vez de usar um atraso inventado.
- **Métricas com semântica explícita:** a métrica de mortalidade aqui é de **óbitos por qualquer causa entre desfechos conhecidos** (`EVOLUCAO` 2 ou 3 sobre 1, 2 ou 3). O relatório também separa `EVOLUCAO=2` de `EVOLUCAO=3`. `VACINA_COV` é vacinação contra COVID-19 registrada nos casos SRAG, não cobertura populacional. Internação em UTI entre casos não equivale a ocupação de leitos.
- **Tool calling real:** o LLM escolhe e solicita ferramentas por meio de `bind_tools`; LangGraph encaminha cada chamada, registra começo/fim/erro e impõe um limite total de chamadas. Ao chegar ao limite, o modelo entra em modo de finalização sem ferramentas.
- **Validação de proveniência:** o guardrail de saída exige as ferramentas, seções e gráficos obrigatórios; confere que percentuais, números e URLs tenham correspondência nos resultados das ferramentas. O validador continua sendo uma barreira adicional, não uma prova formal de veracidade semântica.
- **Notícias nacionais:** a busca executa consultas separadas por fontes institucionais nacionais e prioriza conteúdo com termos nacionais, rejeitando URLs fora da allowlist. Se não houver resultados, não infere ausência de surto ou de risco.
- **Auditoria por evento:** `audit_log.jsonl` registra eventos antes e depois de chamadas a tools/LLM, snapshots das mensagens passadas ao modelo, texto de resposta, hashes, IDs das chamadas, status do validador e tokens quando a API os retorna. O LLM recebe apenas agregados; nunca recebe as linhas individuais da base.
- **Testes:** testes unitários de parsing de data, domínio de códigos, minimização, tratamento de mortalidade, allowlist e proveniência.

## Estrutura

```text
.
├── README.md
├── requirements.txt
├── pyproject.toml
├── diagrama_arquitetura_v2.pdf
├── diagrama_arquitetura_v2.py
├── src/
│   └── srag_poc/
│       ├── config.py
│       ├── dates.py
│       ├── ingestion.py
│       ├── metrics.py
│       ├── charts.py
│       ├── news.py
│       ├── guardrails.py
│       ├── audit.py
│       ├── agent.py
│       └── main.py
└── tests/
    ├── test_dates_and_ingestion.py
    ├── test_metrics.py
    └── test_guardrails.py
```

## Execução local

Requer Python 3.10 ou superior e uma chave de API do Google AI Studio.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[test]"
$env:GOOGLE_API_KEY = Read-Host "Digite sua GOOGLE_API_KEY"
```

Linux/macOS:

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[test]"
read -s GOOGLE_API_KEY
export GOOGLE_API_KEY
```

A execução aceita um ou mais CSVs DATASUS, separando os anos com chamadas repetidas à flag `--csv`:

```bash
python -m srag_poc.main --csv data/INFLUD25-14-09-2026.csv --csv data/INFLUD26-14-09-2026.csv
```

O modelo padrão é `gemini-3.8-flash`, que suporta function calling segundo a [documentação oficial do Gemini](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash). Para trocar o modelo, use `--model` ou a variável `GEMINI_MODEL`. Confirme que o modelo habilitado para a sua chave suporta tool calling antes da execução.

```powershell
$env:GEMINI_MODEL = "gemini-3.8-flash"
python -m srag_poc.main --csv data/INFLUD25-14-09-2026.csv --csv data/INFLUD26-14-09-2026.csv --request "Gere o relatório nacional agregado de SRAG com métricas e gráficos."
```

Artefatos esperados em `outputs/`:

- `srag_dados.db`: apenas colunas analíticas minimizadas;
- `qualidade_dados.json`: contagens dos códigos inválidos/desconhecidos e da cobertura das datas;
- `grafico_30_dias.png` e `grafico_12_meses.png`;
- `relatorio_final.md`;
- `audit_log.jsonl`.

A primeira execução pode consumir chamadas pagas à API. Para testar apenas a limpeza/estatística sem API do LLM, execute os testes unitários.

## Testes

```bash
pytest -q
```

Os testes incluídos são determinísticos e não precisam de conexão com Gemini ou com a busca de notícias. A execução completa do agente depende de chave válida, rede e disponibilidade do modelo/provedor externo.

## Definições e tratamento dos campos

| Campo | Valores tratados | Regra aplicada |
|---|---|---|
| `DT_NOTIFIC` | data de notificação | Obrigatória para manter a linha; valores impossíveis são excluídos e contabilizados. |
| `DT_SIN_PRI` | data dos primeiros sintomas | Interpretada com dia primeiro; datas posteriores à notificação são descartadas como inconsistentes. |
| `UTI` | `1=sim`, `2=não`, `9=ignorado` | Valores fora do domínio viram nulos; indicador usa apenas 1/2 no denominador. |
| `EVOLUCAO` | `1=cura`, `2=óbito`, `3=óbito por outras causas`, `9=ignorado` | Valores fora do domínio viram nulos; mortalidade por qualquer causa conta 2+3 no numerador e 1+2+3 no denominador. |
| `VACINA_COV` | `1=sim`, `2=não`, `9=ignorado` | Valores fora do domínio viram nulos; proxy refere-se à vacina contra COVID-19 registrada entre casos. |

O dicionário SIVEP-Gripe define `EVOLUCAO=3` como “óbito por outras causas”; isso não deve ser ocultado ao calcular mortalidade. Fontes de referência: [dicionário de dados de SRAG/SIVEP-Gripe](https://opendatasus.saude.gov.br/dataset/srag-2021-a-2024/resource/3135ac9c-2019-4989-a893-2ed50ebd8e68) e [conjunto de dados atualmente usado na PoC](https://dadosabertos.saude.gov.br/dataset/srag-2019-a-2026). O repositório original usa snapshots de 2025 e 2026; ajuste os caminhos do exemplo para os arquivos locais disponíveis. Os datasets públicos podem ser atualizados e os registros revisados, então cada relatório deve registrar os arquivos de entrada e a data de corte observada.

## Guardrails e auditoria: limitações restantes

Guardrails baseados em padrões e allowlists reduzem riscos, mas não são infalíveis. A validação numérica automatizada verifica a presença dos números nos resultados das tools, mas não prova que cada frase esteja semanticamente correta; revisão humana continua necessária. Auditoria grava texto dos prompts e respostas enviados ao LLM: mantenha somente solicitações agregadas e nunca adicione dados individuais ao contexto. A PoC não é ferramenta de diagnóstico, prognóstico individual ou decisão clínica.

## Como integrar ao repositório existente sem destruir o histórico

1. Crie branch local `fix/feedback-validacao-v2` a partir de `main`.
2. Copie `src/srag_poc/`, `tests/`, `pyproject.toml`, `.gitignore`, `requirements.txt` e o PDF para a branch.
3. Atualize o README principal em um commit separado para documentar a nova estrutura e retirar instruções antigas que assumem execução pelo script monolítico.
4. Execute `pip install -e ".[test]"`, `pytest -q` e uma execução real com CSVs e `GOOGLE_API_KEY` configurada.
5. Revise o PDF conceitual com o diagrama gerado e teste a aderência nacional das fontes de notícia no snapshot atual.
6. Faça commits atômicos, por exemplo `refactor: split pipeline into domain modules`, `fix: normalize SRAG fields and reporting lag`, `feat: add tool-calling agent and provenance guardrails`, `test: add ingestion and metric tests`.
7. Abra Pull Request para revisão. Não versionar CSVs, banco SQLite, logs ou relatórios gerados.

## Status desta entrega

O pacote inclui a implementação proposta e os testes locais aprovados no ambiente de criação. Não executa uma chamada real ao Gemini nem busca notícias durante os testes, portanto a integração ponta a ponta precisa ser executada com suas credenciais antes de reenviar para validação.
