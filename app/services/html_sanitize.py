"""An allow-list HTML sanitiser for blog posts, written against the standard library.

The administrator writes posts in a rich-text editor, which produces HTML. That HTML is shown to
every visitor, so it is never trusted as it arrives (the editor runs in the browser and its output
can be edited by hand on the way): this rebuilds it from scratch, keeping only tags, attributes and
inline styles from a short list, and dropping everything else. It runs when a post is saved, so
what is stored is what is served.

What it does:
- Tags not on the list are removed and their text kept (`<font>`, `<center>`); tags that can run
  code or load another page (`script`, `style`, `iframe`, `object`, `form`, ...) are removed
  together with everything inside them.
- Attributes not on the list are removed, so `onclick`, `onerror` and the rest cannot survive.
- A link or image address must be http(s), a mail or phone link, or relative to this site;
  `javascript:` and `data:` are dropped.
- Inline styles are reduced to a few harmless presentation properties, with values restricted to
  plain words, numbers, colours and units (no `url()`, no `expression()`).
- Links that open a new tab get `rel="noopener noreferrer"`.
- The output is always balanced: unclosed tags are closed and stray end tags are ignored.
"""

from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit

ALLOWED_TAGS = frozenset(
    {
        "a", "abbr", "b", "blockquote", "br", "caption", "cite", "code", "col", "colgroup",
        "dd", "del", "div", "dl", "dt", "em", "figcaption", "figure", "h1", "h2", "h3", "h4",
        "h5", "h6", "hr", "i", "img", "li", "mark", "ol", "p", "pre", "s", "small", "span",
        "strike", "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr",
        "u", "ul",
    }
)  # fmt: skip

VOID_TAGS = frozenset({"br", "col", "hr", "img"})
# Tags that are removed and have no end tag, so there is no content to skip.
_VOID_DROPPED = frozenset(
    {"area", "base", "embed", "frame", "input", "link", "meta", "param", "source", "track", "wbr"}
)

# Removed together with their contents.
DROP_WITH_CONTENT = frozenset(
    {
        "script", "style", "iframe", "frame", "frameset", "object", "embed", "applet", "noscript",
        "template", "svg", "math", "form", "input", "button", "select", "option", "textarea",
        "link", "meta", "base", "title", "head", "audio", "video", "source", "canvas",
    }
)  # fmt: skip

GLOBAL_ATTRIBUTES = frozenset({"class", "dir", "id", "lang", "style", "title"})
TAG_ATTRIBUTES: dict[str, frozenset[str]] = {
    "a": frozenset({"href", "name", "rel", "target"}),
    "img": frozenset({"alt", "height", "src", "width"}),
    "ol": frozenset({"start", "type"}),
    "li": frozenset({"value"}),
    "td": frozenset({"colspan", "headers", "rowspan", "scope"}),
    "th": frozenset({"colspan", "headers", "rowspan", "scope"}),
    "col": frozenset({"span"}),
    "colgroup": frozenset({"span"}),
    "table": frozenset({"border", "cellpadding", "cellspacing", "summary"}),
}

ALLOWED_STYLES = frozenset(
    {
        "background-color", "border", "border-collapse", "border-color", "border-style",
        "border-width", "clear", "color", "float", "font-family", "font-size", "font-style",
        "font-weight", "height", "line-height", "list-style-type", "margin", "margin-bottom",
        "margin-left", "margin-right", "margin-top", "max-width", "padding", "padding-bottom",
        "padding-left", "padding-right", "padding-top", "text-align", "text-decoration",
        "text-indent", "vertical-align", "white-space", "width",
    }
)  # fmt: skip

_CLASS = re.compile(r"^[A-Za-z0-9_ -]{1,120}$")
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_:.-]{0,60}$")
_NUMBER = re.compile(r"^\d{1,4}%?$")
_SAFE_URL_SCHEMES = frozenset({"http", "https", "mailto", "tel"})
# Words, numbers, units, #hex colours, and the functional notations of colours (rgb(...)), which
# are checked separately. Anything with url(), expression(), a backslash or a comment is refused.
_STYLE_VALUE = re.compile(r"^[A-Za-z0-9#%.,\s'\"/-]{1,120}$")
_COLOR_FUNCTION = re.compile(r"^(rgb|rgba|hsl|hsla)\([0-9\s.,%/]{1,40}\)$", re.IGNORECASE)
_STRIP_CONTROL = re.compile(r"[\x00-\x20\x7f]+")


def _safe_url(value: str, *, image: bool = False) -> str | None:
    """The address if it is safe to link or embed, else None."""
    cleaned = _STRIP_CONTROL.sub("", value or "")
    if not cleaned or len(cleaned) > 2000:
        return None
    if cleaned.startswith("//"):  # protocol-relative: could point anywhere, and is not needed
        return None
    try:
        parts = urlsplit(cleaned)
    except ValueError:
        return None
    if parts.scheme:
        allowed = {"http", "https"} if image else _SAFE_URL_SCHEMES
        if parts.scheme.lower() not in allowed:
            return None
    elif ":" in cleaned.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]:
        return None  # a scheme-like prefix urlsplit did not recognise
    return value.strip()


