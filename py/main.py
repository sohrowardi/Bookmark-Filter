"""
main.py — Firefox Bookmark Filter
A desktop utility to selectively export Firefox bookmark folders.

Usage:
    python main.py
    python main.py bookmarks.html

Requirements:
    PySide6 >= 6.4
"""

from __future__ import annotations

import sys
import os
import json
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QLabel, QPushButton,
    QLineEdit, QFileDialog, QStatusBar, QFrame, QScrollArea,
    QGridLayout, QSizePolicy, QMessageBox, QToolBar, QStyle,
)
from PySide6.QtCore import (
    Qt, QThread, Signal, QSettings, QMimeData, QTimer,
)
from PySide6.QtGui import (
    QDragEnterEvent, QDropEvent, QIcon, QFont, QAction, QColor,
    QPalette,
)

from parser import parse_bookmarks, BookmarkNode
from exporter import export_bookmarks


# ── Settings key ────────────────────────────────────────────────────────────
SETTINGS_ORG = "FirefoxBookmarkFilter"
SETTINGS_APP = "bmark_filter"
KEY_LAST_DIR = "last_dir"
KEY_DARK_MODE = "dark_mode"
KEY_GEOMETRY = "geometry"


# ── Worker thread for parsing large files ───────────────────────────────────
class ParseWorker(QThread):
    done = Signal(object)    # emits BookmarkNode root
    error = Signal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        try:
            with open(self.path, "rb") as f:
                data = f.read()
            root = parse_bookmarks(data)
            self.done.emit(root)
        except Exception as e:
            self.error.emit(str(e))


# ── Tree item with node reference ────────────────────────────────────────────
class BookmarkTreeItem(QTreeWidgetItem):
    def __init__(self, node: BookmarkNode, parent=None):
        super().__init__(parent)
        self.node = node
        self._updating = False
        self._refresh()

    def _refresh(self):
        title = self.node.title or "(untitled)"
        count = self.node.total_bookmarks
        self.setText(0, title)
        self.setText(1, str(count) if count else "")
        if self.node.kind == "folder":
            self.setCheckState(0, Qt.Unchecked)

    def set_check_quiet(self, state: Qt.CheckState):
        """Set check state without triggering itemChanged signal."""
        self._updating = True
        self.setCheckState(0, state)
        self._updating = False


# ── Stats card widget ─────────────────────────────────────────────────────
class StatCard(QFrame):
    def __init__(self, label: str, value: str = "0", accent: bool = False):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        self._val_label = QLabel(value)
        font = QFont()
        font.setPointSize(20)
        font.setWeight(QFont.Medium)
        self._val_label.setFont(font)
        if accent:
            self._val_label.setObjectName("statAccent")

        self._lbl = QLabel(label)
        self._lbl.setObjectName("statLabel")

        layout.addWidget(self._val_label)
        layout.addWidget(self._lbl)

    def set_value(self, v):
        self._val_label.setText(str(v))


