"""Busca contextual de notícias institucionais sobre SRAG, com fallback direto.

A busca por mecanismos externos é útil, mas não é a única fonte: quando DDGS
falha ou retorna poucos resultados, consultamos páginas públicas institucionais.
Resultados sem URL institucional elegível, sem relevância respiratória ou sem
data verificável no fallback não são apresentados como notícias recentes.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
import io
import re
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .config import ALLOWED_NEWS_DOMAINS, MAX_NEWS_RESULTS, NEWS_TIME_LIMIT

NATIONAL_QUERIES = (
    'SRAG Brasil boletim epidemiológico Ministério da Saúde site:gov.br/saude',
    'InfoGripe SRAG Brasil cenário nacional site:fiocruz.br',
    'Síndrome Respiratória Aguda Grave Brasil vigilância epidemiológica site:gov.br OR site:fiocruz.br',
)

# Páginas públicas institucionais usadas como fallback quando buscadores falham.
# As páginas são lidas em tempo de execução; artigos e datas não são inventados
# nem congelados no código.
# Página oficial que lista o informe semanal mais recente do Ministério da Saúde.
# Deve ser consultada em toda execução, mesmo quando o buscador já retornou
# MAX_NEWS_RESULTS snippets sem metadados de publicação confiáveis.
MINISTRY_WEEKLY_REPORTS_PAGE = (
    "https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/c/covid-19/"
    "atualizacao-de-casos/atualizacao-de-casos"
)

INSTITUTIONAL_LISTING_PAGES = (
    MINISTRY_WEEKLY_REPORTS_PAGE,
    "https://www.gov.br/saude/pt-br/assuntos/noticias-ms",
    "https://www.gov.br/saude/pt-br/assuntos/noticias-ms?b_start:int=30",
    "https://www.gov.br/saude/pt-br/assuntos/noticias-ms?b_start:int=60",
    "https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/g/gripe-influenza/notas-tecnicas/notas-tecnicas",
    "https://agencia.fiocruz.br/",
    "https://fiocruz.br/",
)

NATIONAL_TERMS = (
    "brasil", "nacional", "infogripe", "ministério da saúde",
    "boletim epidemiológico", "semana epidemiológica", "sivep-gripe",
)
LOCAL_ONLY_TERMS = (
    "prefeitura municipal", "secretaria municipal", "boletim municipal", "prefeitura de ",
)
STRONG_NATIONAL_TERMS = (
    "infogripe", "ministério da saúde", "nacional", "semana epidemiológica",
    "sivep-gripe", "boletim nacional", "brasil",
)
RELEVANCE_TERMS = (
    "srag", "síndrome respiratória aguda grave", "infogripe", "influenza",
    "vírus respiratórios", "virus respiratorios", "síndrome gripal",
    "vírus sincicial respiratório", "virus sincicial respiratorio", "vsr",
    "bronquiolite", "metapneumovírus", "metapneumovirus", "covid-19",
    "sars-cov-2", "coronavírus", "coronavirus", "gripe",
)

# Janela própria para fallback direto: a página institucional pode não aplicar
# filtros de recência como um mecanismo de busca. Sem data verificável, o item
# não é promovido como notícia recente.
MAX_DIRECT_NEWS_AGE_DAYS = 60
HTTP_TIMEOUT_SECONDS = 6
MAX_RESPONSE_BYTES = 3_000_000

# NEWS_LATENCY_PATCH_V1: limit search-engine fan-out and overlap I/O-bound fetches.
DDGS_TIMEOUT_SECONDS = 4
DDGS_BACKEND_ORDER = "duckduckgo,yahoo"
MAX_INSTITUTIONAL_FETCH_WORKERS = 5
MAX_ARTICLE_FETCH_WORKERS = 5

_PT_MONTHS = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3,
    "abril": 4, "maio": 5, "junho": 6, "julho": 7,
    "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11,
    "dezembro": 12,
}


def allowed_url(url: str) -> bool:
    """Permite apenas HTTPS em domínios institucionais configurados."""
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        host = parsed.hostname.lower().rstrip(".")
        return any(host == domain or host.endswith(f".{domain}") for domain in ALLOWED_NEWS_DOMAINS)
    except (TypeError, ValueError):
        return False


def _is_generic_landing_page(item: dict[str, Any]) -> bool:
    """Rejeita páginas de busca/categoria que não sejam notícias individuais."""
    raw_url = str(item.get("href") or item.get("url") or "").strip()
    if not raw_url:
        return False
    try:
        path = urlparse(raw_url).path.lower().rstrip("/") or "/"
    except ValueError:
        return True
    exact_landing_paths = {"/busca-geral", "/busca", "/search", "/search-results", "/noticias"}
    if path in exact_landing_paths:
        return True
    return any(marker in path for marker in ("/tag/", "/categoria/", "/category/", "/page/"))


def _contains_term(text: str, term: str) -> bool:
    """Match words/phrases, not accidental substrings (e.g. Brasil in brasileira)."""
    phrase = term.strip().lower()
    return bool(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text.lower()))


def _is_relevant_national(item: dict[str, Any]) -> bool:
    if _is_generic_landing_page(item):
        return False
    text = f"{item.get('title', '')} {item.get('body', '')} {item.get('titulo', '')} {item.get('resumo', '')}".lower()
    if not any(_contains_term(text, term) for term in RELEVANCE_TERMS):
        return False
    has_local_signal = any(_contains_term(text, term) for term in LOCAL_ONLY_TERMS)
    has_strong_national_signal = any(_contains_term(text, term) for term in STRONG_NATIONAL_TERMS)
    # Sources in the fallback are national institutional sites; for DDGS, this
    # rule prevents a local-only story from being treated as national context.
    return not has_local_signal or has_strong_national_signal


def _score(item: dict[str, Any]) -> int:
    text = f"{item.get('title', '')} {item.get('body', '')} {item.get('titulo', '')} {item.get('resumo', '')}".lower()
    score = sum(3 for term in NATIONAL_TERMS if _contains_term(text, term))
    score += sum(2 for term in ("srag", "infogripe", "vírus sincicial respiratório", "virus sincicial respiratorio") if _contains_term(text, term))
    score -= sum(4 for term in LOCAL_ONLY_TERMS if _contains_term(text, term))
    return score


def _parse_date(value: str | None) -> date | None:
    """Interpreta datas explícitas em formatos comuns de páginas institucionais."""
    if not value:
        return None
    text = " ".join(str(value).split())
    for pattern, fmt in (
        (r"\b(\d{1,2}/\d{1,2}/\d{4})\b", "%d/%m/%Y"),
        (r"\b(\d{4}-\d{2}-\d{2})\b", "%Y-%m-%d"),
    ):
        match = re.search(pattern, text)
        if match:
            try:
                return datetime.strptime(match.group(1), fmt).date()
            except ValueError:
                pass
    match = re.search(
        r"\b(\d{1,2})\s+de\s+([A-Za-zÀ-ÿ]+)\s+de\s+(\d{4})\b",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        month = _PT_MONTHS.get(match.group(2).lower())
        if month:
            try:
                return date(int(match.group(3)), month, int(match.group(1)))
            except ValueError:
                return None
    return None


def _date_is_recent(value: str | None, *, today: date | None = None) -> bool:
    published = _parse_date(value)
    if published is None:
        return False
    current = today or date.today()
    return current - timedelta(days=MAX_DIRECT_NEWS_AGE_DAYS) <= published <= current + timedelta(days=1)


def _is_article_url(url: str) -> bool:
    if not allowed_url(url) or _is_generic_landing_page({"url": url}):
        return False
    path = urlparse(url).path.lower()
    # Prefere a página HTML do informe ao link que baixa o arquivo diretamente.
    if "@@download/file" in path:
        return False
    return any(marker in path for marker in (
        "/noticias-ms/20", "/noticia/", "/infogripe", "/notas-tecnicas/",
        "/publicacoes-tecnicas/informes/", "/informe-se-",
    ))


class _InstitutionalLinksParser(HTMLParser):
    """Extrai itens de notícias/documentos de cards HTML sem dependência extra."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.items: list[dict[str, str]] = []
        self.current: dict[str, Any] | None = None
        self.anchor_is_candidate = False
        self.anchor_title_parts: list[str] = []
        self.anchor_href: str | None = None
        self.skip_depth = 0

    @staticmethod
    def _clean(value: str) -> str:
        return " ".join(value.split())

    def _finish_item(self) -> None:
        if not self.current:
            return
        title = self._clean(self.current.get("title", ""))
        chunks = self.current.get("chunks", [])
        body = self._clean(" ".join(chunks))
        if title and body.startswith(title):
            body = body[len(title):].strip(" -|:;,.\t")
        url = self.current.get("url", "")
        if title and url:
            self.items.append({"title": title[:300], "url": url, "body": body[:1200]})
        self.current = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "time" and self.current:
            value = attributes.get("datetime")
            if value:
                self.current["date_values"].append(value)
        if tag == "a":
            href = attributes.get("href") or ""
            absolute = urljoin(self.base_url, href)
            self.anchor_is_candidate = _is_article_url(absolute)
            self.anchor_href = absolute if self.anchor_is_candidate else None
            self.anchor_title_parts = []
            if self.anchor_is_candidate:
                self._finish_item()
                self.current = {"url": absolute, "title": "", "chunks": [], "date_values": []}

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        clean = self._clean(data)
        if not clean:
            return
        if self.current is not None:
            self.current["chunks"].append(clean)
            if self.anchor_is_candidate:
                self.anchor_title_parts.append(clean)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag == "a" and self.anchor_is_candidate and self.current is not None:
            self.current["title"] = self._clean(" ".join(self.anchor_title_parts))
        if tag == "a":
            self.anchor_is_candidate = False
            self.anchor_href = None
            self.anchor_title_parts = []

    def close(self) -> None:
        super().close()
        self._finish_item()


