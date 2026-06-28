# Firefox Bookmark Filter

A lightweight desktop utility to selectively export Firefox bookmark folders.

Firefox exports all bookmarks to a single HTML file with no way to pick individual folders.
This tool lets you choose exactly which folders to keep and exports a clean, Firefox-compatible HTML file.

## Features

- **Folder tree** with checkboxes — select/deselect individual folders
- **Cascading selection** — checking a parent selects all children automatically
- **Partial selection** — parent shows a dash (−) when only some children are selected
- **Live preview** — see the exact folder and bookmark counts before exporting
- **Search** — quickly find folders by name
- **Select All / Deselect All / Expand All / Collapse All**
- **Dark mode** toggle (remembered across sessions)
- **Drag-and-drop** — drag your HTML file onto the window
- **Preserves all metadata** — ADD_DATE, LAST_MODIFIED, ICON, HREF, etc.
- **Separators** preserved in output
- **Fast** — 5,000 bookmarks parsed in ~100ms; 50,000+ works fine

## Usage

### Run from source

```bash
pip install PySide6
python main.py
# or
python main.py my_bookmarks.html
```

### How to export from Firefox

1. Open Firefox → Bookmarks → Manage Bookmarks (Ctrl+Shift+O)
2. Click "Import and Backup" → "Export Bookmarks to HTML"
3. Save as `bookmarks.html`

### How to import back into Firefox

1. Use this tool to create a filtered export
2. In Firefox → Bookmarks → Manage Bookmarks → Import and Backup → Import Bookmarks from HTML
3. Select your filtered file

## Package as standalone executable

### Windows / macOS / Linux (PyInstaller)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "BookmarkFilter" main.py
# Output: dist/BookmarkFilter (or .exe on Windows)
```

### Alternative: Nuitka (faster startup)

```bash
pip install nuitka
nuitka --onefile --enable-plugin=pyside6 --windows-disable-console main.py
```

## Project structure

```
bmark_filter/
├── main.py              # PySide6 GUI application
├── parser.py            # Firefox HTML bookmarks parser
├── exporter.py          # Firefox-compatible HTML exporter
├── tests.py             # Test suite (13 tests)
├── sample_bookmarks.html  # Sample file for testing
└── README.md
```

## Output format

The exported HTML is structurally identical to Firefox's own format:

```html
<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks Menu</H1>

<DL><p>
    <DT><H3 ADD_DATE="1609459200">Work</H3>
    <DL><p>
        <DT><A HREF="https://example.com" ADD_DATE="1610000000">Example</A>
    </DL><p>
</DL><p>
```

## Running tests

```bash
python tests.py
```

All 13 tests should pass, covering:
- Parser structure and nesting
- Bookmark counts
- Attribute preservation (ADD_DATE, ICON, etc.)
- Separator handling
- Export of selected vs. excluded folders
- Partial selection (sub-folder only)
- Roundtrip: export → re-parse → verify
- Performance: 5000 bookmarks < 200ms