# ── Main Window ───────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._root: Optional[BookmarkNode] = None
        self._selected_ids: set[int] = set()
        self._all_folder_items: list[BookmarkTreeItem] = []
        self._worker: Optional[ParseWorker] = None
        self._dark = False
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._apply_search)

        self._settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self._dark = self._settings.value(KEY_DARK_MODE, False, type=bool)

        self._build_ui()
        self._apply_theme()
        self.setAcceptDrops(True)

        # Restore geometry
        geom = self._settings.value(KEY_GEOMETRY)
        if geom:
            self.restoreGeometry(geom)
        else:
            self.resize(1000, 660)

        if len(sys.argv) > 1:
            self._load_file(sys.argv[1])

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self):
        self.setWindowTitle("Firefox Bookmark Filter")

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toolbar
        toolbar = self._build_toolbar()
        main_layout.addWidget(toolbar)

        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        main_layout.addWidget(splitter, stretch=1)

        # Left: tree panel
        left_panel = self._build_tree_panel()
        splitter.addWidget(left_panel)

        # Right: preview panel
        right_panel = self._build_preview_panel()
        splitter.addWidget(right_panel)

        splitter.setSizes([580, 380])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Open a Firefox bookmarks HTML file to begin.")

    def _build_toolbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("toolbar")
        bar.setFixedHeight(50)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self._btn_open = QPushButton("  Open file…")
        self._btn_open.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        self._btn_open.setObjectName("btnPrimary")
        self._btn_open.clicked.connect(self._on_open)
        layout.addWidget(self._btn_open)

        layout.addSpacing(4)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search folders…")
        self._search.setMinimumWidth(200)
        self._search.textChanged.connect(lambda _: self._search_timer.start())
        self._search.setClearButtonEnabled(True)
        layout.addWidget(self._search)

        layout.addStretch()

        for text, slot in [
            ("Select all", self._on_select_all),
            ("Deselect all", self._on_deselect_all),
            ("Expand all", self._on_expand_all),
            ("Collapse all", self._on_collapse_all),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            layout.addWidget(btn)

        layout.addSpacing(4)

        self._btn_dark = QPushButton("🌙")
        self._btn_dark.setFixedWidth(36)
        self._btn_dark.setToolTip("Toggle dark mode")
        self._btn_dark.clicked.connect(self._toggle_dark)
        layout.addWidget(self._btn_dark)

        self._btn_export = QPushButton("  Export filtered…")
        self._btn_export.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self._btn_export.setObjectName("btnPrimary")
        self._btn_export.setEnabled(False)
        self._btn_export.clicked.connect(self._on_export)
        layout.addWidget(self._btn_export)

        return bar

    def _build_tree_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel("  Folder tree")
        header.setObjectName("paneHeader")
        header.setFixedHeight(30)
        layout.addWidget(header)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Folder", "Bookmarks"])
        self._tree.header().setDefaultSectionSize(200)
        self._tree.setColumnWidth(0, 380)
        self._tree.setColumnWidth(1, 80)
        self._tree.setAlternatingRowColors(True)
        self._tree.setAnimated(True)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.setUniformRowHeights(True)
        layout.addWidget(self._tree)

        return panel

    def _build_preview_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel("  Live preview")
        header.setObjectName("paneHeader")
        header.setFixedHeight(30)
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(16, 16, 16, 16)
        inner_layout.setSpacing(12)

        # Stats grid
        stats_frame = QWidget()
        grid = QGridLayout(stats_frame)
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)

        self._stat_sel_folders   = StatCard("folders selected", accent=True)
        self._stat_sel_bookmarks = StatCard("bookmarks kept", accent=True)
        self._stat_exc_folders   = StatCard("folders excluded")
        self._stat_exc_bookmarks = StatCard("bookmarks removed")

        grid.addWidget(self._stat_sel_folders,   0, 0)
        grid.addWidget(self._stat_sel_bookmarks, 0, 1)
        grid.addWidget(self._stat_exc_folders,   1, 0)
        grid.addWidget(self._stat_exc_bookmarks, 1, 1)

        inner_layout.addWidget(stats_frame)

        # Selected folders list
        sel_header = QLabel("Selected folders")
        sel_header.setObjectName("sectionHeader")
        inner_layout.addWidget(sel_header)

        self._sel_list_widget = QWidget()
        self._sel_list_layout = QVBoxLayout(self._sel_list_widget)
        self._sel_list_layout.setContentsMargins(0, 0, 0, 0)
        self._sel_list_layout.setSpacing(4)
        inner_layout.addWidget(self._sel_list_widget)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll)

        return panel

    # ── File I/O ──────────────────────────────────────────────────────────

    def _on_open(self):
        last = self._settings.value(KEY_LAST_DIR, str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Firefox Bookmarks", last,
            "HTML Bookmarks (*.html *.htm);;All Files (*)"
        )
        if path:
            self._load_file(path)

    def _load_file(self, path: str):
        if not os.path.isfile(path):
            QMessageBox.warning(self, "File not found", f"Cannot open:\n{path}")
            return

        self._settings.setValue(KEY_LAST_DIR, str(Path(path).parent))
        self._status.showMessage(f"Parsing {Path(path).name}…")
        self._tree.clear()
        self._all_folder_items.clear()
        self._selected_ids.clear()

        self._worker = ParseWorker(path)
        self._worker.done.connect(self._on_parse_done)
        self._worker.error.connect(self._on_parse_error)
        self._worker.start()

    def _on_parse_done(self, root: BookmarkNode):
        self._root = root
        self._populate_tree(root)
        total = root.total_bookmarks
        folders = len(root.all_folders()) - 1  # exclude synthetic root
        self._status.showMessage(
            f"Loaded {total:,} bookmarks across {folders:,} folders."
        )
        self._btn_export.setEnabled(True)
        self._update_preview()

    def _on_parse_error(self, msg: str):
        self._status.showMessage(f"Error: {msg}")
        QMessageBox.critical(self, "Parse error", f"Could not parse the file:\n\n{msg}")

    # ── Tree population ───────────────────────────────────────────────────

    def _populate_tree(self, root: BookmarkNode):
        self._tree.blockSignals(True)
        self._tree.clear()
        self._all_folder_items.clear()

        for child in root.children:
            self._add_node(child, self._tree.invisibleRootItem())

        self._tree.blockSignals(False)
        self._tree.expandToDepth(1)

    def _add_node(self, node: BookmarkNode, parent_item: QTreeWidgetItem):
        if node.kind == "separator":
            return

        item = BookmarkTreeItem(node, parent_item)
        if node.kind == "folder":
            self._all_folder_items.append(item)
            for child in node.children:
                self._add_node(child, item)

    # ── Check state propagation ───────────────────────────────────────────

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        if not isinstance(item, BookmarkTreeItem):
            return
        if item._updating:
            return
        if item.node.kind != "folder":
            return

        self._tree.blockSignals(True)
        state = item.checkState(0)
        self._propagate_down(item, state)
        self._propagate_up(item)
        self._tree.blockSignals(False)

        self._rebuild_selected_ids()
        self._update_preview()

    def _propagate_down(self, item: BookmarkTreeItem, state: Qt.CheckState):
        """Set all descendant folders to the same check state."""
        for i in range(item.childCount()):
            child = item.child(i)
            if isinstance(child, BookmarkTreeItem) and child.node.kind == "folder":
                child.set_check_quiet(state)
                self._propagate_down(child, state)

    def _propagate_up(self, item: BookmarkTreeItem):
        """Update ancestors: if any child checked → partial; all checked → checked; none → unchecked."""
        parent = item.parent()
        if not isinstance(parent, BookmarkTreeItem):
            return
        if parent.node.kind != "folder":
            return

        states = set()
        for i in range(parent.childCount()):
            child = parent.child(i)
            if isinstance(child, BookmarkTreeItem) and child.node.kind == "folder":
                states.add(child.checkState(0))

        if states == {Qt.Checked}:
            new_state = Qt.Checked
        elif Qt.Unchecked in states and states == {Qt.Unchecked}:
            new_state = Qt.Unchecked
        else:
            new_state = Qt.PartiallyChecked

        parent.set_check_quiet(new_state)
        self._propagate_up(parent)

    def _rebuild_selected_ids(self):
        """Collect node ids for all fully-checked folder items."""
        self._selected_ids = {
            id(item.node)
            for item in self._all_folder_items
            if item.checkState(0) == Qt.Checked
        }

    # ── Toolbar actions ───────────────────────────────────────────────────

    def _on_select_all(self):
        self._tree.blockSignals(True)
        for item in self._all_folder_items:
            item.set_check_quiet(Qt.Checked)
        self._tree.blockSignals(False)
        self._rebuild_selected_ids()
        self._update_preview()

    def _on_deselect_all(self):
        self._tree.blockSignals(True)
        for item in self._all_folder_items:
            item.set_check_quiet(Qt.Unchecked)
        self._tree.blockSignals(False)
        self._selected_ids.clear()
        self._update_preview()

    def _on_expand_all(self):
        self._tree.expandAll()

    def _on_collapse_all(self):
        self._tree.collapseAll()
        self._tree.expandToDepth(0)

    # ── Search ────────────────────────────────────────────────────────────

    def _apply_search(self):
        query = self._search.text().strip().lower()
        for item in self._all_folder_items:
            if not query:
                item.setHidden(False)
            else:
                match = query in item.node.title.lower()
                item.setHidden(not match)
                if match:
                    # Show ancestors
                    p = item.parent()
                    while p and isinstance(p, BookmarkTreeItem):
                        p.setHidden(False)
                        p.setExpanded(True)
                        p = p.parent()

    # ── Live preview ──────────────────────────────────────────────────────

    def _update_preview(self):
        if not self._root:
            return

        # Count what's selected vs excluded
        all_folders = self._root.all_folders()
        all_folder_nodes = [f for f in all_folders if f.kind == "folder"]

        sel_folder_nodes = [
            f for f in all_folder_nodes if id(f) in self._selected_ids
        ]
        exc_folder_nodes = [
            f for f in all_folder_nodes if id(f) not in self._selected_ids
        ]

        sel_bookmarks = sum(f.count_bookmarks() for f in sel_folder_nodes
                            if not any(id(p) in self._selected_ids
                                       for p in _ancestors(f, self._root)))
        # Simpler: just count all bookmarks in selected subtrees (may double count)
        # Use the exporter logic: bookmarks kept = those reachable from selected
        sel_bm = _count_kept(self._root, self._selected_ids)
        exc_bm = self._root.total_bookmarks - sel_bm

        self._stat_sel_folders.set_value(len(sel_folder_nodes))
        self._stat_sel_bookmarks.set_value(f"{sel_bm:,}")
        self._stat_exc_folders.set_value(len(exc_folder_nodes))
        self._stat_exc_bookmarks.set_value(f"{exc_bm:,}")

        # Rebuild selected folder list
        while self._sel_list_layout.count():
            w = self._sel_list_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        # Show only "top-level" selected (not children of other selected)
        top_selected = [
            f for f in sel_folder_nodes
            if not any(id(p) in self._selected_ids
                       for p in _ancestors(f, self._root))
        ]

        for node in top_selected[:30]:  # cap to avoid UI lag
            row = QFrame()
            row.setObjectName("selRow")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(10, 6, 10, 6)
            lbl = QLabel(f"📁  {node.title}")
            cnt = QLabel(f"{node.total_bookmarks:,} items")
            cnt.setObjectName("statLabel")
            rl.addWidget(lbl)
            rl.addStretch()
            rl.addWidget(cnt)
            self._sel_list_layout.addWidget(row)

        if len(top_selected) > 30:
            more = QLabel(f"  … and {len(top_selected) - 30} more")
            more.setObjectName("statLabel")
            self._sel_list_layout.addWidget(more)

    # ── Export ────────────────────────────────────────────────────────────

    def _on_export(self):
        if not self._root:
            return
        if not self._selected_ids:
            QMessageBox.information(
                self, "Nothing selected",
                "Please select at least one folder before exporting."
            )
            return

        last = self._settings.value(KEY_LAST_DIR, str(Path.home()))
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Filtered Bookmarks", str(Path(last) / "filtered_bookmarks.html"),
            "HTML Bookmarks (*.html)"
        )
        if not path:
            return

        try:
            html = export_bookmarks(self._root, self._selected_ids)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(html)
            self._status.showMessage(f"Exported to {Path(path).name}")
            QMessageBox.information(
                self, "Export complete",
                f"Filtered bookmarks saved to:\n{path}\n\n"
                "Import it in Firefox via Bookmarks → Manage Bookmarks → "
                "Import and Backup → Import Bookmarks from HTML."
            )
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    # ── Drag and drop ─────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(u.toLocalFile().lower().endswith((".html", ".htm"))
                   for u in urls):
                event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".html", ".htm")):
                self._load_file(path)
                break

    # ── Dark mode ─────────────────────────────────────────────────────────

    def _toggle_dark(self):
        self._dark = not self._dark
        self._settings.setValue(KEY_DARK_MODE, self._dark)
        self._apply_theme()

    def _apply_theme(self):
        if self._dark:
            self._btn_dark.setText("☀️")
            QApplication.instance().setStyleSheet(_DARK_STYLE)
        else:
            self._btn_dark.setText("🌙")
            QApplication.instance().setStyleSheet(_LIGHT_STYLE)

    # ── Close ─────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._settings.setValue(KEY_GEOMETRY, self.saveGeometry())
        super().closeEvent(event)


