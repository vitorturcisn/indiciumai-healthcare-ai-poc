"""Gera diagrama conceitual da arquitetura v2 em PDF (ReportLab)."""
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit

OUT = Path(__file__).resolve().parent / "diagrama_arquitetura_v2.pdf"
PAGE_W, PAGE_H = landscape(A3)

NAVY = colors.HexColor("#19324D")
BLUE = colors.HexColor("#DCEAF7")
TEAL = colors.HexColor("#D9F0EC")
GOLD = colors.HexColor("#FFF0CC")
PURPLE = colors.HexColor("#E9E0F5")
GRAY = colors.HexColor("#EEF1F4")
DARK = colors.HexColor("#243746")
MUTED = colors.HexColor("#596B78")
WHITE = colors.white


def box(c, x, y, w, h, title, lines=(), fill=BLUE, stroke=NAVY, title_size=10, body_size=8):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(1.1)
    c.roundRect(x, y, w, h, 9, fill=1, stroke=1)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", title_size)
    c.drawCentredString(x + w / 2, y + h - 17, title)
    body = "\n".join(lines)
    if body:
        c.setFillColor(DARK)
        c.setFont("Helvetica", body_size)
        wrapped = []
        for line in lines:
            wrapped.extend(simpleSplit(line, "Helvetica", body_size, w - 16))
        total_h = len(wrapped) * (body_size + 3)
        yy = y + (h - 18 + total_h) / 2 - body_size + 1
        for line in wrapped:
            c.drawCentredString(x + w / 2, yy, line)
            yy -= body_size + 3


def arrow(c, x1, y1, x2, y2, color=NAVY, dashed=False, width=1.3, head=6):
    c.saveState()
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(width)
    if dashed:
        c.setDash(4, 3)
    c.line(x1, y1, x2, y2)
    import math
    angle = math.atan2(y2 - y1, x2 - x1)
    left = (x2 - head * math.cos(angle - math.pi / 6), y2 - head * math.sin(angle - math.pi / 6))
    right = (x2 - head * math.cos(angle + math.pi / 6), y2 - head * math.sin(angle + math.pi / 6))
    path = c.beginPath()
    path.moveTo(x2, y2)
    path.lineTo(*left)
    path.lineTo(*right)
    path.close()
    c.drawPath(path, fill=1, stroke=0)
    c.restoreState()


def elbow_arrow(c, points, color=NAVY, dashed=False, head=6):
    for a, b in zip(points[:-2], points[1:-1]):
        c.saveState()
        c.setStrokeColor(color)
        c.setLineWidth(1.2)
        if dashed:
            c.setDash(4, 3)
        c.line(a[0], a[1], b[0], b[1])
        c.restoreState()
    arrow(c, *points[-2], *points[-1], color=color, dashed=dashed, head=head)


