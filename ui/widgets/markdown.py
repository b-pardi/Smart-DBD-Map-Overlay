"""a small dependency-free markdown renderer that packs themed widgets straight into a parent frame.

built for the attributions and about copy so a caller can drop rendered markdown into an existing
scrollable frame without nesting a second scroll of its own. it composes, it does not own a scroll.
supports #/##/### headings, - / * bullets, --- rules, blank-line spacing, plain paragraphs, the
leading-bold **Term** rest pattern, and [text](url) plus bare http(s) urls as clickable accent labels
that keep the url visible. colors and fonts come from the theme only.
"""

import re
import webbrowser

import customtkinter as ctk

from .. import theme

WRAP = 660  # paragraph wrap width, stays inside the content area even at the min window size

# block-level line shapes
_HEADING = re.compile(r"(#{1,3})\s+(.*)")
_BULLET = re.compile(r"[-*]\s+(.*)")
_RULE = re.compile(r"(-{3,}|\*{3,}|_{3,})$")
_NEW_BLOCK = re.compile(r"^\s*([-*]\s+|#{1,3}\s+|(-{3,}|\*{3,}|_{3,})\s*$)")

# inline shapes
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_ANY_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_BARE_URL = re.compile(r"https?://[^\s)]+")
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def render(parent, text):
    """parse markdown text and pack themed, read-only widgets into parent.

    packs directly into parent so it composes inside an existing scrollable frame. supports #/##/###
    headings, - / * bullets, --- rules, blank-line spacing, plain paragraphs, the leading-bold
    **Term** rest pattern, and [text](url) plus bare urls as clickable links.
    """
    started = False
    for kind, payload in _blocks(text):
        if kind == "blank":
            if started:  # skip a spacer before any real content so the top sits flush
                _spacer(parent)
            continue
        started = True
        if kind == "h":
            _heading(parent, *payload)
        elif kind == "hr":
            _rule(parent)
        elif kind == "li":
            _bullet(parent, payload)
        else:
            _paragraph(parent, payload)


def render_file(parent, path, drop_title=False):
    """read a markdown file and render it, showing a friendly note in place if it can't be read.

    drop_title strips a leading level-1 heading so a screen's own header isn't shown twice.
    """
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        name = getattr(path, "name", path)
        _paragraph(parent, f"could not read {name}: {type(e).__name__}: {e}")
        return
    render(parent, strip_title(text) if drop_title else text)


def strip_title(text):
    """drop a leading level-1 heading and its trailing blank so a screen title isn't duplicated"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and re.match(r"#\s+", lines[i].strip()):
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        return "\n".join(lines[i:])
    return text


def _blocks(text):
    """group raw lines into (kind, payload) blocks: h, hr, li, p, blank"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    para = []

    def flush():
        if para:
            out.append(("p", " ".join(s.strip() for s in para).strip()))
            para.clear()

    i, n = 0, len(lines)
    while i < n:
        line = lines[i].strip()
        if not line:
            flush()
            if out and out[-1][0] != "blank":  # one gap per run of blank lines
                out.append(("blank", None))
            i += 1
            continue
        m = _HEADING.match(line)
        if m:
            flush()
            out.append(("h", (len(m.group(1)), m.group(2).strip())))
            i += 1
            continue
        if _RULE.match(line):
            flush()
            out.append(("hr", None))
            i += 1
            continue
        b = _BULLET.match(line)
        if b:
            flush()
            parts = [b.group(1).strip()]
            j = i + 1
            # an indented non-blank line that opens no new block wraps into this same item
            while j < n and lines[j].strip() and lines[j][:1].isspace() and not _NEW_BLOCK.match(lines[j]):
                parts.append(lines[j].strip())
                j += 1
            out.append(("li", " ".join(parts).strip()))
            i = j
            continue
        para.append(line)
        i += 1
    flush()
    return out


def _heading(parent, level, text):
    fam = theme.FONT_TITLE[0]
    size = {1: 20, 2: 16, 3: 13}.get(level, 13)
    top = theme.PAD if level < 3 else 4  # bigger headings breathe more above
    ctk.CTkLabel(
        parent,
        text=_plain(text),
        font=(fam, size, "bold"),
        text_color=theme.BONE,
        anchor="w",
        justify="left",
        wraplength=WRAP,
    ).pack(fill="x", anchor="w", pady=(top, 2))


def _rule(parent):
    ctk.CTkFrame(parent, height=1, corner_radius=0, fg_color=theme.BORDER).pack(
        fill="x", pady=theme.PAD)


def _spacer(parent):
    ctk.CTkFrame(parent, height=theme.PAD, fg_color="transparent").pack(fill="x")


