from datetime import date
import sys
from types import SimpleNamespace

import pytest

from srag_poc import news


class FakeResponse:
    def __init__(self, body: bytes, url: str):
        self._body = body
        self._url = url
        self.headers = FakeHeaders()

    def read(self, limit=-1):
        return self._body[:limit]

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeHeaders:
    def get_content_charset(self):
        return "utf-8"


def test_allowed_url_rejects_non_https_and_untrusted_domain():
    assert not news.allowed_url("http://www.gov.br/saude/noticia")
    assert not news.allowed_url("https://fake-gov.br/noticia")
    assert news.allowed_url("https://www.gov.br/saude/noticia")


def test_generic_landing_pages_are_rejected():
    assert news._is_generic_landing_page({"url": "https://agencia.fiocruz.br/busca-geral"})
    assert not news._is_generic_landing_page({"url": "https://agencia.fiocruz.br/noticia/2026/10/infogripe"})


def test_national_relevance_accepts_respiratory_topic_and_rejects_irrelevant():
    assert news._is_relevant_national({"title": "InfoGripe: SRAG no Brasil", "body": "Boletim nacional"})
    assert not news._is_relevant_national({"title": "Resultado do campeonato", "body": "Esporte"})


def test_local_only_story_is_rejected():
    assert not news._is_relevant_national({
        "title": "SRAG em cidade brasileira",
        "body": "Prefeitura municipal publica boletim municipal",
    })


def test_parse_date_portuguese_and_iso():
    assert news._parse_date("publicado em 08/10/2026") == date(2026, 10, 8)
    assert news._parse_date("Publicado em 8 de outubro de 2026") == date(2026, 10, 8)
    assert news._parse_date("2026-10-08") == date(2026, 10, 8)
    assert news._parse_date("sem data publicada") is None


def test_direct_page_parser_extracts_institutional_article_and_summary():
    html = '''
    <html><body>
      <article>
        <h2><a href="https://www.gov.br/saude/pt-br/assuntos/noticias-ms/2026/outubro/infogripe-srag">InfoGripe: SRAG no Brasil</a></h2>
        <p>Boletim nacional aponta vírus respiratórios e aumento de casos.</p>
        <span>Publicado em 08/10/2026 10h00</span>
      </article>
    </body></html>
    '''
    parser = news._InstitutionalLinksParser("https://www.gov.br/saude/pt-br/assuntos/noticias-ms")
    parser.feed(html)
    parser.close()
    assert len(parser.items) == 1
    assert parser.items[0]["title"] == "InfoGripe: SRAG no Brasil"
    assert "Boletim nacional" in parser.items[0]["body"]
    assert news._parse_date(parser.items[0]["body"]) == date(2026, 10, 8)


def test_fallback_fetches_official_listing_and_returns_recent_relevant_item(monkeypatch):
    html = '''<html><body><article>
    <h2><a href="https://www.gov.br/saude/pt-br/assuntos/noticias-ms/2026/outubro/infogripe-srag">InfoGripe: SRAG no Brasil</a></h2>
    <p>Boletim nacional sobre vírus respiratórios no Brasil.</p>
    <span>Publicado em 08/10/2026 10h00</span>
    </article></body></html>'''

    def fake_fetch(url):
        return html

    monkeypatch.setattr(news, "_fetch_html", fake_fetch)
    monkeypatch.setattr(news, "INSTITUTIONAL_LISTING_PAGES", ("https://www.gov.br/saude/pt-br/assuntos/noticias-ms",))
    monkeypatch.setattr(news, "date", FakeTodayDate)

    results, errors = news._direct_institutional_results()
    assert errors == []
    assert len(results) == 1
    assert results[0]["titulo"] == "InfoGripe: SRAG no Brasil"
    assert results[0]["publicado_em"] == "08/10/2026"


class FakeTodayDate:
    @staticmethod
    def today():
        return date(2026, 10, 9)


def test_search_falls_back_when_ddgs_fails(monkeypatch):
    html = '''<article>
    <h2><a href="https://www.gov.br/saude/pt-br/assuntos/noticias-ms/2026/outubro/infogripe-srag">InfoGripe: SRAG no Brasil</a></h2>
    <p>Boletim nacional sobre vírus respiratórios no Brasil.</p>
    <span>Publicado em 08/10/2026 10h00</span>
    </article>'''

    class FakeDDGS:
        def text(self, *args, **kwargs):
            raise RuntimeError("search engine blocked")

    monkeypatch.setattr(news, "_fetch_html", lambda url: html)
    monkeypatch.setattr(news, "INSTITUTIONAL_LISTING_PAGES", ("https://www.gov.br/saude/pt-br/assuntos/noticias-ms",))
    monkeypatch.setattr(news, "date", FakeTodayDate)
    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeDDGS))

    result = news.search_national_news("SRAG Brasil")
    assert result["status"] == "success"
    assert result["results"][0]["titulo"] == "InfoGripe: SRAG no Brasil"
    assert "institutional_page" in result["fontes_de_busca"]


