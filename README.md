# Indicium HealthCare — SRAG AI PoC

Prova de conceito de **Inteligência Artificial Generativa para monitoramento epidemiológico da Síndrome Respiratória Aguda Grave (SRAG)**, utilizando dados públicos do DATASUS, métricas epidemiológicas, gráficos e notícias de fontes institucionais.

A solução combina Python, SQLite, Pandas, LangGraph e Google Gemini para automatizar a geração de relatórios epidemiológicos agregados, com mecanismos de minimização de dados, validação de resultados, controle das ferramentas e auditoria das execuções.

O projeto foi desenvolvido para avaliar a viabilidade de uma solução que ajude profissionais da saúde a interpretar indicadores epidemiológicos e contextualizá-los com informações externas recentes.

> **Escopo da PoC:** esta solução é experimental e não substitui a análise epidemiológica profissional. Não deve ser utilizada para diagnóstico, prognóstico individual ou tomada de decisão clínica.

## 1. Objetivos do projeto

- Consultar dados públicos de internações por SRAG.
- Tratar inconsistências e valores ausentes nos campos utilizados pela análise.
- Calcular indicadores epidemiológicos com denominadores e limitações explicitados.
- Gerar gráficos diários e mensais de casos.
- Consultar fontes institucionais para buscar informações relacionadas ao cenário nacional de SRAG.
- Utilizar um agente de IA generativa para orquestrar ferramentas e produzir o relatório.
- Validar a consistência numérica e a proveniência das URLs presentes na saída.
- Registrar eventos de execução para auditoria e rastreabilidade.
- Evitar o envio de registros individuais ao modelo de linguagem, trabalhando com dados agregados.

## 2. Arquitetura da solução

O sistema utiliza uma arquitetura modular, separando ingestão, tratamento dos dados, cálculo de métricas, visualização, busca de notícias, orquestração, validação e auditoria.

O diagrama conceitual da arquitetura está disponível em [`diagrama_arquitetura_v2.pdf`](diagrama_arquitetura_v2.pdf).

### Fluxo de execução

1. **Entrada:** o usuário solicita a geração de um relatório por meio da interface de linha de comando (CLI).
2. **Input Guardrail:** a solicitação é validada antes da leitura dos dados e da chamada aos serviços externos.
3. **Ingestão e qualidade:** os CSVs do DATASUS são carregados, as datas são normalizadas, os domínios são tratados e os dados são minimizados.
4. **Persistência:** os dados analíticos são armazenados em um banco SQLite local.
5. **Agente:** o LangGraph coordena o modelo Gemini e as ferramentas disponíveis por meio de tool calling.
6. **Ferramentas:** o agente pode consultar métricas, gerar gráficos e buscar notícias institucionais.
7. **Output Validator:** o relatório é verificado quanto à estrutura, à coerência numérica e à proveniência das URLs.
8. **Saída e auditoria:** o relatório, os gráficos, o resumo de qualidade e os eventos da execução são registrados localmente.

### Ferramentas do agente

| Ferramenta | Responsabilidade |
|---|---|
| `consultar_metricas` | Consultar os indicadores epidemiológicos calculados a partir do SQLite. |
| `gerar_graficos` | Produzir as séries temporais de casos diários e mensais. |
| `buscar_noticias` | Buscar conteúdos de fontes institucionais relacionados à SRAG e a vírus respiratórios. |

As consultas analíticas são executadas por funções controladas, e não por SQL livre gerado pelo modelo. O agente tem um limite configurável de chamadas às ferramentas, definido por `MAX_TOOL_CALLS`, cujo padrão é seis.

## 3. Estrutura do repositório

```text
.
├── README.md
├── .gitignore
├── pyproject.toml
├── requirements.txt
├── diagrama_arquitetura_v2.pdf
├── diagrama_arquitetura_v2.py
├── src/
│   └── srag_poc/
│       ├── __init__.py
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
    ├── test_agent_content.py
    ├── test_dates_and_ingestion.py
    ├── test_dates_iso_regression.py
    ├── test_guardrails.py
    ├── test_metrics.py
    └── test_news.py
```

### Principais módulos

