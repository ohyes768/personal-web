# -*- coding: utf-8 -*-
# Strict mojibake scanner.
# Strategy: try UTF-8 first; for files that decode cleanly, look for SIGNATURE
# mojibake patterns that cannot appear in genuine UTF-8 text:
#   1) U+FFFD replacement character
#   2) file starts with 0x9518 (BOM EF BB BF misread as GBK -> 锘?)
#   3) high Latin-1 chars (0xC0-0xFF) followed by Latin-1 continuation bytes
#      (0x80-0xBF), the classic UTF-8-as-Latin1 look
#   4) known mojibake tokens (Ã©, â€™, Â , 锘? etc.)
# For files that only decode as GB18030, flag them as non-utf-8.

import os
import re
import sys

ROOT = r"F:\github\person_project\personal-web"
SKIP = ("node_modules",".git","dist","build","__pycache__",".next",".pnpm",".venv","venv",".codex",".gitnexus","logs")
EXTS = (".py",".js",".ts",".tsx",".jsx",".vue",".go",".java",".c",".cpp",".h",".html",".css",".json",".yml",".yaml",".md",".sh",".sql",".txt",".toml",".ini",".cfg",".conf")
REPORT_PATH = r"F:\github\person_project\personal-web\scripts\mojibake_report.txt"

RE_REPLACEMENT = re.compile("\uFFFD")
RE_BOM_AS_GBK = re.compile("^\u9518.")
RE_UTF8_AS_LATIN1 = re.compile(r"[\u00C0-\u00FF][\u0080-\u00BF]{1,3}")
KNOWN_TOKENS = ["\u00C3\u00A9","\u00C3\u00A8","\u00C3\u00A1","\u00C3\u00A2","\u00C3\u00A4","\u00C3\u00AB","\u00C3\u00AF","\u00C3\u00B9","\u00C3\u00BB","\u00C3\u00B1","\u00C3\u00AD","\u00E2\u20AC\u2122","\u00E2\u20AC\u0153","\u00E2\u20AC\u009D","\u00E2\u20AC\u201C","\u00E2\u20AC\u2013","\u00E2\u20AC\u2014","\u00E2\u20AC\u00A6","\u00C2\u00A0","\u00C2\u00A1","\u00C2\u00A2","\u00C2\u00A3","\u00C2\u00A4","\u00C2\u00A5","\u9518\u003F","\u9518\uFEFF"]
RE_KNOWN = re.compile("|".join(re.escape(t) for t in KNOWN_TOKENS))

def is_comment_line(line, ext):
    s = line.strip()
    if not s: return False
    if ext in (".py",".sh",".yml",".yaml",".toml",".ini",".cfg",".conf"):
        return s.startswith("#")
    if ext in (".js",".ts",".tsx",".jsx",".vue",".java",".c",".cpp",".h",".go",".css",".sql"):
        return s.startswith("//") or s.startswith("/*") or s.startswith("*")
    if ext in (".html",".md"):
        return True
    return False

def scan_file(path, ext):
    try:
        with open(path, "rb") as fh: data = fh.read()
    except OSError:
        return "binary", []
    if b"\x00" in data: return "binary", []
    try:
        text = data.decode("utf-8"); encoding = "utf-8"
    except UnicodeDecodeError:
        try:
            text = data.decode("gb18030"); encoding = "gb18030"
        except UnicodeDecodeError:
            return "binary", []
    hits = []
    if encoding != "utf-8": return encoding, []
    for m in RE_REPLACEMENT.finditer(text):
        ln = text.count("\n", 0, m.start()) + 1
        ls = text.rfind("\n", 0, m.start()) + 1
        le = text.find("\n", m.end())
        if le < 0: le = len(text)
        hits.append((ln, "replacement_char", text[ls:le].strip()[:200]))
    if RE_BOM_AS_GBK.match(text):
        hits.append((1, "bom_as_gbk", text.split("\n", 1)[0][:200]))
    for m in RE_UTF8_AS_LATIN1.finditer(text):
        ln = text.count("\n", 0, m.start()) + 1
        ls = text.rfind("\n", 0, m.start()) + 1
        le = text.find("\n", m.end())
        if le < 0: le = len(text)
        line = text[ls:le].strip()
        if is_comment_line(line, ext):
            hits.append((ln, "utf8_as_latin1", line[:200]))
    for m in RE_KNOWN.finditer(text):
        ln = text.count("\n", 0, m.start()) + 1
        ls = text.rfind("\n", 0, m.start()) + 1
        le = text.find("\n", m.end())
        if le < 0: le = len(text)
        line = text[ls:le].strip()
        if is_comment_line(line, ext) or m.start() < 50:
            hits.append((ln, "known_token:" + m.group(0), line[:200]))
    return encoding, hits

def main():
    total = 0
    by_enc = {"utf-8": [], "gb18030": [], "binary": []}
    hit_files = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in files:
            if not f.lower().endswith(EXTS): continue
            path = os.path.join(base, f)
            total += 1
            ext = os.path.splitext(f)[1].lower()
            enc, hits = scan_file(path, ext)
            by_enc[enc].append(path)
            if hits: hit_files.append((path, hits))
    out = []
    out.append(f"scanned files: {total}")
    out.append(f"utf-8: {len(by_enc['utf-8'])}")
    out.append(f"gb18030 (non-utf-8): {len(by_enc['gb18030'])}")
    for p in by_enc["gb18030"]:
        out.append("  non-utf8: " + p)
    out.append(f"binary: {len(by_enc['binary'])}")
    out.append("")
    out.append(f"=== files with mojibake signatures: {len(hit_files)}")
    for path, hits in hit_files:
        out.append("--- " + path)
        for ln, name, line in hits[:20]:
            out.append(f"  L{ln} [{name}]")
            out.append(f"     | {line}")
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print(f"scanned={total} utf8={len(by_enc['utf-8'])} non_utf8={len(by_enc['gb18030'])} mojibake_files={len(hit_files)}")
    print("full report -> " + REPORT_PATH)
    return 0

if __name__ == "__main__":
    sys.exit(main())