def test_no_results_is_explicit_and_never_claims_no_epidemic(monkeypatch):
    class EmptyDDGS:
        def text(self, *args, **kwargs):
            return []

    monkeypatch.setattr(news, "_fetch_html", lambda url: "<html><body>Sem notícias relevantes</body></html>")
    monkeypatch.setattr(news, "INSTITUTIONAL_LISTING_PAGES", ("https://www.gov.br/saude/pt-br/assuntos/noticias-ms",))
    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=EmptyDDGS))

    result = news.search_national_news("SRAG Brasil")
    assert result["status"] == "no_results"
    assert result["results"] == []
    assert "não indica ausência" in result["message"]


def test_latest_ministry_weekly_listing_is_in_institutional_fallback():
    assert news.INSTITUTIONAL_LISTING_PAGES[0] == news.MINISTRY_WEEKLY_REPORTS_PAGE
    assert news._is_article_url(
        "https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/c/covid-19/"
        "atualizacao-de-casos/informe-se-39-de-2026.pdf/view"
    )
    assert not news._is_article_url(
        "https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/c/covid-19/"
        "atualizacao-de-casos/informe-se-39-de-2026.pdf/@@download/file"
    )


def test_official_weekly_report_is_parsed_with_publication_date(monkeypatch):
    official_url = (
        "https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/c/covid-19/"
        "atualizacao-de-casos/informe-se-39-de-2026.pdf/view"
    )
    html = f'''<html><body><article>
    <h2><a href="{official_url}">Informe SE 39 de 2026 | Vigilância das Síndromes Gripais, SRAG, Influenza e Covid-19</a></h2>
    <p>Secretaria de Vigilância em Saúde e Ambiente. Publicado em 08/10/2026 11h26.</p>
    <a href="{official_url.replace('/view', '/@@download/file')}">Baixar arquivo</a>
    </article></body></html>'''
    monkeypatch.setattr(news, "_fetch_html", lambda url: html)
    monkeypatch.setattr(news, "INSTITUTIONAL_LISTING_PAGES", (news.MINISTRY_WEEKLY_REPORTS_PAGE,))
    monkeypatch.setattr(news, "date", FakeTodayDate)

    results, errors = news._direct_institutional_results()
    assert errors == []
    assert results
    report = next(item for item in results if item["url"] == official_url)
    assert "Informe SE 39 de 2026" in report["titulo"]
    assert report["publicado_em"] == "08/10/2026"


def test_official_report_is_consulted_even_when_search_fills_result_limit(monkeypatch):
    official_url = (
        "https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/c/covid-19/"
        "atualizacao-de-casos/informe-se-39-de-2026.pdf/view"
    )

    class FullDDGS:
        def __init__(self):
            self.n = 0

        def text(self, *args, **kwargs):
            result = {
                "title": f"InfoGripe SRAG Brasil boletim nacional {self.n}",
                "href": f"https://agencia.fiocruz.br/noticia/2026/10/infogripe-srag-{self.n}",
                "date": "10/10/2026",
                "body": "Boletim nacional sobre SRAG e vírus respiratórios no Brasil.",
            }
            self.n += 1
            return [result]

    official = {
        "titulo": "Informe SE 39 de 2026 | Vigilância nacional de SRAG e vírus respiratórios",
        "url": official_url,
        "dominio": "www.gov.br",
        "publicado_em": "08/10/2026",
        "resumo": "Boletim nacional sobre tendência de SRAG no Brasil.",
    }
    calls = {"count": 0}

    def fake_direct():
        calls["count"] += 1
        return [official], []

    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FullDDGS))
    monkeypatch.setattr(news, "_direct_institutional_results", fake_direct)
    monkeypatch.setattr(news, "MAX_NEWS_RESULTS", 5)

    result = news.search_national_news("SRAG Brasil")
    assert calls["count"] == 1
    assert result["status"] == "success"
    assert len(result["results"]) == 4
    assert result["results"][0]["url"] == official_url
    assert "institutional_page" in result["fontes_de_busca"]
