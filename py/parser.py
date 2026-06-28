"""
parser.py — Firefox bookmarks HTML parser.

Parses the Netscape Bookmark File format (used by Firefox, Chrome, etc.)
into a tree of BookmarkNode objects, preserving all attributes.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Optional
import re


@dataclass
class BookmarkNode:
    """Represents either a folder or a bookmark."""
    kind: str          # "folder" | "bookmark" | "separator" | "root"
    title: str = ""
    url: str = ""
    attrs: dict = field(default_factory=dict)   # raw HTML attributes
    children: list["BookmarkNode"] = field(default_factory=list)
    parent: Optional["BookmarkNode"] = field(default=None, repr=False)

    # Computed during tree-walk
    total_bookmarks: int = 0   # recursive count including sub-folders

    def is_folder(self) -> bool:
        return self.kind in ("folder", "root")

    def count_bookmarks(self) -> int:
        """Recursively count bookmark (leaf) nodes."""
        if self.kind == "bookmark":
            return 1
        return sum(c.count_bookmarks() for c in self.children)

    def all_folders(self) -> list["BookmarkNode"]:
        """Return self + all descendant folders in DFS order."""
        result = []
        if self.is_folder():
            result.append(self)
        for child in self.children:
            result.extend(child.all_folders())
        return result


class _BookmarksParser(HTMLParser):
    """
    State-machine HTML parser for Firefox bookmarks format.

    The format looks like:
        <DT><H3 ...>Folder Name</H3>
        <DL><p>
            <DT><A HREF="..." ...>Bookmark Title</A>
            <DT><H3 ...>Sub-folder</H3>
            <DL><p>
                ...
            </DL><p>
        </DL><p>
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = BookmarkNode(kind="root", title="__root__")
        self._stack: list[BookmarkNode] = [self.root]
        self._current_tag: str = ""
        self._pending_attrs: dict = {}

    @property
    def _current(self) -> BookmarkNode:
        return self._stack[-1]

    def handle_starttag(self, tag: str, attrs):
        tag = tag.upper()
        attr_dict = {k.upper(): v for k, v in attrs}
        self._current_tag = tag
        self._pending_attrs = attr_dict

        if tag == "DL":
            # Push current folder context — already on stack from <H3>
            pass

        elif tag == "H3":
            # New folder; will be named when we see the text in handle_data
            node = BookmarkNode(
                kind="folder",
                attrs=attr_dict,
                parent=self._current,
            )
            self._current.children.append(node)
            self._stack.append(node)

        elif tag == "A":
            node = BookmarkNode(
                kind="bookmark",
                url=attr_dict.get("HREF", ""),
                attrs=attr_dict,
                parent=self._current,
            )
            self._current.children.append(node)
            self._stack.append(node)

        elif tag == "HR":
            node = BookmarkNode(kind="separator", parent=self._current)
            self._current.children.append(node)

    def handle_endtag(self, tag: str):
        tag = tag.upper()
        self._current_tag = ""

        if tag == "H3":
            # Folder name was set in handle_data; pop back to parent
            # BUT keep it on the stack — the next <DL> is its children.
            # We only truly leave when </DL> closes.
            pass

        elif tag == "A":
            if self._stack and self._current.kind == "bookmark":
                self._stack.pop()

        elif tag == "DL":
            # Close this folder level
            if len(self._stack) > 1 and self._current.is_folder():
                self._stack.pop()

    def handle_data(self, data: str):
        data = data.strip()
        if not data:
            return
        if self._current_tag == "H3" and self._current.kind == "folder":
            self._current.title = data
        elif self._current_tag == "A" and self._current.kind == "bookmark":
            self._current.title = data


def parse_bookmarks(html_content: str) -> BookmarkNode:
    """
    Parse Firefox bookmarks HTML and return the root BookmarkNode.

    The returned node has kind="root" and its children are the top-level
    Firefox containers (Bookmarks Menu, Toolbar, Other Bookmarks).
    """
    # Firefox sometimes writes latin-1 or windows-1252; normalise to str
    if isinstance(html_content, bytes):
        for enc in ("utf-8", "windows-1252", "latin-1"):
            try:
                html_content = html_content.decode(enc)
                break
            except UnicodeDecodeError:
                continue

    parser = _BookmarksParser()
    parser.feed(html_content)

    # Compute recursive bookmark counts
    _annotate_counts(parser.root)
    return parser.root


def _annotate_counts(node: BookmarkNode):
    node.total_bookmarks = node.count_bookmarks()
    for child in node.children:
        _annotate_counts(child)
