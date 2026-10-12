# Indicium HealthCare - PoC de monitoramento epidemiológico de SRAG

PoC modular de IA generativa para analisar indicadores agregados de Síndrome Respiratória Aguda Grave (SRAG), gerar gráficos e acrescentar contexto de fontes institucionais. Esta versão incorpora a remediação dos feedbacks de validação: limpeza e minimização de dados, tratamento explícito de datas e códigos epidemiológicos, extração de conteúdo HTML/PDF, tool calling real, guardrails de proveniência e auditoria por evento.

> **Escopo:** ferramenta de análise agregada e apoio à vigilância, não é sistema de diagnóstico, prognóstico individual ou decisão clínica. Os resultados dependem do snapshot de dados e da disponibilidade das fontes externas.

## Status da validação local

### Validação ponta a ponta de referência

Foi registrada uma execução ponta a ponta em **12/10/2026**, utilizando `gemini-3.8-flash` e os snapshots `INFLUD25-28-09-2026.csv` e `INFLUD26-28-09-2026.csv`. Naquela execução, a ingestão persistiu **557.361 registros minimizados**, a aplicação terminou com código de saída `0` e o Output Validator aprovou o relatório após uma tentativa limitada de reparo.

Essa execução é uma evidência de referência do comportamento ponta a ponta observado naquele momento. Ela não substitui a execução da suíte automatizada nem garante disponibilidade contínua dos serviços externos.

### Suíte automatizada e integração contínua

Após as últimas alterações de guardrails e métricas, a suíte automatizada foi executada localmente em **12/10/2026**, com o comando `python -m pytest -q`: **65 testes aprovados**, sem avisos de depreciação nessa execução.

