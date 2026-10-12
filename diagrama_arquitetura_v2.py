from __future__ import annotations

from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit

OUTPUT = Path(__file__).with_name("diagrama_arquitetura_v2.pdf")
PAGE_W, PAGE_H = landscape(A3)

NAVY = colors.HexColor("#15365A")
TEXT = colors.HexColor("#22364A")
MUTED = colors.HexColor("#596D80")
BLUE = colors.HexColor("#DCEAF7")
PALE_BLUE = colors.HexColor("#EDF3F8")
YELLOW = colors.HexColor("#FFF0C9")
GREEN = colors.HexColor("#D9F0EA")
PURPLE = colors.HexColor("#E8E0F4")
WHITE = colors.white
BORDER = colors.HexColor("#254B73")


def draw_box(c: canvas.Canvas, x: float, y: float, w: float, h: float,
             title: str, body: list[str], fill: colors.Color,
             title_size: int = 10, body_size: int = 7) -> None:
    c.setFillColor(fill)
    c.setStrokeColor(BORDER)
    c.setLineWidth(1.05)
    c.roundRect(x, y, w, h, 9, fill=1, stroke=1)

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", title_size)
    title_lines = simpleSplit(title, "Helvetica-Bold", title_size, w - 14)
    title_leading = title_size + 2
    ty = y + h - 17
    for line in title_lines:
        c.drawCentredString(x + w / 2, ty, line)
        ty -= title_leading

    c.setFillColor(TEXT)
    c.setFont("Helvetica", body_size)
    line_leading = body_size + 2
    # Give titles a clear boundary; the body is centered in the remaining height.
    wrapped: list[str] = []
    for item in body:
        wrapped.extend(simpleSplit(item, "Helvetica", body_size, w - 18))
    body_block_height = len(wrapped) * line_leading
    available_bottom = y + 8
    available_top = ty - 4
    body_y = (available_bottom + available_top + body_block_height) / 2
    for line in wrapped:
        c.drawCentredString(x + w / 2, body_y, line)
        body_y -= line_leading


def arrow(c: canvas.Canvas, x1: float, y1: float, x2: float, y2: float,
          dashed: bool = False, color: colors.Color = NAVY) -> None:
    c.saveState()
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(1.05)
    if dashed:
        c.setDash(4, 3)
    c.line(x1, y1, x2, y2)
    angle = __import__("math").atan2(y2 - y1, x2 - x1)
    size = 5
    left = (x2 - size * __import__("math").cos(angle - 0.45), y2 - size * __import__("math").sin(angle - 0.45))
    right = (x2 - size * __import__("math").cos(angle + 0.45), y2 - size * __import__("math").sin(angle + 0.45))
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(*left)
    p.lineTo(*right)
    p.close()
    c.drawPath(p, stroke=0, fill=1)
    c.restoreState()