# ── Helper functions ──────────────────────────────────────────────────────

def _ancestors(node: BookmarkNode, root: BookmarkNode) -> list[BookmarkNode]:
    """Return all ancestor folders of node (not including root)."""
    result = []

    def walk(current: BookmarkNode, path: list[BookmarkNode]) -> bool:
        if current is node:
            result.extend(path)
            return True
        for child in current.children:
            if walk(child, path + [current]):
                return True
        return False

    walk(root, [])
    return result


def _count_kept(root: BookmarkNode, selected_ids: set[int]) -> int:
    """Count bookmarks that would be kept given selected_ids."""
    # Walk the tree; a bookmark is kept if it is inside a selected folder
    total = 0

    def walk(node: BookmarkNode, inside_selected: bool):
        nonlocal total
        if node.kind == "bookmark":
            if inside_selected:
                total += 1
        elif node.kind == "folder":
            now_selected = inside_selected or (id(node) in selected_ids)
            for child in node.children:
                walk(child, now_selected)
        else:
            for child in node.children:
                walk(child, inside_selected)

    walk(root, False)
    return total


# ── Stylesheets ───────────────────────────────────────────────────────────

_BASE_STYLE = """
QMainWindow, QWidget { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 13px; }
QTreeWidget { border: none; outline: none; }
QTreeWidget::item { padding: 3px 4px; }
QTreeWidget::item:selected { background: #d0e8ff; color: #003580; }
QTreeWidget::item:hover { background: #eef5ff; }
QHeaderView::section { padding: 4px 8px; font-weight: 500; border: none; border-bottom: 1px solid #ddd; }

QPushButton { padding: 5px 12px; border-radius: 6px; border: 1px solid #ccc; background: white; cursor: pointer; }
QPushButton:hover { background: #f0f0f0; }
QPushButton:pressed { background: #e0e0e0; }
QPushButton#btnPrimary { background: #0061e3; color: white; border-color: #004fbb; }
QPushButton#btnPrimary:hover { background: #0055cc; }
QPushButton#btnPrimary:disabled { background: #aac4e8; border-color: #aac4e8; }

QLineEdit { padding: 5px 10px; border-radius: 6px; border: 1px solid #ccc; background: white; }
QLineEdit:focus { border-color: #0061e3; }

QFrame#toolbar { border-bottom: 1px solid #ddd; }
QLabel#paneHeader { background: #f5f5f5; border-bottom: 1px solid #ddd; padding-left: 12px; font-size: 12px; color: #666; font-weight: 500; }
QLabel#sectionHeader { font-size: 12px; color: #555; font-weight: 500; margin-top: 4px; }
QLabel#statLabel { font-size: 11px; color: #888; }
QLabel#statAccent { color: #0061e3; }
QFrame#selRow { background: #f8f8f8; border-radius: 6px; border: 1px solid #eee; }
QFrame#selRow:hover { background: #f0f0f0; }

QSplitter::handle { background: #ddd; width: 1px; }
QStatusBar { font-size: 12px; color: #666; border-top: 1px solid #ddd; }
QScrollBar:vertical { width: 8px; background: transparent; }
QScrollBar::handle:vertical { background: #ccc; border-radius: 4px; min-height: 20px; }
"""

