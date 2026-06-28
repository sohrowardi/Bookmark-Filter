"""
tests.py — Automated tests for the bookmark parser and exporter.

Run with: python tests.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from parser import parse_bookmarks, BookmarkNode
from exporter import export_bookmarks


SAMPLE = open(os.path.join(os.path.dirname(__file__), "sample_bookmarks.html")).read()


def test_parse_structure():
    root = parse_bookmarks(SAMPLE)
    assert root.kind == "root"
    # Should have 4 top-level folders
    folders = [c for c in root.children if c.kind == "folder"]
    assert len(folders) == 4, f"Expected 4 folders, got {len(folders)}: {[f.title for f in folders]}"
    print("✓ parse_structure: 4 top-level folders found")


def test_parse_titles():
    root = parse_bookmarks(SAMPLE)
    titles = [c.title for c in root.children if c.kind == "folder"]
    assert "Work" in titles
    assert "Personal" in titles
    assert "Reading" in titles
    assert "Toolbar" in titles
    print("✓ parse_titles: all expected folder names found")


def test_parse_nesting():
    root = parse_bookmarks(SAMPLE)
    work = next(c for c in root.children if c.title == "Work")
    sub_folders = [c for c in work.children if c.kind == "folder"]
    assert len(sub_folders) == 2, f"Expected 2 sub-folders under Work, got {len(sub_folders)}"
    sub_titles = {f.title for f in sub_folders}
    assert "Design Resources" in sub_titles
    assert "APIs" in sub_titles
    print("✓ parse_nesting: nested folders parsed correctly")


def test_bookmark_count():
    root = parse_bookmarks(SAMPLE)
    work = next(c for c in root.children if c.title == "Work")
    # 2 bookmarks directly + 2 in Design + 2 in APIs = 6
    assert work.total_bookmarks == 6, f"Expected 6 bookmarks in Work, got {work.total_bookmarks}"
    print("✓ bookmark_count: recursive count is correct")


def test_attributes_preserved():
    root = parse_bookmarks(SAMPLE)
    work = next(c for c in root.children if c.title == "Work")
    assert "ADD_DATE" in work.attrs, "ADD_DATE should be in folder attrs"
    assert work.attrs["ADD_DATE"] == "1609459200"
    # Bookmark with ICON
    py_docs = next(c for c in work.children if c.kind == "bookmark" and "Python" in c.title)
    assert "ICON" in py_docs.attrs, "ICON attribute should be preserved"
    print("✓ attributes_preserved: ADD_DATE, ICON etc. kept")


def test_separator_preserved():
    root = parse_bookmarks(SAMPLE)
    reading = next(c for c in root.children if c.title == "Reading")
    kinds = [c.kind for c in reading.children]
    assert "separator" in kinds, "Separator should be preserved in Reading folder"
    print("✓ separator_preserved")


def test_export_selected_work():
    root = parse_bookmarks(SAMPLE)
    work = next(c for c in root.children if c.title == "Work")
    selected = {id(work)}
    html = export_bookmarks(root, selected)

    # Work folder must be present
    assert "Work" in html
    assert "Python Docs" in html
    assert "Figma" in html
    # Personal must NOT be present
    assert "Personal" not in html
    assert "Netflix" not in html
    print("✓ export_selected_work: Work exported, Personal excluded")


def test_export_partial_selection():
    """Select only Design Resources (nested) but not all of Work."""
    root = parse_bookmarks(SAMPLE)
    work = next(c for c in root.children if c.title == "Work")
    design = next(c for c in work.children if c.title == "Design Resources")

    selected = {id(design)}
    html = export_bookmarks(root, selected)

    # Work should appear as container (ancestor)
    assert "Work" in html
    # Design Resources and its bookmarks should be present
    assert "Design Resources" in html
    assert "Figma" in html
    # APIs should NOT be present (sibling, not selected)
    assert "APIs" not in html
    assert "Swagger" not in html
    print("✓ export_partial_selection: partial sub-folder export works")


def test_export_firefox_doctype():
    root = parse_bookmarks(SAMPLE)
    work = next(c for c in root.children if c.title == "Work")
    html = export_bookmarks(root, {id(work)})
    assert "NETSCAPE-Bookmark-file-1" in html
    assert "charset=UTF-8" in html
    print("✓ export_firefox_doctype: correct DOCTYPE and meta present")


def test_export_attributes_preserved():
    root = parse_bookmarks(SAMPLE)
    work = next(c for c in root.children if c.title == "Work")
    html = export_bookmarks(root, {id(work)})
    # ADD_DATE should be in the output
    assert "ADD_DATE" in html
    # ICON attribute should be preserved for Python Docs
    assert "ICON=" in html
    print("✓ export_attributes_preserved: ADD_DATE, ICON etc. in output")


def test_export_empty_selection():
    root = parse_bookmarks(SAMPLE)
    html = export_bookmarks(root, set())
    # Should still be valid HTML, just no folder content
    assert "NETSCAPE-Bookmark-file-1" in html
    assert "Netflix" not in html
    print("✓ export_empty_selection: empty set produces minimal valid HTML")


def test_roundtrip():
    """Export selected folders then re-parse to verify structure."""
    root = parse_bookmarks(SAMPLE)
    work = next(c for c in root.children if c.title == "Work")
    reading = next(c for c in root.children if c.title == "Reading")

    html = export_bookmarks(root, {id(work), id(reading)})
    root2 = parse_bookmarks(html)

    titles2 = {c.title for c in root2.children if c.kind == "folder"}
    assert "Work" in titles2, f"Work missing from roundtrip: {titles2}"
    assert "Reading" in titles2, f"Reading missing from roundtrip: {titles2}"
    # Personal and Toolbar should be absent
    assert "Personal" not in titles2
    assert "Toolbar" not in titles2

    work2 = next(c for c in root2.children if c.title == "Work")
    assert work2.total_bookmarks == 6, f"Expected 6 bookmarks, got {work2.total_bookmarks}"
    print("✓ roundtrip: re-parsed output has correct structure and bookmark counts")


def test_large_file_performance():
    """Generate a synthetic 5000-bookmark file and time the parse."""
    import time
    lines = [
        '<!DOCTYPE NETSCAPE-Bookmark-file-1>',
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        '<TITLE>Bookmarks</TITLE><H1>Bookmarks Menu</H1>',
        '<DL><p>',
    ]
    for i in range(50):
        lines.append(f'<DT><H3 ADD_DATE="1600000000">Folder {i}</H3><DL><p>')
        for j in range(100):
            lines.append(f'<DT><A HREF="https://example.com/{i}/{j}" ADD_DATE="1600000000">Bookmark {i}-{j}</A>')
        lines.append('</DL><p>')
    lines.append('</DL><p>')
    big_html = "\n".join(lines)

    start = time.perf_counter()
    root = parse_bookmarks(big_html)
    elapsed = time.perf_counter() - start

    assert root.total_bookmarks == 5000
    assert elapsed < 2.0, f"Parsing 5000 bookmarks took {elapsed:.2f}s — too slow"
    print(f"✓ large_file_performance: 5000 bookmarks parsed in {elapsed*1000:.1f}ms")


if __name__ == "__main__":
    tests = [
        test_parse_structure,
        test_parse_titles,
        test_parse_nesting,
        test_bookmark_count,
        test_attributes_preserved,
        test_separator_preserved,
        test_export_selected_work,
        test_export_partial_selection,
        test_export_firefox_doctype,
        test_export_attributes_preserved,
        test_export_empty_selection,
        test_roundtrip,
        test_large_file_performance,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"✗ {t.__name__}: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    if failed == 0:
        print("All tests passed! ✓")
    sys.exit(0 if failed == 0 else 1)