def draw_diagram(output: Path = OUTPUT) -> Path:
    c = canvas.Canvas(str(output), pagesize=landscape(A3), pageCompression=1)
    c.setTitle("Diagrama de Arquitetura - Indicium HealthCare SRAG PoC v2")
    c.setAuthor("Indicium HealthCare SRAG PoC")
    c.setSubject("Fluxo modular, tool calling, normalização, notícias e auditoria")

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(30, PAGE_H - 34, "Arquitetura da PoC - Agente epidemiológico SRAG")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 9)
    c.drawString(30, PAGE_H - 50, "v2 | tool calling real, evidências HTML/PDF, normalização determinística e auditoria por evento")

    # Primary reporting path.
    top_y, top_h = 606, 102
    top_boxes = [
        (30, 160, "Solicitação CLI", ["--request validado", "entrada agregada", "sem identificadores"], PALE_BLUE),
        (211, 166, "Input Guardrail", ["limite de tamanho", "bloqueio de PII e prompt override", "rejeição antes da ingestão"], YELLOW),
        (398, 188, "Agente LangGraph + Gemini", ["bind_tools / function calling real", "limite compartilhado de tool calls", "tratamento de erros e finalização"], PURPLE),
        (607, 160, "Normalização determinística", ["contagens e denominadores", "EVOLUCAO=3 e duplicidades", "mês parcial e ressalvas"], YELLOW),
        (788, 160, "Output Validator", ["seções e gráficos obrigatórios", "números, percentuais e URLs", "achados de notícias com evidências"], YELLOW),
        (969, 192, "Relatório e artefatos", ["relatorio_final.md", "2 gráficos PNG", "qualidade_dados.json", "banco SQLite e audit JSONL"], GREEN),
    ]
    for x, w, title, body, fill in top_boxes:
        draw_box(c, x, top_y, w, top_h, title, body, fill, title_size=9, body_size=7)
    for i in range(len(top_boxes) - 1):
        x1, w1, *_ = top_boxes[i]
        x2, *_ = top_boxes[i + 1]
        arrow(c, x1 + w1 + 3, top_y + top_h / 2, x2 - 4, top_y + top_h / 2)

    # Tool router and tools.
    router_x, router_y, router_w, router_h = 470, 518, 250, 42
    draw_box(c, router_x, router_y, router_w, router_h, "Tool router + contador de chamadas",
             ["falhas auditadas; limite respeitado"], BLUE, title_size=9, body_size=6)
    arrow(c, 492, top_y, router_x + router_w / 2, router_y + router_h)

    tool_y, tool_h = 342, 128
    tool_boxes = [
        (45, 325, "Tool 1 - consultar_metricas", ["SQLite read-only; agregados e denominadores", "mortalidade / UTI / VACINA_COV", "atraso P90 e qualidade dos dados", "duplicidades após minimização"], BLUE),
        (433, 325, "Tool 2 - gerar_graficos", ["série diária dos últimos 30 dias", "série mensal dos últimos 12 meses", "dias/meses ausentes preenchidos com zero", "último mês parcial identificado"], BLUE),
        (821, 325, "Tool 3 - buscar_noticias", ["DDGS com backends limitados e paralelismo", "allowlist: gov.br / fiocruz.br / who.int", "extração HTML/PDF com limites de tamanho", "texto normalizado e trechos rastreáveis", "snippet marcado quando extração falha"], GREEN),
    ]
    for x, w, title, body, fill in tool_boxes:
        draw_box(c, x, tool_y, w, tool_h, title, body, fill, title_size=9, body_size=7)

    centers = [x + w / 2 for x, w, *_ in tool_boxes]
    branch_y = 493
    arrow(c, router_x + router_w / 2, router_y, router_x + router_w / 2, branch_y, dashed=True, color=MUTED)
    c.saveState()
    c.setStrokeColor(MUTED)
    c.setLineWidth(1.0)
    c.setDash(4, 3)
    c.line(centers[0], branch_y, centers[-1], branch_y)
    c.restoreState()
    for center in centers:
        arrow(c, center, branch_y, center, tool_y + tool_h, dashed=True, color=MUTED)

    c.setFillColor(MUTED)
    c.setFont("Helvetica-Oblique", 7)
    c.drawCentredString(PAGE_W / 2, 482, "Resultados agregados e evidências retornam ao agente; conteúdo externo permanece não confiável")

    # Data and governance layer.
    data_y, data_h = 142, 112
    data_boxes = [
        (30, 190, "CSV DATASUS / SIVEP-Gripe", ["um ou mais snapshots anuais", "arquivos locais ignorados pelo Git", "data de entrada registrada"], PALE_BLUE),
        (250, 214, "Pandas - ingestão e limpeza", ["parse explícito de datas brasileiras/ISO", "validação dos códigos de domínio", "minimização para campos analíticos", "DT_SIN_PRI com fallback DT_NOTIFIC"], YELLOW),
        (494, 202, "SQLite analítico", ["apenas registros minimizados", "consultas agregadas para as tools", "sem linhas individuais no prompt"], BLUE),
        (728, 216, "Fontes institucionais", ["Ministério da Saúde / InfoGripe", "Fiocruz e OMS quando pertinentes", "links e conteúdo de fonte verificados"], GREEN),
        (974, 186, "Audit Log JSONL", ["prompts/respostas e hashes", "tools, validações e tentativas", "tokens quando disponíveis; status final"], PURPLE),
    ]
    for x, w, title, body, fill in data_boxes:
        draw_box(c, x, data_y, w, data_h, title, body, fill, title_size=8, body_size=7)
    # Ingestion pipeline.
    for i in range(2):
        x1, w1, *_ = data_boxes[i]
        x2, *_ = data_boxes[i + 1]
        arrow(c, x1 + w1 + 4, data_y + data_h / 2, x2 - 4, data_y + data_h / 2)

    # SQLite feeds deterministic metric/chart tools.
    db_center = data_boxes[2][0] + data_boxes[2][1] / 2
    c.saveState()
    c.setStrokeColor(MUTED)
    c.setLineWidth(1.0)
    c.setDash(3, 3)
    c.line(db_center, data_y + data_h, db_center, 302)
    c.line(centers[0], 302, centers[1], 302)
    c.restoreState()
    arrow(c, centers[0], 302, centers[0], tool_y, dashed=True, color=MUTED)
    arrow(c, centers[1], 302, centers[1], tool_y, dashed=True, color=MUTED)

    # Official sources feed news search; audit box receives cross-cutting events.
    source_center = data_boxes[3][0] + data_boxes[3][1] / 2
    c.saveState()
    c.setStrokeColor(MUTED)
    c.setLineWidth(1.0)
    c.setDash(3, 3)
    c.line(source_center, data_y + data_h, source_center, 290)
    c.line(source_center, 290, centers[2], 290)
    c.restoreState()
    arrow(c, centers[2], 290, centers[2], tool_y, dashed=True, color=MUTED)

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7)
    c.drawString(30, 119, "Governança: o LLM recebe agregados, não linhas individuais. Auditoria captura chamadas, validações, reparos e resultado final.")
    c.drawString(30, 104, "Limites conceituais: proporção de casos em UTI != ocupação real de leitos; vacina registrada nos casos != cobertura vacinal populacional.")
    c.setStrokeColor(colors.HexColor("#B7C5D2"))
    c.line(30, 89, PAGE_W - 30, 89)
    c.setFillColor(MUTED)
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(30, 72, "Diagrama conceitual alinhado à implementação da PoC. Validação numérica automatizada reduz risco, mas não substitui revisão epidemiológica humana.")
    c.drawRightString(PAGE_W - 30, 72, "Indicium HealthCare SRAG PoC | v2")

    c.showPage()
    c.save()
    return output


if __name__ == "__main__":
    result = draw_diagram()
    print(f"Diagrama gerado: {result}")