- `config.py`: configurações, modelo utilizado, caminhos de saída e limites da aplicação.
- `dates.py`: interpretação explícita de datas brasileiras e ISO.
- `ingestion.py`: leitura, limpeza, minimização, avaliação da qualidade e persistência dos dados.
- `metrics.py`: cálculos reproduzíveis dos indicadores epidemiológicos.
- `charts.py`: geração dos gráficos de séries temporais.
- `news.py`: busca de conteúdos institucionais e validação de URLs.
- `guardrails.py`: validação da solicitação e do relatório gerado.
- `audit.py`: registro estruturado dos eventos da execução.
- `agent.py`: ferramentas, estado e orquestração do agente.
- `main.py`: ponto de entrada da aplicação.

## 4. Tecnologias utilizadas

| Tecnologia | Aplicação |
|---|---|
| Python | Linguagem principal e implementação da solução |
| Pandas | Leitura, transformação e análise dos dados |
| SQLite | Persistência local dos dados analíticos |
| Matplotlib | Geração dos gráficos |
| LangGraph | Orquestração do fluxo do agente |
| LangChain | Integração entre o modelo e as ferramentas |
| Google Gemini | Geração de texto e seleção de ferramentas |
| DDGS | Busca de conteúdos externos |
| Pytest | Testes automatizados |
| ReportLab | Geração programática do diagrama em PDF |

