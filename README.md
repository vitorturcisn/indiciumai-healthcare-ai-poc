# Indicium HealthCare — PoC de monitoramento epidemiológico de SRAG

Prova de Conceito (PoC) de Inteligência Artificial Generativa para analisar dados agregados de Síndrome Respiratória Aguda Grave (SRAG), calcular indicadores epidemiológicos, gerar gráficos e contextualizar os resultados com informações de fontes institucionais.

A solução combina Python, Pandas, SQLite, LangChain, LangGraph e Google Gemini. O agente utiliza chamadas reais de ferramentas (*tool calling*) para consultar métricas, gerar gráficos e pesquisar notícias. O relatório passa por normalizações determinísticas e por um validador de saída, com uma tentativa limitada de reparo quando necessário.

> **Escopo e responsabilidade:** esta PoC é uma ferramenta experimental de análise agregada e apoio à vigilância epidemiológica. Não é um sistema de diagnóstico, prognóstico individual ou decisão clínica. Seus resultados dependem da qualidade e da atualidade dos dados, das evidências disponíveis e da disponibilidade dos serviços externos.

## 1. Status da validação

### Validação ponta a ponta

Foi registrada uma execução de referência em **12/10/2026**, utilizando o modelo `gemini-3.8-flash` e os snapshots `INFLUD25-28-09-2026.csv` e `INFLUD26-28-09-2026.csv`.

Nessa execução, a ingestão persistiu **557.361 registros minimizados**, a aplicação terminou com código de saída `0` e o Output Validator aprovou o relatório após uma tentativa limitada de reparo.

Esse resultado documenta uma execução observada em um momento específico. Não garante que uma nova execução produzirá os mesmos resultados, pois o snapshot, as fontes externas, a conectividade e a disponibilidade do provedor podem mudar.

### Testes automatizados e integração contínua

A suíte automatizada foi executada localmente com:

```powershell
python -m pytest -q
```

**Resultado registrado: 70 testes aprovados.**

Após a integração das alterações técnicas à branch `main`, o GitHub Actions também concluiu com sucesso os jobs de **Python 3.10 e Python 3.12**, incluindo as verificações do Ruff e a execução dos testes.