O GitHub Actions também passou nos testes para **Python 3.10 e Python 3.12** após a integração das alterações à branch `main`. Consulte a [execução de CI no GitHub Actions](https://github.com/vitorturcisn/indiciumai-healthcare-ai-poc/actions/runs/38294629140).

A suíte automatizada não requer chamadas reais à API do modelo ou aos mecanismos externos de busca. Uma nova validação ponta a ponta continua dependendo de credenciais válidas, conectividade e disponibilidade das fontes.

A validação dos testes e a validação ponta a ponta são evidências distintas; os resultados devem ser interpretados conforme o respectivo escopo.

## Arquitetura

Consulte [`diagrama_arquitetura_v2.pdf`](diagrama_arquitetura_v2.pdf) para o fluxo de ingestão, ferramentas, normalização, validação e auditoria. O código é organizado em `src/srag_poc/`:

- `ingestion.py` e `dates.py`: leitura, validação e minimização dos CSVs;
- `metrics.py`: indicadores agregados e metadados de qualidade;
- `charts.py`: gráficos diários e mensais;
- `news.py`: busca institucional, validação de URLs e extração segura de conteúdo HTML/PDF;
- `agent.py`: LangGraph, chamadas reais de ferramentas, normalização determinística e reparo limitado do relatório;
- `guardrails.py`: validação da solicitação e da saída;
- `audit.py`: log JSONL por evento;
- `config.py` e `main.py`: parâmetros e interface de linha de comando.

### Fluxo principal

1. A solicitação passa pelo guardrail de entrada antes da ingestão ou das chamadas externas.
2. Pandas interpreta datas e códigos, descarta datas obrigatórias inválidas e reduz os dados aos campos analíticos necessários.
3. SQLite armazena os registros minimizados. As ferramentas disponibilizam ao LLM agregados e metadados, não linhas individuais.
4. LangGraph encaminha chamadas reais do Gemini a `consultar_metricas`, `gerar_graficos` e `buscar_noticias`, respeitando o limite de chamadas.
5. O sistema aplica normalizações determinísticas, executa o Output Validator e, quando necessário, permite uma tentativa limitada de reparo.
6. Relatório, gráficos, qualidade e eventos de auditoria são gravados nos diretórios de saída configurados.

## Dados e semântica das métricas

O snapshot é obtido no [Portal de Dados Abertos do SUS - SRAG 2019 a 2026](https://dadosabertos.saude.gov.br/dataset/srag-2019-a-2026). A PoC minimiza os campos analíticos para `DT_NOTIFIC`, `DT_SIN_PRI`, `UTI`, `EVOLUCAO` e `VACINA_COV`, além de datas e metadados derivados necessários à análise.

| Indicador | Definição e limite de interpretação |
|---|---|
| Variação de casos | Compara duas janelas de 30 dias antes do corte calculado para mitigar atraso de notificação. É variação de contagens notificadas, não de incidência populacional. |
| Mortalidade por qualquer causa entre desfechos conhecidos | Numerador: `EVOLUCAO=2` e `EVOLUCAO=3`. Denominador: `EVOLUCAO=1`, `EVOLUCAO=2` e `EVOLUCAO=3`. `EVOLUCAO=3` é óbito por outras causas; não se deve apresentar o indicador como mortalidade atribuída exclusivamente à SRAG. |
| Proporção em UTI | `UTI=1` sobre casos com `UTI=1` ou `UTI=2` conhecido. Não representa ocupação de leitos, que exige dados de capacidade e uso de leitos. |
| Vacina registrada | `VACINA_COV=1` sobre `VACINA_COV=1` ou `VACINA_COV=2` conhecido. Refere-se à vacinação contra COVID-19 registrada entre casos notificados de SRAG, não à cobertura vacinal populacional. |
| Duplicidades exatas após minimização | Coincidências exatas nas colunas analíticas minimizadas. Não comprovam pacientes ou notificações duplicados, pois não há identificador individual unívoco nessa etapa. |

Datas `dd/mm/aaaa` são interpretadas explicitamente como dia/mês/ano; datas ISO são aceitas. `DT_SIN_PRI` é priorizada como referência epidemiológica quando válida, com fallback documentado para `DT_NOTIFIC`. O percentil 90 do atraso de notificação só é estimado quando há amostra válida suficiente; sem isso, a variação pode ser `N/A`, em vez de assumir um atraso.

Os gráficos representam contagens diárias dos últimos 30 dias e mensais dos últimos 12 meses, preenchendo períodos sem registros com zero e identificando o último mês parcial.

## Busca e evidências de notícias

A ferramenta pesquisa fontes institucionais nacionais e aplica uma allowlist de hostnames para `gov.br`, `fiocruz.br` e `who.int`. Resultados externos são tratados como dados não confiáveis, nunca como instruções.

Quando uma fonte é selecionada, a ferramenta tenta recuperar conteúdo HTML ou PDF com limites de tamanho e páginas, normaliza quebras de linha e seleciona trechos relevantes. O resultado mantém URL e método de extração; quando o conteúdo integral não é obtido, a limitação a snippet deve ser explícita. Números e tendências de notícias não devem ser apresentados como métricas calculadas a partir do snapshot local.

A disponibilidade de provedores de busca pode variar e alguns podem retornar erros ou limites de taxa. Uma falha de fonte deve ser auditada e não pode ser interpretada como ausência de risco epidemiológico.

## Guardrails e auditoria

O guardrail de entrada bloqueia solicitações que tentem expor dados individuais ou identificadores. O validador de saída verifica seções e gráficos requeridos, números e percentuais com proveniência nos resultados das ferramentas, URLs permitidas e ressalvas metodológicas. Trata-se de uma barreira determinística de consistência, não de uma prova formal de correção semântica: a revisão humana continua necessária.

`audit_log.jsonl` registra eventos por execução, incluindo chamadas de ferramentas e do LLM, hashes, snapshots de mensagens, respostas, status de validação, reparos e uso de tokens quando disponível. O log não deve receber linhas individuais da base. Como prompts e respostas podem conter informações da solicitação, revise e proteja os logs antes de compartilhá-los; não versione arquivos de auditoria gerados localmente.

## Requisitos e instalação

- Python 3.10 ou superior;
- chave Google Gemini (`GOOGLE_API_KEY`);
- snapshots CSV usados na execução;
- rede e disponibilidade do modelo/provedor para execução ponta a ponta.

No Windows PowerShell, na raiz do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[test]"
$env:GOOGLE_API_KEY = Read-Host "Digite sua GOOGLE_API_KEY"
```

Não grave a chave em código ou em arquivos versionados. Configure-a apenas na sessão local ou pelo gerenciador de segredos utilizado no ambiente.

## Executar a PoC

Os nomes abaixo correspondem aos snapshots usados na validação de referência; adapte-os aos arquivos disponíveis localmente. Os CSVs são ignorados pelo Git e não devem ser versionados.

```powershell
python -m srag_poc.main `
    --csv ".\data\INFLUD25-28-09-2026.csv" `
    --csv ".\data\INFLUD26-28-09-2026.csv"
```

O modelo padrão é `gemini-3.8-flash`. Para trocar o modelo, use `--model` ou defina `GEMINI_MODEL`. A saída padrão é `outputs/`; também pode ser isolada com `SRAG_OUTPUT_DIR`. O banco, relatórios, imagens e logs gerados não devem ser versionados.

Artefatos gerados:

- `relatorio_final.md` - relatório epidemiológico;
- `grafico_30_dias.png` e `grafico_12_meses.png` - séries de contagens;
- `qualidade_dados.json` - completude e metadados da limpeza;
- `srag_dados.db` - banco SQLite minimizado;
- `audit_log.jsonl` - auditoria por evento.

## Testes automatizados

Execute:

```powershell
python -m pytest -q
```

Na validação local de **12/10/2026**, foram aprovados **65 testes**. A execução da suíte não exige chamadas à API ou busca externa; a validação ponta a ponta requer credenciais e rede. A CI verifica Python 3.10 e 3.12 no GitHub Actions.

Arquivos cobertos:

- `test_dates_and_ingestion.py` e `test_dates_iso_regression.py` - datas, limpeza e minimização;
- `test_metrics.py` - denominadores, desfechos, atraso e duplicidades após minimização;
- `test_news.py` - allowlist, extração HTML/PDF, normalização e limites da busca;
- `test_guardrails.py` - entrada/saída, números, percentuais, URLs e evidências;
- `test_agent_content.py` - requisitos de conteúdo do relatório;
- `test_orchestration_audit.py` - tool calling, falhas e eventos de auditoria;
- `test_report_normalization.py` - normalizações determinísticas e regressões metodológicas.

Para regenerar o diagrama PDF após editar `diagrama_arquitetura_v2.py`, instale `reportlab` no ambiente de desenvolvimento e execute:

```powershell
python diagrama_arquitetura_v2.py
```

## Referências

- [Portal de Dados Abertos do SUS - SRAG 2019 a 2026](https://dadosabertos.saude.gov.br/dataset/srag-2019-a-2026)
- [Dicionário de dados SRAG/SIVEP-Gripe](https://opendatasus.saude.gov.br/dataset/srag-2021-a-2024/resource/3135ac9c-2019-4989-a893-2ed50ebd8e68)
- [Documentação de modelos Gemini](https://ai.google.dev/gemini-api/docs/models)

## Publicação e controle de versão

Antes de publicar, revise o diff, confira se os CSVs, o SQLite, relatórios e logs estão ignorados pelo Git, execute `python -m pytest -q` e valide que o README e o diagrama correspondem ao código efetivamente entregue. Prefira commits pequenos e com propósito claro; não sobrescreva `main` sem revisão e abra um Pull Request para avaliação.
