from __future__ import annotations

from jobagent.textutil import html_to_text, truncate


def test_strips_plain_html():
    assert html_to_text("<p>Train <b>RL</b> agents</p>") == "Train RL agents"


def test_strips_entity_escaped_html():
    """Greenhouse returns HTML that is itself escaped — unescape first, or the
    tags survive into the description."""
    out = html_to_text("&lt;p&gt;Train RL agents&lt;/p&gt;")
    assert out == "Train RL agents"
    assert "<" not in out and "&lt;" not in out


def test_salary_range_survives_span_markup():
    """The exact shape Greenhouse uses for pay ranges."""
    raw = (
        '&lt;div class="pay-range"&gt;&lt;span&gt;$275,000&lt;/span&gt;'
        '&lt;span class="divider"&gt;&amp;mdash;&lt;/span&gt;'
        '&lt;span&gt;$380,000 USD&lt;/span&gt;&lt;/div&gt;'
    )
    out = html_to_text(raw)
    assert "$275,000" in out and "$380,000" in out
    assert "—" in out and "span" not in out


def test_drops_script_and_style_content():
    out = html_to_text("<style>.a{color:red}</style><p>Hi</p><script>x=1</script>")
    assert out == "Hi"


def test_block_tags_become_line_breaks():
    assert html_to_text("<li>One</li><li>Two</li>") == "One\nTwo"


def test_truncate_cuts_on_a_word_boundary():
    assert truncate("alpha beta gamma delta", 14).endswith("…")
    assert "gamma" not in truncate("alpha beta gamma delta", 14)


def test_truncate_leaves_short_text_alone():
    assert truncate("short", 100) == "short"