def main():
    c = canvas.Canvas(str(OUT), pagesize=landscape(A3))
    c.setTitle("Diagrama de Arquitetura - Indicium HealthCare SRAG PoC v2")
    c.setAuthor("Indicium HealthCare SRAG PoC")

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(30, PAGE_H - 38, "Arquitetura conceitual - Agente epidemiológico SRAG")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 9)
    c.drawString(30, PAGE_H - 55, "v2 | tool calling real, minimização de dados, validação de proveniência e auditoria por evento")

    # Pipeline principal
    main_y, main_h = 650, 84
    box(c, 28, main_y, 142, main_h, "Solicitação CLI", ["--request validado", "sem identificadores"], fill=GRAY)
    box(c, 205, main_y, 155, main_h, "Input Guardrail", ["Limite de tamanho", "PII / prompt override", "rejeição antes da ingestão"], fill=GOLD)
    box(c, 395, main_y, 220, main_h, "Agente LangGraph + Gemini", ["bind_tools / function calling", "decide qual tool executar", "limite total de chamadas", "finalização sem tools no limite"], fill=PURPLE)
    box(c, 660, main_y, 160, main_h, "Output Validator", ["seções / gráficos", "números e percentuais", "URLs com proveniência"], fill=GOLD)
    box(c, 865, main_y, 290, main_h, "Relatório e artefatos", ["relatorio_final.md", "grafico_30_dias.png + grafico_12_meses.png", "qualidade_dados.json"], fill=TEAL)

    arrow(c, 170, main_y + main_h / 2, 205, main_y + main_h / 2)
    arrow(c, 360, main_y + main_h / 2, 395, main_y + main_h / 2)
    arrow(c, 615, main_y + main_h / 2, 660, main_y + main_h / 2)
    arrow(c, 820, main_y + main_h / 2, 865, main_y + main_h / 2)

    # Router de ferramentas e tools
    box(c, 445, 540, 165, 55, "Tool router", ["respeita os tool_calls do LLM"], fill=BLUE, title_size=9, body_size=7.5)
    arrow(c, 505, main_y, 505, 595)
    # Branch bus between router and tool cards
    bus_y = 505
    c.setStrokeColor(NAVY)
    c.setLineWidth(1.1)
    c.line(172, bus_y, 802, bus_y)
    for center in (172, 487, 802):
        arrow(c, center, bus_y, center, 478, head=5)
    box(c, 52, 390, 240, 88, "Tool 1 - consultar_metricas", ["SQLite read-only", "agregados e denominadores", "mortalidade / UTI / VACINA_COV", "ajuste do atraso de notificação"], fill=BLUE, title_size=9, body_size=7.2)
    box(c, 367, 390, 240, 88, "Tool 2 - gerar_graficos", ["SQLite agregado", "série diária de 30 dias", "série mensal de 12 meses", "datas ausentes preenchidas com zero"], fill=BLUE, title_size=9, body_size=7.2)
    box(c, 682, 390, 240, 88, "Tool 3 - buscar_noticias", ["DDGS com consultas nacionais", "allowlist gov.br / fiocruz.br / who.int", "trechos sao dados externos", "falha não significa ausência de risco"], fill=TEAL, title_size=9, body_size=7.2)
    c.setFillColor(MUTED)
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(615, 518, "tool results agregados retornam ao agente para redação")
    # Loop de retorno conceitual
    elbow_arrow(c, [(922, 430), (950, 430), (950, 536), (610, 536), (610, 567)], color=MUTED, dashed=True, head=5)

    # Camada de dados e fontes
    box(c, 35, 180, 175, 80, "CSV DATASUS", ["um ou mais anos", "não versionados", "snapshot com data registrada"], fill=GRAY, title_size=9)
    box(c, 250, 180, 235, 80, "Pandas - ingestão/limpeza", ["parse DD/MM/AAAA explícito", "regras de domínio aplicadas", "minimização para 5 campos", "DT_SIN_PRI / fallback DT_NOTIFIC"], fill=GOLD, title_size=9, body_size=7.5)
    box(c, 530, 180, 190, 80, "SQLite analitico", ["casos minimizados", "indices por data", "metadata + qualidade", "sem município/idade/sexo"], fill=BLUE, title_size=9, body_size=7.5)
    box(c, 765, 180, 200, 80, "Fontes institucionais", ["Ministério da Saúde", "Fiocruz / InfoGripe", "OMS quando relevante", "somente links validados"], fill=TEAL, title_size=9, body_size=7.5)
    box(c, 1005, 180, 150, 80, "Audit Log JSONL", ["start / finish / error", "prompts e respostas", "hashes e tokens", "validação e tool calls"], fill=PURPLE, title_size=9, body_size=7.2)

    arrow(c, 210, 220, 250, 220)
    arrow(c, 485, 220, 530, 220)
    arrow(c, 922, 390, 865, 260, color=MUTED, dashed=True, head=5)
    # Database connector - routed to metrics and charts without crossing text boxes.
    elbow_arrow(c, [(625, 260), (625, 330), (172, 330), (172, 390)], color=MUTED, dashed=True, head=5)
    elbow_arrow(c, [(635, 260), (635, 345), (487, 345), (487, 390)], color=MUTED, dashed=True, head=5)
    # Audit observes lifecycle of orchestration and validation.
    elbow_arrow(c, [(505, 650), (505, 625), (1080, 625), (1080, 260)], color=PURPLE, dashed=True, head=5)
    arrow(c, 965, 220, 1005, 220, color=MUTED, dashed=True, head=5)

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(35, 135, "Dados sensíveis: o modelo nunca recebe linhas individuais. Os resultados numéricos sao calculados fora do LLM.")
    c.drawString(35, 120, "Importante: ocupação real de UTI e cobertura vacinal populacional não são estimáveis apenas com estes campos; o relatório identifica as proxies.")
    c.setStrokeColor(colors.HexColor("#CDD5DC"))
    c.line(30, 105, PAGE_W - 30, 105)
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawString(30, 88, "Versão conceitual para a PoC. Validação numérica automatizada reduz risco, mas não substitui revisão epidemiológica humana.")
    c.drawRightString(PAGE_W - 30, 88, "Indicium HealthCare SRAG PoC | v2")

    c.showPage()
    c.save()
    print(OUT)


if __name__ == "__main__":
    main()