class _AllowlistedRedirectHandler(HTTPRedirectHandler):
    """Bloqueia destino não institucional antes de seguir o redirecionamento."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        if not allowed_url(target):
            raise HTTPError(
                req.full_url,
                code,
                "Redirecionamento para domínio não permitido",
                headers,
                fp,
            )
        return super().redirect_request(req, fp, code, msg, headers, target)


def _open_allowlisted(request: Request, timeout: int):
    """Abre URL institucional com validação prévia de cada redirecionamento."""
    if not allowed_url(request.full_url):
        raise ValueError("URL fora da allowlist institucional.")
    opener = build_opener(_AllowlistedRedirectHandler())
    return opener.open(request, timeout=timeout)


def _fetch_html(url: str) -> str:
    if not allowed_url(url):
        raise ValueError("URL fora da allowlist institucional.")
    request = Request(
        url,
        headers={
            "User-Agent": "IndiciumHealthcareSRAG/2.0 (+institutional public-health context)",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5",
        },
    )
    with _open_allowlisted(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        final_url = response.geturl()
        if not allowed_url(final_url):
            raise ValueError("Redirecionamento para domínio não permitido")
        payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        payload = payload[:MAX_RESPONSE_BYTES]
    # Os portais oficiais normalmente informam charset no header, mas UTF-8 é
    # o padrão esperado quando ele estiver ausente ou inválido.
    try:
        charset = response.headers.get_content_charset() or "utf-8"
    except Exception:
        charset = "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")



# NEWS_CONTENT_EXTRACTION_V1
# Limites defensivos para extração de conteúdo de páginas e boletins PDF.
MAX_ARTICLE_TEXT_CHARS = 9000
MAX_PDF_PAGES = 10
MIN_ARTICLE_CONTENT_CHARS = 240
MAX_EVIDENCE_PASSAGES = 6
MAX_EVIDENCE_PASSAGE_CHARS = 520

_PDF_URL_RE = re.compile(r"(?:\.pdf(?:/|$)|@@download/file)", re.IGNORECASE)
_EVIDENCE_TERMS = (
    "srag", "respirat", "infogripe", "influenza", "rinovírus", "rinovirus",
    "metapneum", "sars-cov-2", "covid-19", "vírus", "virus", "bronquiolite",
    "aument", "crescimento", "estabil", "oscila", "redução", "reducao",
    "queda", "alerta", "risco", "crianças", "criancas", "adolescentes",
    "internação", "internacao", "óbitos", "obitos", "mortalidade",
    "alagoas", "roraima", "sergipe", "unidades federativas",
)


def _looks_like_pdf_url(url: str) -> bool:
    try:
        return bool(_PDF_URL_RE.search(urlparse(url).path.lower()))
    except (TypeError, ValueError):
        return False


class _ArticleContentParser(HTMLParser):
# Extrai blocos textuais de artigo e links para anexos PDF institucionais.

    SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form"}
    BLOCK_TAGS = {"h1", "h2", "h3", "h4", "p", "li", "blockquote", "dd", "dt"}

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.skip_depth = 0
        self.current_block: str | None = None
        self.current_parts: list[str] = []
        self.paragraphs: list[str] = []
        self.pdf_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return

        if tag == "a":
            href = attributes.get("href") or ""
            absolute = urljoin(self.base_url, href)
            if _looks_like_pdf_url(absolute) and allowed_url(absolute) and absolute not in self.pdf_links:
                self.pdf_links.append(absolute)

        if self.current_block is None and tag in self.BLOCK_TAGS:
            self.current_block = tag
            self.current_parts = []

    def handle_data(self, data: str) -> None:
        if not self.skip_depth and self.current_block is not None:
            cleaned = " ".join(data.split())
            if cleaned:
                self.current_parts.append(cleaned)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if self.current_block == tag:
            paragraph = " ".join(self.current_parts).strip()
            if paragraph and (not self.paragraphs or self.paragraphs[-1] != paragraph):
                self.paragraphs.append(paragraph)
            self.current_block = None
            self.current_parts = []

    @property
    def text(self) -> str:
        return "\n".join(self.paragraphs).strip()


def _fetch_pdf_bytes(url: str) -> tuple[bytes, str]:
# Baixa PDF somente de domínio institucional permitido e com tamanho limitado.
    if not allowed_url(url):
        raise ValueError("URL do PDF fora da allowlist institucional.")
    request = Request(
        url,
        headers={
            "User-Agent": "IndiciumHealthcareSRAG/2.0 (+institutional public-health context)",
            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.5",
        },
    )
    with _open_allowlisted(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        final_url = response.geturl()
        payload = response.read(MAX_RESPONSE_BYTES + 1)
    if not allowed_url(final_url):
        raise ValueError("Redirecionamento do PDF para domínio não permitido.")
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("PDF excede o limite de tamanho permitido.")
    if not payload.lstrip().startswith(b"%PDF"):
        raise ValueError("O recurso institucional não retornou um arquivo PDF válido.")
    return payload, final_url


# NEWS_PDF_LINEWRAP_NORMALIZATION_V1

def _normalize_extracted_text(text: str) -> str:
    """Join soft line wraps from HTML/PDF extraction while preserving paragraphs."""
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    paragraphs: list[str] = []
    for paragraph in re.split(r"\n\s*\n+", value):
        # PDF extraction sometimes hyphenates a word at the end of a visual line.
        paragraph = re.sub(r"(?<=\w)-[ \t]*\n[ \t]*(?=\w)", "", paragraph)
        # A single newline is normally a visual line break, not a sentence boundary.
        paragraph = re.sub(r"[ \t]*\n[ \t]*", " ", paragraph)
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if paragraph:
            paragraphs.append(paragraph)
    return "\n\n".join(paragraphs)


def _extract_pdf_text(payload: bytes) -> str:
    # Extract a bounded number of pages; never execute PDF content.
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(payload), strict=False)
    pages: list[str] = []
    page_count = min(len(reader.pages), MAX_PDF_PAGES)
    total_chars = 0
    for index in range(page_count):
        try:
            page_text = reader.pages[index].extract_text() or ""
        except Exception:
            page_text = ""
        if page_text.strip():
            pages.append(page_text.strip())
            total_chars += len(page_text)
        if total_chars >= MAX_ARTICLE_TEXT_CHARS:
            break
    text = _normalize_extracted_text("\n\n".join(pages))
    return text[:MAX_ARTICLE_TEXT_CHARS]


def _select_relevant_passages(text: str) -> list[str]:
    # Keep literal evidence passages; normalize PDF visual line breaks first.
    normalized_text = _normalize_extracted_text(text)
    units: list[str] = []
    for paragraph in re.split(r"\n{2,}", normalized_text):
        cleaned = re.sub(r"\s+", " ", paragraph).strip()
        if not cleaned:
            continue
        # Split sentence-like units only after line wrapping has been resolved.
        for sentence in re.split(
            r"(?<=[.!?])\s+(?=[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ0-9])", cleaned
        ):
            sentence = sentence.strip()
            if len(sentence) >= 45:
                units.append(sentence)

    selected: list[str] = []
    seen: set[str] = set()
    for unit in units:
        lower = unit.lower()
        if any(term in lower for term in _EVIDENCE_TERMS):
            normalized = re.sub(r"\s+", " ", unit).casefold()
            if normalized not in seen:
                selected.append(unit[:MAX_EVIDENCE_PASSAGE_CHARS])
                seen.add(normalized)
        if len(selected) >= MAX_EVIDENCE_PASSAGES:
            break

    if not selected:
        selected = [unit[:MAX_EVIDENCE_PASSAGE_CHARS] for unit in units[:3]]
    return selected

def _extract_article_content(url: str) -> tuple[str, str, str]:
# Retorna (texto, método, URL de conteúdo) para uma página ou relatório oficial.
    if not allowed_url(url):
        raise ValueError("URL do artigo fora da allowlist institucional.")

    path = urlparse(url).path.lower()
    if path.endswith(".pdf") or "@@download/file" in path:
        payload, final_url = _fetch_pdf_bytes(url)
        text = _extract_pdf_text(payload)
        if len(text.strip()) < MIN_ARTICLE_CONTENT_CHARS:
            raise ValueError("O PDF não contém camada de texto suficiente para análise.")
        return text[:MAX_ARTICLE_TEXT_CHARS], "pdf_text", final_url

    html = _fetch_html(url)
    parser = _ArticleContentParser(url)
    parser.feed(html)
    parser.close()
    page_text = parser.text

    # A página de visualização de boletins do gov.br costuma ser uma capa HTML
    # com link de download. Priorize o anexo PDF nesses casos.
    is_pdf_view = ".pdf/view" in path or "/pdf/" in path
    if not is_pdf_view and len(page_text) >= MIN_ARTICLE_CONTENT_CHARS:
        return page_text[:MAX_ARTICLE_TEXT_CHARS], "html_article", url

    pdf_errors: list[str] = []
    for pdf_url in parser.pdf_links[:3]:
        try:
            payload, final_url = _fetch_pdf_bytes(pdf_url)
            text = _extract_pdf_text(payload)
            if len(text.strip()) >= MIN_ARTICLE_CONTENT_CHARS:
                return text[:MAX_ARTICLE_TEXT_CHARS], "pdf_text", final_url
        except Exception as exc:
            pdf_errors.append(type(exc).__name__)

    if len(page_text) >= MIN_ARTICLE_CONTENT_CHARS:
        return page_text[:MAX_ARTICLE_TEXT_CHARS], "html_article", url

    if pdf_errors:
        raise ValueError("Não foi possível extrair o conteúdo dos anexos PDF institucionais.")
    raise ValueError("A página não expôs conteúdo substantivo extraível.")


def _enrich_news_item(item: dict[str, Any]) -> dict[str, Any]:
# Enriquece um resultado com texto de fonte real sem falhar toda a busca.
    enriched = dict(item)
    original_summary = str(enriched.get("resumo") or "")
    enriched.setdefault("resumo_busca", original_summary)
    url = str(enriched.get("url") or "")

    try:
        text, method, content_url = _extract_article_content(url)
        if len(text.strip()) < MIN_ARTICLE_CONTENT_CHARS:
            raise ValueError("Conteúdo extraído curto demais.")
        passages = _select_relevant_passages(text)
        enriched.update({
            "conteudo_extraido": True,
            "status_conteudo": "extraido",
            "metodo_extracao": method,
            "url_conteudo": content_url,
            "texto_conteudo": text[:MAX_ARTICLE_TEXT_CHARS],
            "trechos_relevantes": passages,
        })
        if passages:
            enriched["resumo"] = " ".join(passages[:3])[:1200]
        else:
            enriched["resumo"] = text[:1200]
    except Exception as exc:
        # A busca continua disponível, mas um snippet não é rotulado como texto do artigo.
        enriched.update({
            "conteudo_extraido": False,
            "status_conteudo": "somente_snippet",
            "metodo_extracao": "snippet_only",
            "url_conteudo": url,
            "texto_conteudo": "",
            "trechos_relevantes": [],
            "erro_extracao": type(exc).__name__,
            "resumo": original_summary,
        })
    return enriched



def _direct_institutional_results() -> tuple[list[dict[str, Any]], list[str]]:
    """Consulta portais institucionais em paralelo, mantendo falha isolada por página."""
    collected: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    today = date.today()

    def fetch_listing(page_url: str) -> tuple[str, str | None, Exception | None]:
        try:
            return page_url, _fetch_html(page_url), None
        except Exception as exc:  # uma página inacessível não bloqueia as demais
            return page_url, None, exc

    worker_count = min(MAX_INSTITUTIONAL_FETCH_WORKERS, max(1, len(INSTITUTIONAL_LISTING_PAGES)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        for page_url, html, error in executor.map(fetch_listing, INSTITUTIONAL_LISTING_PAGES):
            if error is not None:
                errors.append(f"{urlparse(page_url).hostname}:{type(error).__name__}")
                continue
            try:
                parser = _InstitutionalLinksParser(page_url)
                parser.feed(html or "")
                parser.close()
                for raw_item in parser.items:
                    item_for_filter = {
                        "title": raw_item["title"],
                        "body": raw_item["body"],
                        "url": raw_item["url"],
                    }
                    if not _is_relevant_national(item_for_filter):
                        continue
                    if not allowed_url(raw_item["url"]):
                        continue
                    published = _parse_date(raw_item["body"])
                    if published is None or not _date_is_recent(published.isoformat(), today=today):
                        continue
                    key = raw_item["url"].split("#", 1)[0].rstrip("/")
                    if key in collected:
                        continue
                    collected[key] = {
                        "titulo": raw_item["title"],
                        "url": raw_item["url"],
                        "dominio": urlparse(raw_item["url"]).hostname,
                        "publicado_em": published.strftime("%d/%m/%Y"),
                        "resumo": raw_item["body"][:600] or "Resumo não informado no card institucional.",
                        "_score": _score(item_for_filter),
                        "_published_date": published,
                    }
            except Exception as exc:  # parsing de uma página não cancela as demais
                errors.append(f"{urlparse(page_url).hostname}:{type(exc).__name__}")

    ordered = sorted(
        collected.values(),
        key=lambda item: (item["_published_date"], item["_score"]),
        reverse=True,
    )
    for item in ordered:
        item.pop("_score", None)
        item.pop("_published_date", None)
    return ordered[:MAX_NEWS_RESULTS], errors

def search_national_news(query: str = "SRAG Brasil") -> dict[str, Any]:
    """Busca notícias institucionais nacionais; indisponibilidade não é evidência epidemiológica."""
    try:
        from ddgs import DDGS
    except ImportError:
        DDGS = None  # fallback direto segue disponível mesmo sem ddgs

    requested = " ".join(str(query).split())[:120]
    collected: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    search_queries_attempted = 0
    search_queries_succeeded = 0
    if DDGS is not None:
        try:
            client = DDGS(timeout=DDGS_TIMEOUT_SECONDS)
            for base_query in NATIONAL_QUERIES:
                search_query = f"{base_query} {requested}".strip()
                try:
                    search_queries_attempted += 1
                    results = client.text(
                        search_query,
                        region="br-pt",
                        timelimit=NEWS_TIME_LIMIT,
                        max_results=min(5, max(1, int(MAX_NEWS_RESULTS))),
                        backend=DDGS_BACKEND_ORDER,
                    )
                    search_queries_succeeded += 1
                    for result in results or []:
                        url = str(result.get("href") or result.get("url") or "").strip()
                        if not allowed_url(url) or not _is_relevant_national(result):
                            continue
                        key = url.split("#", 1)[0].rstrip("/")
                        if key in collected:
                            continue
                        collected[key] = {
                            "titulo": str(result.get("title") or "Título não informado")[:300],
                            "url": url,
                            "dominio": urlparse(url).hostname,
                            "publicado_em": str(result.get("date") or "").strip() or None,
                            "resumo": str(result.get("body") or "Resumo não informado")[:600],
                            "_score": _score(result),
                            "_source": "ddgs",
                        }
                except Exception as exc:  # uma consulta falhar não cancela as demais
                    errors.append(f"ddgs:{type(exc).__name__}")
        except Exception as exc:
            errors.append(f"ddgs_init:{type(exc).__name__}")
    else:
        errors.append("ddgs:ImportError")

    # Consulte sempre as páginas institucionais. Os buscadores podem preencher
    # o limite com snippets sem data estruturada ou com links que não são o
    # informe epidemiológico oficial mais recente.
    direct_results, direct_errors = _direct_institutional_results()
    for result in direct_results:
        key = result["url"].split("#", 1)[0].rstrip("/")
        direct_item = {
            **result,
            "_score": _score({"title": result["titulo"], "body": result["resumo"]}),
            "_source": "institutional_page",
        }
        # A extração direta da página oficial, com data visível, tem precedência
        # sobre um snippet do buscador para a mesma URL.
        existing = collected.get(key)
        if existing is None or existing.get("_source") != "institutional_page":
            collected[key] = direct_item
    errors.extend(direct_errors)

    def publication_sort_key(item: dict[str, Any]) -> tuple[int, date, int]:
        published = _parse_date(str(item.get("publicado_em") or ""))
        verified_institutional_page = 1 if item.get("_source") == "institutional_page" else 0
        # Primeiro, fontes recuperadas diretamente de páginas institucionais;
        # dentro desse grupo, as publicações mais recentes vêm primeiro.
        return (verified_institutional_page, published or date.min, int(item.get("_score", 0)))

    ordered = sorted(collected.values(), key=publication_sort_key, reverse=True)
    selected = ordered[:MAX_NEWS_RESULTS]
    if selected:
        with ThreadPoolExecutor(max_workers=min(MAX_ARTICLE_FETCH_WORKERS, len(selected))) as executor:
            selected = list(executor.map(_enrich_news_item, selected))
    sources_used = sorted({item.get("_source", "ddgs") for item in selected})
    for item in selected:
        item.pop("_score", None)
        item.pop("_source", None)

    if selected:
        return {
            "status": "success",
            "escopo": "Brasil/nacional; domínios institucionais permitidos",
            "queries": list(NATIONAL_QUERIES),
            "fontes_de_busca": sources_used,
            "consultas_com_erro": errors,
            "results": selected,
        }
    search_failed_completely = DDGS is None or (
        search_queries_attempted > 0 and search_queries_succeeded == 0
    )
    direct_failed_completely = bool(INSTITUTIONAL_LISTING_PAGES) and (
        len(direct_errors) == len(INSTITUTIONAL_LISTING_PAGES)
    )
    if search_failed_completely and direct_failed_completely:
        message = "Buscadores indisponíveis e portais institucionais inacessíveis; nenhum cenário epidemiológico foi inferido."
        status = "error"
    else:
        message = "Nenhuma notícia institucional nacional relevante, com URL validada e data verificável recente, foi localizada. Isso não indica ausência de surtos ou ausência de risco."
        status = "no_results"
    return {
        "status": status,
        "message": message,
        "consultas_com_erro": errors,
        "results": [],
    }
