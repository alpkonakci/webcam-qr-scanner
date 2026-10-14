"""Mechanical literal-only migration; never wrap QR data or user names."""
import ast
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
catalog = json.loads((root / "pwa/lib/translations.tr.json").read_text(encoding="utf-8"))
for name in ("home_ui.py", "paired_phones_ui.py", "pairing_ui.py", "phone_scanner_ui.py", "qr_creator_ui.py", "tray_app.py", "display_selector.py", "screen_selector.py", "ui.py"):
    path = root / name
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines: offsets.append(offsets[-1] + len(line))
    def position(line, column):
        # AST columns count UTF-8 bytes; slicing source counts codepoints.
        return offsets[line - 1] + len(lines[line - 1].encode()[:column].decode())
    changes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str): continue
        if " ".join(node.value.split()) not in catalog: continue
        ancestor, inside_function, excluded = node, False, False
        while ancestor in parents:
            ancestor = parents[ancestor]
            if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)): inside_function = True
            if isinstance(ancestor, ast.JoinedStr): excluded = True
            if isinstance(ancestor, ast.Call) and isinstance(ancestor.func, ast.Name) and ancestor.func.id == "t": excluded = True
        if not inside_function or excluded: continue
        if isinstance(parents.get(node), ast.Expr): continue
        start, end = position(node.lineno, node.col_offset), position(node.end_lineno, node.end_col_offset)
        changes.append((start, end, "t(" + source[start:end] + ")"))
    for start, end, value in sorted(changes, reverse=True): source = source[:start] + value + source[end:]
    if "from desktop_i18n import t" not in source:
        source = source.replace("from __future__ import annotations\n", "from __future__ import annotations\n\nfrom desktop_i18n import t\n", 1)
    if name in {"ui.py", "screen_selector.py"}:
        source = source.replace("    cv2.putText(\n", "    put_text(\n")
        if name == "screen_selector.py" and "from ui import put_text" not in source:
            source = source.replace("from ui import COLOR_ACCENT", "from ui import put_text\nfrom ui import COLOR_ACCENT")
    path.write_text(source, encoding="utf-8")
    print(name, len(changes), "UI literals migrated")
