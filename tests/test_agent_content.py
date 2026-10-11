from srag_poc.agent import _extract_text_content


def test_plain_string_is_preserved():
    report = "# Relatório Epidemiológico de SRAG\n\nTexto do relatório."
    assert _extract_text_content(report) == report


def test_gemini_text_block_extracts_markdown_not_envelope():
    content = [
        {
            "type": "text",
            "text": "# Relatório Epidemiológico de SRAG\n\n## Período analisado",
            "extras": {"signature": "SEGREDO-QUE-NAO-DEVE-IR-PARA-O-RELATORIO"},
        }
    ]
    extracted = _extract_text_content(content)
    assert extracted.startswith("# Relatório Epidemiológico de SRAG")
    assert "SEGREDO-QUE-NAO-DEVE-IR-PARA-O-RELATORIO" not in extracted
    assert '"type": "text"' not in extracted


def test_multiple_text_blocks_are_joined_in_order():
    content = [
        {"type": "text", "text": "# Relatório Epidemiológico de SRAG"},
        {"type": "text", "text": "## Período analisado"},
    ]
    assert _extract_text_content(content) == (
        "# Relatório Epidemiológico de SRAG\n## Período analisado"
    )


def test_non_text_blocks_are_ignored():
    content = [
        {"type": "image", "url": "https://example.invalid/image.png"},
        {"type": "text", "text": "# Relatório Epidemiológico de SRAG"},
        {"type": "tool_use", "name": "tool", "input": {"x": 1}},
    ]
    assert _extract_text_content(content) == "# Relatório Epidemiológico de SRAG"


def test_nested_content_dict_is_supported():
    content = {"content": [{"type": "text", "text": "Relatório"}]}
    assert _extract_text_content(content) == "Relatório"


def test_unrecognized_structured_content_returns_empty_text():
    assert _extract_text_content({"extras": {"signature": "metadata"}}) == ""