O modelo padrão configurado no projeto é `gemini-3.8-flash`. Ele pode ser alterado por meio da opção `--model` ou da variável de ambiente `GEMINI_MODEL`. Consulte a [documentação oficial dos modelos Gemini](https://ai.google.dev/gemini-api/docs/models) e verifique quais modelos habilitados para sua chave suportam function calling.

## 5. Dados e fontes

### Conjunto de dados

A solução utiliza arquivos CSV públicos de internações por SRAG do sistema SIVEP-Gripe, disponibilizados pelo DATASUS.

Fontes:

- [Conjunto de dados SRAG — Dados Abertos do Ministério da Saúde](https://dadosabertos.saude.gov.br/dataset/srag-2019-a-2026)
- [Conjunto SRAG 2021–2024 — OpenDataSUS](https://opendatasus.saude.gov.br/dataset/srag-2021-a-2024)
- [Dicionário de dados SRAG/SIVEP-Gripe](https://opendatasus.saude.gov.br/dataset/srag-2021-a-2024/resource/3135ac9c-2019-4989-a893-2ed50ebd8e68)

Os arquivos de origem não são armazenados no GitHub. Para executar a aplicação, baixe os snapshots desejados e coloque-os na pasta local `data/`.

### Fontes externas de notícias

A ferramenta de notícias prioriza fontes institucionais e utiliza uma lista de domínios permitidos:

- Ministério da Saúde e outros conteúdos em `gov.br`;
- Fundação Oswaldo Cruz e conteúdos em `fiocruz.br`;
- Organização Mundial da Saúde e conteúdos em `who.int`.

As URLs precisam ser HTTPS e pertencer aos domínios autorizados. O fallback institucional prioriza itens com relevância para o tema e data de publicação verificável.

A ausência de resultados na busca **não significa ausência de surtos ou de risco epidemiológico**.

## 6. Tratamento, minimização e qualidade dos dados

Os arquivos do DATASUS podem apresentar valores ausentes, formatos de data diferentes, códigos inválidos e registros inconsistentes. Por isso, a ingestão aplica regras explícitas antes de persistir os dados.

### Campos utilizados

| Campo | Significado | Tratamento |
|---|---|---|
| `DT_NOTIFIC` | Data da notificação | Obrigatória. Registros sem data válida são excluídos e contabilizados. |
| `DT_SIN_PRI` | Data dos primeiros sintomas | Opcional. Utilizada como referência epidemiológica quando válida. |
| `UTI` | Informação sobre internação em UTI | São considerados os códigos `1`, `2` e `9`; códigos inválidos são convertidos em nulos. |
| `EVOLUCAO` | Evolução do caso | São considerados os códigos `1`, `2`, `3` e `9`; códigos inválidos são convertidos em nulos. |
| `VACINA_COV` | Registro de vacinação contra COVID-19 | São considerados os códigos `1`, `2` e `9`; códigos inválidos são convertidos em nulos. |

A base mantém os cinco campos de origem acima e campos derivados para análise temporal e rastreabilidade, como `DATA_REFERENCIA`, `ORIGEM_DATA_REFERENCIA` e `ATRASO_NOTIFICACAO_DIAS`.

Município, idade, sexo e identificadores individuais não fazem parte da base analítica minimizada utilizada pelo agente. O modelo recebe resultados agregados das ferramentas, e não linhas individuais do dataset.

### Tratamento das datas

A leitura de datas diferencia explicitamente o formato brasileiro `dd/mm/aaaa` dos formatos ISO, incluindo timestamps ISO. Isso evita inverter mês e dia ao interpretar datas.

A definição da data de referência segue as regras:

1. Usar `DT_SIN_PRI` quando for válida.
2. Descartar `DT_SIN_PRI` como referência quando estiver ausente, inválida ou for posterior à notificação.
3. Utilizar `DT_NOTIFIC` como fallback quando a data dos sintomas não puder ser utilizada.

O relatório registra o período observado e ressalta a possibilidade de subnotificação e revisão dos dados recentes.

### Domínios dos campos

| Campo | Códigos aceitos | Interpretação |
|---|---|---|
| `UTI` | `1`, `2`, `9` | Sim, não, ignorado/desconhecido |
| `EVOLUCAO` | `1`, `2`, `3`, `9` | Cura, óbito, óbito por outras causas, ignorado/desconhecido |
| `VACINA_COV` | `1`, `2`, `9` | Sim, não, ignorado/desconhecido |

O código `9` é mantido como desconhecido e excluído do denominador dos indicadores que exigem informação conhecida. Códigos fora do domínio e valores malformados são convertidos em nulos e contabilizados no relatório de qualidade.

A solução também registra a quantidade de duplicidades exatas na base minimizada. Essa contagem não confirma duplicações de pacientes ou notificações: como os identificadores individuais não são mantidos, registros iguais nos campos analíticos não são suficientes para provar duplicidade real. Por isso, a solução não remove essas linhas automaticamente.

## 7. Métricas epidemiológicas

### Variação de casos

Compara a quantidade de casos em duas janelas consecutivas de 30 dias: a janela recente e a janela anterior. A comparação respeita um corte temporal que procura reduzir o viés de atraso de notificação.

O atraso é estimado pelo percentil 90 (P90) dos atrasos válidos entre `DT_SIN_PRI` e `DT_NOTIFIC`, considerando notificações dos últimos 180 dias e pelo menos 30 observações válidas.

Quando não há amostra suficiente para estimar o atraso, ou a janela de comparação não é completa, a variação é apresentada como `N/A`, em vez de assumir um atraso arbitrário.

### Mortalidade entre desfechos conhecidos

A métrica é definida como a proporção de óbitos por qualquer causa entre os registros com desfecho conhecido:

- **Numerador:** `EVOLUCAO = 2` ou `EVOLUCAO = 3`.
- **Denominador:** `EVOLUCAO = 1`, `EVOLUCAO = 2` ou `EVOLUCAO = 3`.

O código `EVOLUCAO = 3` corresponde a óbito por outras causas e é apresentado separadamente do código `2`. Essa métrica não deve ser interpretada automaticamente como letalidade exclusivamente por SRAG.

### Indicador de internação em UTI

É calculado como a proporção de registros com `UTI = 1` entre os registros com informação conhecida (`UTI = 1` ou `UTI = 2`).

Esse indicador representa internação em UTI entre casos de SRAG com informação disponível. **Não representa a taxa de ocupação dos leitos hospitalares**, pois a base não oferece todos os elementos necessários para calcular ocupação real.

### Indicador de vacinação contra COVID-19 registrada

É calculado como a proporção de registros com `VACINA_COV = 1` entre aqueles com informação vacinal conhecida (`VACINA_COV = 1` ou `VACINA_COV = 2`).

O indicador representa vacinação contra COVID-19 documentada entre os casos de SRAG. **Não representa a cobertura vacinal da população brasileira**, pois o conjunto de dados não fornece o denominador populacional apropriado.

### Qualidade e completude

O relatório apresenta a completude dos campos de UTI, evolução e vacinação, além das contagens de valores desconhecidos, inválidos e duplicidades exatas na base minimizada.

Todos os indicadores devem ser interpretados considerando seus denominadores, os registros excluídos e as limitações da base.

## 8. Gráficos

O relatório inclui os dois gráficos exigidos pelo desafio:

- **Casos diários dos últimos 30 dias**, com tratamento dos dias sem registros.
- **Casos mensais dos últimos 12 meses**, com indicação de que o período mensal mais recente pode estar incompleto.

Os gráficos são gerados a partir das séries agregadas, com títulos e eixos identificados.

## 9. Agente, guardrails e auditoria

### Orquestração

O agente utiliza LangGraph e integração com o Gemini para selecionar e solicitar ferramentas. As chamadas são encaminhadas pela aplicação, e seus resultados retornam ao fluxo de geração do relatório.

O número máximo de chamadas às ferramentas pode ser ajustado pela variável `MAX_TOOL_CALLS`. O limite reduz o risco de ciclos excessivos de execução.

### Validação da saída

O Output Validator verifica elementos como:

- Presença das seções e dos gráficos obrigatórios.
- Coerência de números e percentuais com os resultados das ferramentas.
- Proveniência das URLs utilizadas.
- Atendimento às condições mínimas de estrutura do relatório.

Essa validação reduz o risco de números ou links sem suporte nos resultados disponíveis, mas não garante a veracidade semântica de todas as afirmações. A revisão humana continua necessária.

### Auditoria

A execução registra eventos em formato JSONL, incluindo informações como identificador da execução, versão da aplicação, modelo utilizado, eventos de ferramentas e do LLM, status da validação e hashes de conteúdo. O registro de tokens depende das informações disponibilizadas pelo provedor.

O arquivo de auditoria pode conter conteúdo de solicitações e respostas. Ele deve permanecer local e não ser compartilhado publicamente sem revisão. Não inclua dados individuais ou informações confidenciais nas solicitações do agente.

### Limitações dos guardrails

Guardrails baseados em padrões, allowlists e validações determinísticas reduzem riscos, mas não garantem que o modelo nunca produza conteúdo incorreto. A validação de proveniência comprova correspondência com resultados registrados, não necessariamente que uma interpretação epidemiológica esteja correta.

## 10. Instalação e execução local

### Pré-requisitos

- Python 3.10 ou superior.
- Git.
- Uma chave de API do Google AI Studio.
- Arquivos CSV válidos do DATASUS.
- Acesso à internet para a integração com o Gemini e a busca externa de notícias.

### 10.1. Clonar o repositório

```bash
git clone https://github.com/vitorturcisn/indiciumai-healthcare-ai-poc.git
cd indiciumai-healthcare-ai-poc
```

### 10.2. Criar o ambiente virtual

```bash
python -m venv .venv
```

No Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[test]"
```

No Linux/macOS:

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[test]"
```

### 10.3. Configurar a chave de API

No Windows PowerShell, configure a chave somente na sessão atual:

```powershell
$secureKey = Read-Host "Digite sua GOOGLE_API_KEY" -AsSecureString
$env:GOOGLE_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
```

No Linux/macOS:

```bash
read -s -p "Digite sua GOOGLE_API_KEY: " GOOGLE_API_KEY
echo
export GOOGLE_API_KEY
```

A chave não deve ser escrita diretamente no código ou no README, nem incluída em commits. O `.gitignore` exclui arquivos de ambiente e outros arquivos comuns de credenciais.

### 10.4. Disponibilizar os arquivos CSV

Crie a pasta `data/` caso não exista e coloque nela os CSVs baixados do DATASUS.

Exemplo de arquivos locais:

```text
data/
├── INFLUD25-28-09-2026.csv
└── INFLUD26-28-09-2026.csv
```

Os nomes acima são exemplos dos snapshots utilizados no ambiente de desenvolvimento. Utilize os nomes reais dos arquivos que você baixou, sem pressupor que novos snapshots terão a mesma data ou estrutura.

A pasta `data/` é local e os arquivos brutos são excluídos do versionamento.

### 10.5. Executar a aplicação

O comando aceita uma ou mais opções `--csv`, uma para cada arquivo:

```powershell
$env:GEMINI_MODEL = "gemini-3.8-flash"

python -m srag_poc.main `
  --csv data/INFLUD25-28-09-2026.csv `
  --csv data/INFLUD26-28-09-2026.csv `
  --request "Gere o relatório nacional agregado de SRAG com métricas, gráficos e contexto institucional recente."
```

Se os nomes dos arquivos forem diferentes, substitua os caminhos pelos nomes disponíveis localmente.

A execução completa depende de uma chave válida, acesso à internet, disponibilidade dos serviços externos e suporte a tool calling no modelo escolhido. A primeira execução pode consumir chamadas de API.

### 10.6. Artefatos gerados

A aplicação utiliza a pasta `outputs/` como diretório padrão para arquivos gerados:

| Arquivo | Descrição |
|---|---|
| `srag_dados.db` | Banco SQLite com dados analíticos minimizados e metadados |
| `qualidade_dados.json` | Resumo do tratamento, qualidade e cobertura temporal |
| `grafico_30_dias.png` | Gráfico diário de casos |
| `grafico_12_meses.png` | Gráfico mensal de casos |
| `relatorio_final.md` | Relatório epidemiológico em Markdown |
| `audit_log.jsonl` | Eventos de auditoria da execução |

Esses artefatos permanecem locais por padrão e não devem ser publicados indiscriminadamente no repositório.

## 11. Testes automatizados

Execute a suíte de testes com:

```bash
python -m pytest -q
```

Os testes cobrem a interpretação de datas, limpeza e ingestão, domínios dos campos, cálculo de métricas, guardrails, processamento do conteúdo do agente e busca de notícias.

Na execução local de 11/10/2026, foram aprovados **39 testes**. A execução também emitiu avisos de depreciação do NumPy/Pandas, que não impediram a aprovação, mas podem exigir manutenção futura.

Os testes unitários são determinísticos e não precisam realizar chamadas ao Gemini ou à busca externa. Por isso, a aprovação dos testes não substitui uma execução completa do agente com credenciais e dados reais.

## 12. Estado atual e limitações conhecidas

A versão atual foi publicada no GitHub com estrutura modular, ferramenta de busca institucional, guardrails, auditoria, métricas e testes automatizados.

Na última execução completa registrada em 11/10/2026, as ferramentas de métricas, gráficos e notícias finalizaram com sucesso, e o validador aprovou o relatório após uma etapa de correção automática.

Entretanto, ainda existe uma limitação relevante na parte de notícias: **a ferramenta consegue localizar fontes e registrar títulos, datas e URLs, mas o relatório ainda precisa sintetizar de forma consistente os achados epidemiológicos do conteúdo consultado e relacioná-los às métricas calculadas**.

Essa etapa é necessária para atender plenamente ao objetivo central do desafio: não apenas apresentar indicadores e fontes externas, mas utilizá-los para explicar e contextualizar o cenário epidemiológico.

Outras limitações importantes:

- Indicadores de UTI e vacinação são proxies baseadas nos campos disponíveis, não estimativas de ocupação real de leitos ou cobertura vacinal populacional.
- Dados recentes podem estar incompletos por atraso de notificação e sujeitos a revisão.
- A validação automatizada não substitui uma revisão epidemiológica humana.
- Os testes unitários não comprovam, isoladamente, a confiabilidade de todas as integrações externas.

## 13. Referências técnicas

- [Dados Abertos do Ministério da Saúde — SRAG 2019–2026](https://dadosabertos.saude.gov.br/dataset/srag-2019-a-2026)
- [OpenDataSUS — SRAG 2021–2024](https://opendatasus.saude.gov.br/dataset/srag-2021-a-2024)
- [Dicionário de dados SIVEP-Gripe](https://opendatasus.saude.gov.br/dataset/srag-2021-a-2024/resource/3135ac9c-2019-4989-a893-2ed50ebd8e68)
- [Google Gemini API — Modelos](https://ai.google.dev/gemini-api/docs/models)
- [Google Gemini API — Function Calling](https://ai.google.dev/gemini-api/docs/function-calling)
- [LangGraph — Documentação](https://docs.langchain.com/oss/python/langgraph/overview)
- [Pytest — Documentação](https://docs.pytest.org/)

---

**Repositório:** [vitorturcisn/indiciumai-healthcare-ai-poc](https://github.com/vitorturcisn/indiciumai-healthcare-ai-poc)