def _paragraph(parent, content):
    _rich(parent, content)


def _bullet(parent, content):
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", anchor="w", pady=1)
    ctk.CTkLabel(
        row,
        text="•",
        font=theme.FONT_BODY,
        text_color=theme.ACCENT_BRIGHT,
        width=16,
        anchor="n",
    ).pack(side="left", anchor="n")
    holder = ctk.CTkFrame(row, fg_color="transparent")
    holder.pack(side="left", fill="x", expand=True)
    _rich(holder, content, wrap=WRAP - 24)


def _rich(parent, content, wrap=WRAP):
    """render one inline string: an optional leading-bold term with its rest, then any urls as links"""
    term, rest = _split_leading_bold(content.strip())
    body, links = _extract_links(rest)
    body = re.sub(r"\s{2,}", " ", _plain(body)).strip()

    if term is not None:
        term = _plain(term)
        if body and _est_width(term) <= wrap * 0.55:
            # the common case, bold term and its rest on one row
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", anchor="w")
            ctk.CTkLabel(
                row,
                text=term,
                font=(theme.FONT_BODY[0], theme.FONT_BODY[1], "bold"),
                text_color=theme.BONE,
                anchor="nw",
                justify="left",
            ).pack(side="left", anchor="n")
            rest_wrap = max(int(wrap - _est_width(term) - 20), 220)
            ctk.CTkLabel(
                row,
                text=" " + body,
                font=theme.FONT_BODY,
                text_color=theme.BONE,
                anchor="nw",
                justify="left",
                wraplength=rest_wrap,
            ).pack(side="left", anchor="n")
        else:
            # a long term or an empty rest reads better stacked than crammed onto one row
            ctk.CTkLabel(
                parent,
                text=term,
                font=(theme.FONT_BODY[0], theme.FONT_BODY[1], "bold"),
                text_color=theme.BONE,
                anchor="w",
                justify="left",
                wraplength=wrap,
            ).pack(fill="x", anchor="w")
            if body:
                ctk.CTkLabel(
                    parent,
                    text=body,
                    font=theme.FONT_BODY,
                    text_color=theme.BONE,
                    anchor="w",
                    justify="left",
                    wraplength=wrap,
                ).pack(fill="x", anchor="w")
    elif body:
        ctk.CTkLabel(
            parent,
            text=body,
            font=theme.FONT_BODY,
            text_color=theme.BONE,
            anchor="w",
            justify="left",
            wraplength=wrap,
        ).pack(fill="x", anchor="w")

    for url in links:
        _link_label(parent, url, wrap)


def _split_leading_bold(content):
    """(term, rest) when content opens with **term**, else (None, content)"""
    m = re.match(r"\*\*(.+?)\*\*\s*(.*)$", content, re.S)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None, content


def _extract_links(text):
    """pull urls out so each renders as its own visible clickable label, returns (text, [url, ...]).

    a [text](url) keeps its visible text inline and surfaces the url as a link, a bare url moves out
    whole so it stays clickable instead of sitting as dead text.
    """
    links = []

    def take_md(m):
        links.append(m.group(2))
        return m.group(1)

    def take_bare(m):
        url = m.group(0).rstrip(".,;:")
        links.append(url)
        return " "

    text = _MD_LINK.sub(take_md, text)
    text = _BARE_URL.sub(take_bare, text)
    return text, links


def _plain(text):
    """strip any leftover markdown punctuation so nothing raw ever shows"""
    text = _BOLD.sub(r"\1", text)
    text = _ANY_LINK.sub(r"\1", text)
    return text.replace("**", "").strip()


def _est_width(s, per=7.5):
    """rough pixel width of a short bold label, only used to choose inline vs stacked layout"""
    return len(s) * per + 16


def _link_label(parent, url, wrap=WRAP):
    """an accent-colored clickable label that opens the url and keeps it visible"""
    lbl = ctk.CTkLabel(
        parent,
        text=url,
        font=(theme.FONT_BODY[0], theme.FONT_BODY[1], "underline"),
        text_color=theme.ACCENT_BRIGHT,
        anchor="w",
        justify="left",
        wraplength=wrap,
        cursor="hand2",
    )
    lbl.pack(fill="x", anchor="w", pady=(0, 2))
    lbl.bind("<Button-1>", lambda _e, u=url: webbrowser.open(u))
    lbl.bind("<Enter>", lambda _e: lbl.configure(text_color=theme.ACCENT_HOVER))
    lbl.bind("<Leave>", lambda _e: lbl.configure(text_color=theme.ACCENT_BRIGHT))
