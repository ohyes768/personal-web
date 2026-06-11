# -*- coding: utf-8 -*-
# Strip UTF-8 BOM (EF BB BF) from non-Python text files in the repo.
# Rationale: old Windows tools that decode UTF-8 as GBK render the BOM
# as the garbage character U+9518 ("锘"). The BOM is invisible in modern
# editors anyway, so removing it cleans up display in legacy tools.
# We keep BOMs in .py files because the Windows Python interpreter uses
# the BOM as a magic marker to detect UTF-8 source encoding.

import os
import sys

ROOT = r"F:\github\person_project\personal-web"
SKIP = (
    "node_modules", ".git", "dist", "build", "__pycache__", ".next",
    ".pnpm", ".venv", "venv", ".codex", ".gitnexus", "logs",
)
TEXT_EXTS = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".go", ".java",
    ".c", ".cpp", ".h", ".html", ".css", ".json", ".yml", ".yaml",
    ".md", ".sh", ".sql", ".txt", ".toml", ".ini", ".cfg", ".conf",
    ".bat", ".ps1",
)
BOM = b"\xef\xbb\xbf"
KEEP_BOM_EXTS = {".py"}  # Python needs BOM to detect UTF-8 on Windows


def main() -> int:
    scanned = 0
    had_bom = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in files:
            if not f.lower().endswith(TEXT_EXTS):
                continue
            path = os.path.join(base, f)
            scanned += 1
            try:
                with open(path, "rb") as fh:
                    data = fh.read()
            except OSError:
                continue
            if not data.startswith(BOM):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in KEEP_BOM_EXTS:
                continue
            # Re-encode without BOM
            new_data = data[len(BOM):]
            with open(path, "wb") as fh:
                fh.write(new_data)
            had_bom.append(path)
    print(f"scanned: {scanned}")
    print(f"stripped BOM from {len(had_bom)} files:")
    for p in had_bom:
        print("  " + p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