_LIGHT_STYLE = _BASE_STYLE + """
QMainWindow, QWidget { background: #ffffff; color: #1a1a1a; }
QTreeWidget { background: #ffffff; alternate-background-color: #f9f9f9; }
"""

_DARK_STYLE = _BASE_STYLE + """
QMainWindow, QWidget { background: #1e1e1e; color: #d4d4d4; }
QTreeWidget { background: #252525; alternate-background-color: #2a2a2a; color: #d4d4d4; }
QTreeWidget::item:selected { background: #264f78; color: #d4d4d4; }
QTreeWidget::item:hover { background: #2d3a47; }
QHeaderView::section { background: #2d2d2d; color: #aaa; border-color: #444; }

QPushButton { background: #3c3c3c; color: #d4d4d4; border-color: #555; }
QPushButton:hover { background: #4a4a4a; }
QPushButton:pressed { background: #555; }
QPushButton#btnPrimary { background: #0e639c; border-color: #1177bb; color: white; }
QPushButton#btnPrimary:hover { background: #1177bb; }
QPushButton#btnPrimary:disabled { background: #2a4a6a; border-color: #2a4a6a; }

QLineEdit { background: #3c3c3c; color: #d4d4d4; border-color: #555; }
QLineEdit:focus { border-color: #0e639c; }

QFrame#toolbar { background: #252525; border-bottom-color: #444; }
QLabel#paneHeader { background: #2d2d2d; color: #888; border-bottom-color: #444; }
QLabel#sectionHeader { color: #999; }
QLabel#statLabel { color: #777; }
QLabel#statAccent { color: #4da6ff; }
QFrame#selRow { background: #2d2d2d; border-color: #444; }
QFrame#selRow:hover { background: #353535; }
QSplitter::handle { background: #444; }
QStatusBar { background: #252525; color: #888; border-top-color: #444; }
QScrollBar::handle:vertical { background: #555; }
"""


# ── Entry point ───────────────────────────────────────────────────────────

def main():
    # High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(SETTINGS_APP)
    app.setOrganizationName(SETTINGS_ORG)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
