"""
exporter.py — Serialize selected BookmarkNode subtrees back to Firefox HTML.

Output is structurally identical to Firefox's own export so it can be
reimported via Bookmarks > Import Bookmarks from HTML.
"""

from __future__ import annotations
from parser import BookmarkNode
import html as html_lib
from typing import Iterable


_HEADER = """\
<!DOCTYPE NETSCAPE-Bookmark-file-1>
<!-- This is an automatically generated file.
     It will be read and overwritten.
     DO NOT EDIT! -->
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks Menu</H1>

<DL><p>
"""

_FOOTER = "</DL><p>\n"


def export_bookmarks(root: BookmarkNode, selected_ids: set[int]) -> str:
    """
    Build a Firefox-compatible bookmarks HTML string containing only the
    folders (and their full subtrees) whose id() is in *selected_ids*.

    A folder is included if:
      - its id is in selected_ids, OR
      - it is an ancestor of a selected folder (so hierarchy is preserved)
    """
    ancestor_ids = _compute_ancestors(root, selected_ids)
    include_ids = selected_ids | ancestor_ids

    lines: list[str] = [_HEADER]
    for child in root.children:
        _serialize(child, include_ids, selected_ids, lines, indent=1)
    lines.append(_FOOTER)
    return "".join(lines)


def _compute_ancestors(node: BookmarkNode, selected_ids: set[int]) -> set[int]:
    """
    Return the set of folder node ids that are ancestors of any selected node.
    These must be present in the output to preserve the hierarchy.
    """
    ancestors: set[int] = set()

    def walk(n: BookmarkNode, path: list[int]):
        if id(n) in selected_ids and n.kind == "folder":
            # All nodes in path are ancestors
            ancestors.update(path)
        for child in n.children:
            walk(child, path + [id(n)])

    walk(node, [])
    return ancestors


def _serialize(
    node: BookmarkNode,
    include_ids: set[int],
    selected_ids: set[int],
    lines: list[str],
    indent: int,
):
    pad = "    " * indent

    if node.kind == "folder":
        # Include this folder if it (or any descendant) is selected
        if id(node) not in include_ids:
            return

        attrs_str = _build_attrs(node.attrs, exclude={"FOLDED"})
        title_esc = html_lib.escape(node.title)

        lines.append(f"{pad}<DT><H3{attrs_str}>{title_esc}</H3>\n")
        lines.append(f"{pad}<DL><p>\n")

        for child in node.children:
            if id(node) in selected_ids:
                # Folder is fully selected — include everything inside
                _serialize_full(child, lines, indent + 1)
            else:
                # Ancestor folder — recurse with filter
                _serialize(child, include_ids, selected_ids, lines, indent + 1)

        lines.append(f"{pad}</DL><p>\n")

    elif node.kind == "bookmark":
        # Top-level bookmarks (directly under root containers) — always include
        _serialize_full(node, lines, indent)

    elif node.kind == "separator":
        lines.append(f"{pad}<HR>\n")


def _serialize_full(node: BookmarkNode, lines: list[str], indent: int):
    """Serialize a node and ALL its children unconditionally."""
    pad = "    " * indent

    if node.kind == "folder":
        attrs_str = _build_attrs(node.attrs, exclude={"FOLDED"})
        title_esc = html_lib.escape(node.title)
        lines.append(f"{pad}<DT><H3{attrs_str}>{title_esc}</H3>\n")
        lines.append(f"{pad}<DL><p>\n")
        for child in node.children:
            _serialize_full(child, lines, indent + 1)
        lines.append(f"{pad}</DL><p>\n")

    elif node.kind == "bookmark":
        attrs_str = _build_attrs(node.attrs)
        title_esc = html_lib.escape(node.title)
        lines.append(f"{pad}<DT><A{attrs_str}>{title_esc}</A>\n")

    elif node.kind == "separator":
        lines.append(f"{pad}<HR>\n")


def _build_attrs(attrs: dict, exclude: set[str] | None = None) -> str:
    """Reconstruct HTML attribute string from parsed attrs dict."""
    exclude = exclude or set()
    parts = []
    # Preserve important attributes in a sensible order
    priority = ["HREF", "ADD_DATE", "LAST_MODIFIED", "ICON_URI", "ICON",
                "SHORTCUTURL", "TAGS", "LAST_CHARSET", "ID"]
    seen = set()
    for key in priority:
        if key in attrs and key not in exclude:
            val = attrs[key]
            parts.append(f' {key}="{html_lib.escape(val or "", quote=True)}"')
            seen.add(key)
    for key, val in attrs.items():
        if key not in seen and key not in exclude:
            parts.append(f' {key}="{html_lib.escape(val or "", quote=True)}"')
    return "".join(parts)
