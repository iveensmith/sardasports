"""The blog's HTML allow-list: what survives, what is removed, and that it settles."""

from __future__ import annotations

import pytest

from app.services.html_sanitize import html_to_text, sanitize_html


@pytest.mark.parametrize(
    ("dirty", "clean"),
    [
        ("<p>Hello <b>world</b></p>", "<p>Hello <b>world</b></p>"),
        ('<p onclick="x()">hi</p>', "<p>hi</p>"),
        ("<p>a<script>alert(1)</script>b</p>", "<p>ab</p>"),
        ("<style>p{color:red}</style><p>y</p>", "<p>y</p>"),
        ('<a href="javascript:alert(1)">x</a>', "<a>x</a>"),
        ('<a href=" JaVaScRiPt:alert(1)">x</a>', "<a>x</a>"),
        ('<a href="//evil.example/x">x</a>', "<a>x</a>"),
        (
            '<a href="https://e.com" target="_blank">ok</a>',
            '<a href="https://e.com" target="_blank" rel="noopener noreferrer">ok</a>',
        ),
        ('<img src="data:image/svg+xml;base64,AAA">', ""),
        ('<img src="https://e.com/a.png" onerror="x()">', '<img src="https://e.com/a.png">'),
        ("<iframe src='https://evil'></iframe>after", "after"),
        ("<input type=text><p>kept</p>", "<p>kept</p>"),
        ("<svg onload=alert(1)><circle/></svg>ok", "ok"),
        ("<font color=red>old</font>", "old"),
        ("<p>unclosed <b>bold", "<p>unclosed <b>bold</b></p>"),
        ("</div>stray<p>x</p>", "stray<p>x</p>"),
        ("1 < 2 & 3 > 2", "1 &lt; 2 &amp; 3 &gt; 2"),
        ("<!-- note --><p>x</p>", "<p>x</p>"),
        (
            '<p style="color:red;background:url(javascript:x);position:fixed;font-size:14px">x</p>',
            '<p style="color: red; font-size: 14px">x</p>',
        ),
        (
            '<p style="color: rgb(255, 0, 0)">x</p>',
            '<p style="color: rgb(255, 0, 0)">x</p>',
        ),
        ('<p style="width: expression(alert(1))">x</p>', "<p>x</p>"),
    ],
)
def test_the_allow_list(dirty, clean):
    assert sanitize_html(dirty) == clean


def test_running_it_again_changes_nothing():
    dirty = '<div onclick="x"><p style="color:red">a <i>b</i><script>z</script></p><br/></div>'
    once = sanitize_html(dirty)

    assert sanitize_html(once) == once


def test_an_unterminated_script_cannot_smuggle_what_follows():
    out = sanitize_html("<p>before</p><script>alert(1)<p>after</p>")

    assert "alert" not in out and "script" not in out


def test_text_extraction_skips_code_and_separates_blocks():
    html = "<h1>Title</h1><p>One <b>two</b></p><script>x()</script><p>three</p>"

    assert html_to_text(html) == "Title One two three"