[Consultar a execução de CI no GitHub Actions](https://github.com/vitorturcisn/indiciumai-healthcare-ai-poc/actions/runs/38301659925)

A suíte automatizada não requer chamadas reais à API do modelo ou aos mecanismos externos de busca. A validação ponta a ponta, por outro lado, depende de credenciais válidas, conectividade, disponibilidade do modelo e acesso às fontes.

Os testes verificam comportamentos definidos pelo projeto; não substituem uma revisão epidemiológica humana nem constituem prova formal da correção semântica de todas as respostas geradas pelo LLM.

## 2. Objetivo e relação com o desafio

O desafio propõe uma solução baseada em IA Generativa capaz de consultar dados e notícias, calcular métricas relevantes e produzir relatórios com explicações sobre o cenário analisado.

A PoC implementa esse fluxo com:

- ingestão, validação, tratamento e minimização dos dados;
- armazenamento analítico local em SQLite;
- ferramentas determinísticas para métricas e gráficos;
- pesquisa de fontes institucionais e extração controlada de conteúdo;
- agente orquestrado por LangGraph com chamadas reais de ferramentas;
- guardrails de entrada e saída;
- auditoria por eventos em JSONL;
- relatório em Markdown e artefatos gerados localmente;
- testes automatizados e integração contínua.

O objetivo é demonstrar uma arquitetura modular, verificável e consciente das limitações dos dados e dos modelos generativos.

## 3. Arquitetura

Consulte o arquivo [`diagrama_arquitetura_v2.pdf`](diagrama_arquitetura_v2.pdf) para visualizar o fluxo entre a solicitação, o agente, as ferramentas, o banco, as fontes externas, a validação e a auditoria.

### Fluxo de execução

1. **Entrada e validação:** a solicitação passa pelo guardrail antes da ingestão e das chamadas externas.
2. **Ingestão e minimização:** Pandas interpreta datas, valida códigos epidemiológicos e mantém somente as colunas analíticas necessárias, além dos campos derivados utilizados pela aplicação.
3. **Persistência:** os dados minimizados são gravados em um banco SQLite local.
4. **Orquestração:** LangGraph organiza as interações com o Gemini e as ferramentas, observando o limite configurado de chamadas.
5. **Execução das ferramentas:** o agente pode consultar métricas, gerar gráficos e buscar notícias institucionais.
6. **Normalização:** regras determinísticas acrescentam ou corrigem informações metodológicas obrigatórias, sem depender exclusivamente do texto produzido pelo modelo.
7. **Validação de saída:** o relatório é verificado quanto à estrutura, à proveniência de números e percentuais, às URLs e ao suporte das afirmações sobre notícias.
8. **Reparo limitado:** se a validação reprovar o relatório, o agente pode realizar uma única tentativa de reparo, sem novas chamadas às ferramentas nessa etapa.
9. **Finalização:** quando aprovado, o relatório e os eventos de auditoria são gravados nos locais configurados.

### Ferramentas disponíveis ao agente

| Ferramenta | Responsabilidade |
|---|---|
| `consultar_metricas` | Calcula os indicadores agregados, os denominadores, o atraso de notificação e os indicadores de qualidade. |
| `gerar_graficos` | Gera as séries diárias dos últimos 30 dias e as séries mensais dos últimos 12 meses. |
| `buscar_noticias` | Pesquisa fontes institucionais, valida URLs e tenta recuperar conteúdo HTML ou PDF para obter evidências relevantes. |

As consultas analíticas não dependem de SQL escrito livremente pelo LLM. O agente utiliza ferramentas definidas pela aplicação, com operações controladas e resultados delimitados.

### Organização do código

O código principal está em `src/srag_poc/`:

| Arquivo | Responsabilidade |
|---|---|
| `main.py` | Interface de linha de comando, configuração da execução e geração do relatório. |
| `config.py` | Parâmetros, caminhos, modelo padrão e limites da aplicação. |
| `dates.py` | Interpretação explícita de datas brasileiras e ISO. |
| `ingestion.py` | Leitura dos CSVs, tratamento dos códigos, minimização, qualidade e gravação do banco. |
| `database.py` | Abertura de conexões SQLite em modo somente leitura para as ferramentas analíticas. |
| `metrics.py` | Cálculo dos indicadores e metadados de qualidade. |
| `charts.py` | Geração dos gráficos diários e mensais. |
| `news.py` | Busca institucional, validação de URLs e extração de conteúdo. |
| `agent.py` | Grafo LangGraph, tool calling, tratamento de falhas, normalização e reparo limitado. |
| `guardrails.py` | Validação da solicitação e da saída, com verificações de proveniência. |
| `audit.py` | Registro dos eventos e funções de geração de hashes. |

## 4. Dados e origem

A implementação utiliza a série pública **SRAG 2019 a 2026**, disponível no Portal de Dados Abertos do SUS:

- [Dataset SRAG 2019–2026 — Portal de Dados Abertos do SUS](https://dadosabertos.saude.gov.br/dataset/srag-2019-a-2026)
- [Dataset SRAG 2021–2024 — referência indicada no enunciado](https://opendatasus.saude.gov.br/dataset/srag-2021-a-2024)
- [Dicionário de dados SRAG/SIVEP-Gripe](https://opendatasus.saude.gov.br/dataset/srag-2021-a-2024/resource/3135ac9c-2019-4989-a893-2ed50ebd8e68)

**Escolha do conjunto de dados:** o enunciado original indica a série SRAG 2021–2024. Esta implementação optou pela série pública SRAG 2019–2026 para ampliar o intervalo histórico e permitir análises com snapshots mais recentes. A escolha está documentada para deixar explícita a diferença em relação à referência original. A execução depende dos arquivos CSV efetivamente obtidos e fornecidos ao programa.

A leitura dos arquivos utiliza o separador `;` e tenta encodings comuns, incluindo UTF-8 e Latin-1. A aplicação verifica a presença das colunas obrigatórias e permite fornecer mais de um snapshot na mesma execução.

### Minimização de dados

A aplicação seleciona inicialmente as variáveis necessárias à análise:

- `DT_NOTIFIC`: data da notificação;
- `DT_SIN_PRI`: data dos primeiros sintomas, quando disponível;
- `UTI`: informação registrada sobre internação em UTI;
- `EVOLUCAO`: classificação do desfecho;
- `VACINA_COV`: informação registrada sobre vacinação contra COVID-19.

A aplicação também produz campos derivados para a data de referência, sua origem e o atraso entre o início dos sintomas e a notificação.

Outras colunas presentes nos CSVs de origem, como idade e sexo, não são mantidas na tabela analítica minimizada. O LLM recebe os resultados das ferramentas, que trabalham com agregados e metadados, e não linhas individuais de pacientes.

### Tratamento e qualidade

A ingestão aplica as seguintes regras:

- interpretação explícita de datas brasileiras no formato `dd/mm/aaaa` e aceitação de formatos ISO;
- exclusão de registros sem data válida de notificação;
- prioridade para `DT_SIN_PRI` quando válida;
- fallback para `DT_NOTIFIC` quando a data de início dos sintomas estiver ausente, inválida ou posterior à notificação;
- validação dos domínios de `UTI`, `EVOLUCAO` e `VACINA_COV`;
- conversão de valores malformados ou fora do domínio esperado em valores nulos após a contabilização na qualidade;
- registro da completude, das datas e das quantidades removidas ou normalizadas.

O código `9` é reconhecido como valor ignorado/desconhecido nos domínios definidos pela aplicação e não entra nos denominadores dos indicadores correspondentes. Códigos inválidos não são tratados como respostas conhecidas.

A aplicação também calcula coincidências exatas nas colunas minimizadas. Como identificadores individuais não são mantidos, essa contagem não comprova que pacientes ou notificações sejam duplicados. Por esse motivo, esses registros não são removidos automaticamente com base somente nessa coincidência.

## 5. Definição e interpretação das métricas

As métricas são calculadas pelas ferramentas determinísticas a partir da base minimizada.

| Indicador | Cálculo e interpretação |
|---|---|
| Variação percentual de casos | Compara contagens em duas janelas de 30 dias, antes do corte utilizado para mitigar o atraso de notificação. Mede variação das contagens notificadas, não incidência populacional. |
| Mortalidade por qualquer causa entre desfechos conhecidos | Numerador: `EVOLUCAO=2` e `EVOLUCAO=3`. Denominador: `EVOLUCAO=1`, `EVOLUCAO=2` e `EVOLUCAO=3`. O grupo `EVOLUCAO=2` também é apresentado separadamente. |
| Proporção de casos com internação em UTI registrada | `UTI=1` dividido pelos casos com `UTI=1` ou `UTI=2` conhecido. É uma proporção entre casos SRAG com informação conhecida, não uma medida de ocupação real de leitos. |
| Proporção de casos com vacinação contra COVID-19 registrada | `VACINA_COV=1` dividido pelos casos com `VACINA_COV=1` ou `VACINA_COV=2` conhecido. Não representa cobertura vacinal da população geral. |

### Atraso de notificação

As datas mais recentes podem estar subnotificadas ou ser revisadas. Para reduzir esse viés, a ferramenta estima o percentil 90 (P90) dos atrasos válidos entre início dos sintomas e notificação.

A estimativa considera atrasos não negativos de até 365 dias e notificações dos 180 dias mais recentes. O P90 só é calculado quando há pelo menos 30 atrasos válidos nessa janela. Quando existe amostra suficiente, o cálculo da variação utiliza um corte conservador, excluindo os dias finais estimados pelo P90. Sem amostra suficiente ou sem janela anterior completa, a variação pode ser apresentada como `N/A`, em vez de presumir um atraso.

Registros sem data válida de início dos sintomas continuam usando a data de notificação como fallback. Por isso, o ajuste reduz um risco de interpretação, mas não elimina todas as limitações temporais do snapshot.

### Limitações epidemiológicas

Os indicadores precisam ser interpretados conforme seus denominadores e as definições das variáveis:

- `EVOLUCAO=3` significa óbito por outras causas; o indicador que inclui `EVOLUCAO=2` e `EVOLUCAO=3` é descrito como mortalidade por qualquer causa entre desfechos conhecidos, não como mortalidade atribuída exclusivamente à SRAG.
- A proporção de casos com internação em UTI registrada não equivale à ocupação hospitalar de UTI. A ocupação exige dados de capacidade e uso de leitos.
- `VACINA_COV` se refere à vacinação contra COVID-19 registrada entre casos SRAG, não à cobertura vacinal populacional.
- A variação de contagens notificadas não equivale à variação de incidência populacional.
- As estimativas dependem da completude, da consistência e da atualização dos registros recebidos.

## 6. Gráficos

A ferramenta gera dois gráficos determinísticos:

- `grafico_30_dias.png`: contagens diárias nos últimos 30 dias disponíveis no snapshot;
- `grafico_12_meses.png`: contagens mensais nos últimos 12 meses disponíveis no snapshot.

As séries são ancoradas na data de referência mais recente disponível no banco, e não necessariamente no dia atual do calendário. Períodos sem registros são preenchidos com zero. O gráfico mensal identifica quando o último mês é parcial.

Os gráficos apresentam títulos, eixos e informações metodológicas para apoiar a interpretação das séries. A leitura dos períodos recentes deve considerar o atraso de notificação e a possibilidade de revisão dos dados.

## 7. Busca de notícias e evidências externas

A ferramenta de notícias complementa os indicadores locais com contexto institucional. Ela realiza buscas externas e, quando necessário, consulta páginas institucionais como fallback.

A implementação utiliza uma allowlist de hostnames institucionais, incluindo:

- `gov.br`;
- `fiocruz.br`;
- `who.int`.

As URLs são verificadas quanto ao uso de HTTPS e ao domínio permitido. Os redirecionamentos também são validados antes de serem seguidos, para evitar que uma URL inicialmente permitida redirecione para um destino não autorizado.

Quando uma fonte é selecionada, a ferramenta tenta recuperar conteúdo HTML ou PDF, respeitando limites de tamanho, páginas e tempo. O texto é normalizado e trechos relevantes são selecionados para sustentar a síntese.

### Limites e transparência

- Títulos, snippets e resultados de busca são dados externos não confiáveis e não devem ser tratados como instruções ao agente.
- A ferramenta busca contexto nacional e rejeita páginas genéricas ou resultados claramente pouco aderentes ao tema.
- Quando o conteúdo integral não é recuperado, essa limitação deve ser informada explicitamente. Snippets, títulos e URLs isolados não sustentam uma síntese epidemiológica substantiva.
- As afirmações sobre notícias são verificadas quanto ao suporte em passagens extraídas e à compatibilidade de tendências explícitas.
- O contexto das notícias é separado das métricas calculadas sobre o snapshot local.
- Falhas de busca ou ausência de resultados não significam ausência de risco epidemiológico.

A busca depende da disponibilidade dos provedores e das fontes. A extração e as verificações reduzem riscos de afirmações sem suporte, mas não substituem a revisão humana da fonte original.

## 8. Guardrails, segurança e auditoria

### Guardrail de entrada

A solicitação é validada antes da ingestão e das chamadas externas. São aplicados limites de tamanho e padrões de bloqueio para pedidos de exposição de dados pessoais, registros individualizados e tentativas conhecidas de sobrescrever as instruções do agente.

### Validação de saída

O Output Validator verifica os elementos obrigatórios do relatório, a presença dos gráficos quando disponíveis, a proveniência de números e percentuais, as URLs permitidas e as ressalvas metodológicas. Também verifica o suporte de afirmações sobre notícias quando existem metadados de extração.

Quando a validação reprova o relatório, o agente tem direito a uma tentativa limitada de reparo. Se o relatório continuar inválido, a aplicação não o trata como execução bem-sucedida.

Esses mecanismos são barreiras determinísticas de consistência, e não uma prova formal de correção semântica. A revisão humana permanece necessária.

### Auditoria por evento

O arquivo `audit_log.jsonl` registra eventos da execução, incluindo:

- identificação da execução, versão da aplicação e modelo selecionado;
- início e conclusão das chamadas do LLM;
- hashes e comprimentos de conteúdo, além de metadados das ferramentas;
- início, conclusão, bloqueio ou falha de chamadas de ferramentas;
- hashes dos arquivos CSV de entrada e seus tamanhos;
- resultado da validação, reparos e status final;
- uso de tokens quando fornecido pelo provedor.

A auditoria padrão não persiste o conteúdo integral de prompts, respostas e argumentos das ferramentas. Em vez disso, registra hashes, tamanhos, nomes de ferramentas, chaves de argumentos e metadados selecionados para permitir rastreabilidade sem copiar desnecessariamente o conteúdo.

Os CSVs de entrada são identificados pelo nome, tamanho e SHA-256, sem copiar seus conteúdos ou caminhos absolutos para os eventos de auditoria. Logs podem conter metadados operacionais, portanto devem ser protegidos e revisados antes do compartilhamento.

Os arquivos de auditoria gerados localmente não devem ser versionados.

## 9. Requisitos e instalação

### Requisitos

- Python 3.10 ou superior;
- chave de API do Google Gemini;
- arquivos CSV de entrada compatíveis com as colunas esperadas;
- conectividade com o provedor do modelo e com fontes externas para a execução ponta a ponta.

### Instalação no Windows PowerShell

Na raiz do repositório:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test,diagram,lint]"
```

Configure a chave de API na sessão atual do PowerShell, sem gravá-la no repositório:

```powershell
$secureKey = Read-Host "Digite sua GOOGLE_API_KEY" -AsSecureString
$env:GOOGLE_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
```

Não coloque a chave de API no código, no README, em arquivos versionados ou em logs compartilhados. Para ambientes persistentes, utilize um gerenciador de segredos apropriado.

## 10. Executar a PoC

Os nomes abaixo correspondem aos snapshots utilizados na validação de referência. Ajuste os caminhos para os arquivos que você obteve localmente.

Os CSVs não são fornecidos pelo repositório e devem permanecer fora do controle de versão.

```powershell
python -m srag_poc.main `
    --csv ".\data\INFLUD25-28-09-2026.csv" `
    --csv ".\data\INFLUD26-28-09-2026.csv"
```

A opção `--csv` pode ser repetida para combinar mais de um arquivo. A aplicação valida a solicitação, verifica os arquivos, registra seus metadados, executa a ingestão e inicia o agente.

O modelo padrão é `gemini-3.8-flash`. Para selecionar outro modelo compatível com tool calling, utilize `--model`:

```powershell
python -m srag_poc.main `
    --csv ".\data\INFLUD25-28-09-2026.csv" `
    --csv ".\data\INFLUD26-28-09-2026.csv" `
    --model "gemini-3.8-flash"
```

A solicitação do relatório pode ser personalizada com `--request`, mas continuará sujeita ao guardrail de entrada.

### Artefatos gerados

Por padrão, a saída é gravada no diretório `outputs/`, que pode ser alterado com `SRAG_OUTPUT_DIR`.

| Artefato | Descrição |
|---|---|
| `relatorio_final.md` | Relatório epidemiológico final aprovado pelo validador. |
| `grafico_30_dias.png` | Gráfico diário dos últimos 30 dias disponíveis no snapshot. |
| `grafico_12_meses.png` | Gráfico mensal dos últimos 12 meses disponíveis no snapshot. |
| `qualidade_dados.json` | Metadados da ingestão, completude e tratamento dos dados. |
| `srag_dados.db` | Banco SQLite com os dados minimizados. |
| `audit_log.jsonl` | Eventos de auditoria da execução. |

A configuração também permite ajustar, quando necessário, caminhos por variáveis de ambiente, incluindo `SRAG_DB_PATH`, `SRAG_AUDIT_PATH`, `SRAG_QUALITY_PATH` e `SRAG_REPORT_PATH`. O modelo padrão pode ser definido por `GEMINI_MODEL`; o limite de chamadas de ferramentas pode ser configurado por `MAX_TOOL_CALLS`.

O banco, os relatórios, as imagens e os logs são artefatos locais de execução e não devem ser versionados.

## 11. Testes automatizados

Execute a suíte na raiz do repositório:

```powershell
python -m pytest -q
```

Para executar as verificações estáticas:

```powershell
python -m ruff check src tests
```

Na validação local documentada para a versão técnica integrada, foram aprovados **70 testes**, e o Ruff concluiu sem erros. A integração contínua executou os mesmos comandos para Python 3.10 e Python 3.12.

Os principais grupos de testes cobrem:

- `test_dates_and_ingestion.py` e `test_dates_iso_regression.py`: interpretação de datas, limpeza, minimização e regras dos domínios;
- `test_metrics.py`: denominadores, desfechos, vacinação, atraso e duplicidades após minimização;
- `test_news.py`: allowlist, redirecionamentos, extração HTML/PDF, filtros e limites de busca;
- `test_guardrails.py`: validação de entrada e saída, proveniência numérica, URLs e evidências de notícias;
- `test_agent_content.py`: extração de conteúdo textual das respostas do modelo;
- `test_orchestration_audit.py`: tool calling, falhas, limite de chamadas, auditoria e privacidade;
- `test_database_readonly.py`: consultas somente leitura e prevenção de criação acidental do banco;
- `test_report_normalization.py`: normalizações determinísticas e regras metodológicas obrigatórias.

A suíte automatizada não exige chave de API válida para testar os comportamentos cobertos pelos testes. Uma nova execução ponta a ponta exige credenciais e conectividade.

### Regenerar o diagrama

Depois de alterar `diagrama_arquitetura_v2.py`, instale a dependência opcional do diagrama e regenere o PDF:

```powershell
python -m pip install -e ".[diagram]"
python diagrama_arquitetura_v2.py
```

O arquivo gerado é `diagrama_arquitetura_v2.pdf`.

## 12. Limitações conhecidas

A PoC é uma demonstração técnica, não um produto de vigilância epidemiológica em produção.

- A qualidade dos resultados depende da completude, da consistência e da atualização dos dados do SIVEP-Gripe.
- O atraso de notificação é estimado a partir dos registros com datas válidas e amostra suficiente; o ajuste não elimina todos os vieses temporais.
- As métricas de UTI e vacinação são proporções entre casos com informação conhecida, não medidas de ocupação hospitalar ou cobertura populacional.
- Duplicidades exatas após minimização não permitem identificar duplicação real de pessoas ou notificações.
- As fontes externas podem estar indisponíveis, retornar apenas snippets ou não oferecer conteúdo suficiente para uma síntese confiável.
- O guardrail de saída aplica regras determinísticas e verificações lexicais e de proveniência; não garante que toda interpretação textual esteja epidemiologicamente correta.
- Uma execução ponta a ponta depende de credenciais, conectividade e disponibilidade do Gemini e dos mecanismos externos de busca.
- O resultado deve ser revisado por uma pessoa com conhecimento do contexto epidemiológico antes de ser usado para comunicação ou tomada de decisão.

## 13. Referências

- [Portal de Dados Abertos do SUS — SRAG 2019 a 2026](https://dadosabertos.saude.gov.br/dataset/srag-2019-a-2026)
- [Open DATASUS — SRAG 2021 a 2024, conjunto indicado no desafio](https://opendatasus.saude.gov.br/dataset/srag-2021-a-2024)
- [Dicionário de dados SRAG/SIVEP-Gripe](https://opendatasus.saude.gov.br/dataset/srag-2021-a-2024/resource/3135ac9c-2019-4989-a893-2ed50ebd8e68)
- [Documentação de modelos Gemini](https://ai.google.dev/gemini-api/docs/models)
- [Repositório GitHub](https://github.com/vitorturcisn/indiciumai-healthcare-ai-poc)
- [GitHub Actions — execução de CI da versão técnica integrada](https://github.com/vitorturcisn/indiciumai-healthcare-ai-poc/actions/runs/38301659925)

---

**Indicium HealthCare — PoC de monitoramento epidemiológico de SRAG.**