def _clean_style(value: str) -> str:
    declarations: list[str] = []
    for declaration in (value or "").split(";"):
        if ":" not in declaration:
            continue
        prop, _, raw = declaration.partition(":")
        prop = prop.strip().lower()
        raw = raw.strip()
        if prop not in ALLOWED_STYLES or not raw:
            continue
        lowered = raw.lower()
        if "url(" in lowered or "expression" in lowered or "javascript" in lowered:
            continue
        if "(" in raw or ")" in raw:
            # Only a colour function, and only as a whole value.
            if not _COLOR_FUNCTION.match(raw):
                continue
        elif not _STYLE_VALUE.match(raw):
            continue
        declarations.append(f"{prop}: {raw}")
    return "; ".join(declarations)


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[str] = []
        self.drop_depth = 0  # >0 while inside a tag that is removed with its contents

    # -- helpers
    def _attributes(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        allowed = GLOBAL_ATTRIBUTES | TAG_ATTRIBUTES.get(tag, frozenset())
        parts: list[str] = []
        target_blank = False
        for name, raw in attrs:
            name = name.lower()
            value = raw or ""
            if name not in allowed or name.startswith("on"):
                continue
            if name == "href":
                url = _safe_url(value)
                if url is None:
                    continue
                value = url
            elif name == "src":
                url = _safe_url(value, image=True)
                if url is None:
                    continue
                value = url
            elif name == "style":
                value = _clean_style(value)
                if not value:
                    continue
            elif name == "class":
                if not _CLASS.match(value):
                    continue
            elif name in {"id", "name"}:
                if not _ID.match(value):
                    continue
            elif name == "target":
                if value != "_blank":
                    continue
                target_blank = True
            elif name == "rel":
                continue  # set below, so a page cannot ask for anything else
            elif name in {"width", "height", "colspan", "rowspan", "span", "start", "value"}:
                if not _NUMBER.match(value.strip()):
                    continue
                value = value.strip()
            elif name in {"border", "cellpadding", "cellspacing"}:
                if not re.match(r"^\d{1,2}$", value.strip()):
                    continue
                value = value.strip()
            elif name == "dir":
                if value.lower() not in {"ltr", "rtl"}:
                    continue
                value = value.lower()
            elif name == "scope":
                if value.lower() not in {"row", "col", "rowgroup", "colgroup"}:
                    continue
                value = value.lower()
            elif name == "type":
                if value not in {"1", "a", "A", "i", "I"}:
                    continue
            parts.append(f' {name}="{escape(value, quote=True)}"')
        if tag == "a" and target_blank:
            parts.append(' rel="noopener noreferrer"')
        return "".join(parts)

    # -- parser callbacks
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            if tag not in _VOID_DROPPED:
                self.drop_depth += 1
            return
        if self.drop_depth or tag not in ALLOWED_TAGS:
            return
        if tag == "img" and not any(
            n == "src" and _safe_url(v or "", image=True) for n, v in attrs
        ):
            return  # an image without a usable address is nothing
        self.out.append(f"<{tag}{self._attributes(tag, attrs)}>")
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            return  # `<script/>` has no contents to skip
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS and tag in ALLOWED_TAGS and not self.drop_depth:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            if self.drop_depth and tag not in _VOID_DROPPED:
                self.drop_depth -= 1
            return
        if self.drop_depth or tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return
        if tag not in self.stack:
            return  # a stray end tag
        while self.stack:
            open_tag = self.stack.pop()
            self.out.append(f"</{open_tag}>")
            if open_tag == tag:
                break

    def handle_data(self, data: str) -> None:
        if self.drop_depth:
            return
        self.out.append(escape(data, quote=False))

    # Comments, declarations, processing instructions: dropped (they are the default no-ops).

    def result(self) -> str:
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")
        return "".join(self.out)


def sanitize_html(html: str) -> str:
    """The post body rebuilt from the allow-list. Idempotent: running it again changes nothing."""
    parser = _Sanitizer()
    parser.feed(html or "")
    parser.close()
    return parser.result()


class _TextExtractor(HTMLParser):
    BLOCK = frozenset(
        {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.drop_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in DROP_WITH_CONTENT:
            if tag not in _VOID_DROPPED:
                self.drop_depth += 1
        elif tag in self.BLOCK:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in DROP_WITH_CONTENT:
            if tag not in _VOID_DROPPED:
                self.drop_depth = max(0, self.drop_depth - 1)
        elif tag in self.BLOCK:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.drop_depth:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    """The readable text of some HTML, whitespace collapsed (for summaries and search)."""
    extractor = _TextExtractor()
    extractor.feed(html or "")
    extractor.close()
    return re.sub(r"\s+", " ", "".join(extractor.parts)).strip()
