#!/usr/bin/env python3
"""
deduplicate_and_parse.py  --  CDD Pre-Processing (Skill-Aufgabe 1)

Zweck (Heavy-Lifting am Dateisystem, damit das Kontext-Fenster der KI geschont wird):
  1. ID-Injektion (Traceability):
     Fuegt jedem sichtbaren HTML-Knoten ein stabiles, deterministisches Attribut
     `cdd-id="cdd-xxxxxxxx"` hinzu (alias des in den Deliverables genannten
     "data-agent-id"). Bereits vorhandene cdd-ids werden wiederverwendet (idempotent).
  2. Deduplizierung (Content-Hashing):
       - exact-duplicate Dateien  -> ueber sha256 der Rohdatei erkannt
       - exact-duplicate Elemente -> identische Markup-Subtrees (inkl. Text)
       - structural duplicates     -> gleiche Bausteine mit anderem Text
                                       (z.B. dieselbe Card 12x mit anderem Titel)
     Strukturelle Duplikate sind der Kern von Aufgabe 3: dutzende gleiche Cards/
     Buttons werden zu EINER Komponente konsolidiert; jede Instanz referenziert
     den kanonischen Knoten ueber dessen cdd-id.
  3. JSON-Output (ohne Bewertung):
     Das Skript klassifiziert NICHT (kein atom/molecule/organism). Es liefert nur
     deterministische Struktur-Signale. Die Atomic-Design-Einstufung trifft der
     Agent gemaess SKILL.md (Aufgabe 2).

Das Skript ist dependency-frei (nur Python-Standardbibliothek), damit es ueberall
ohne `pip install` laeuft.

Aufruf (input-agnostisch: funktioniert mit jedem HTML-Prototyp-Ordner):
  python .claude/skills/cdd-worker-preprocessor/scripts/deduplicate_and_parse.py \
      --prototype-dir <pfad-zum-prototyp-ordner> \
      --out-dir <pfad-fuer-output>

Outputs (relativ zu --out-dir):
  indexed-prototypes/<spiegelt die Prototyp-Struktur, mit injizierten cdd-ids>
  deduplicated-components.json   (Struktur: siehe references/deduplicated-components.template.json)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
from html.parser import HTMLParser

# --- Konfiguration -----------------------------------------------------------

ATTR_NAME = "cdd-id"  # injiziertes Traceability-Attribut (== "data-agent-id" der Angabe)

# Tags, die kein sichtbares UI-Element sind -> keine ID-Injektion, keine Komponente.
SKIP_TAGS = {
    "html", "head", "meta", "link", "title", "style", "script", "base", "noscript",
}

# Void-Elemente (kein schliessendes Tag) -> als self-closing behandeln.
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

# Tags, die fuer den Agenten als "interaktiv" gelten (Signal, keine Wertung).
INTERACTIVE_TAGS = {"button", "a", "input", "select", "textarea"}

# Sectioning / Container-Tags (Signal fuer potentielle Organismen).
SECTIONING_TAGS = {"section", "header", "nav", "main", "article", "aside", "footer", "form"}

_WS_RE = re.compile(r"\s+")


def _sha(text: str, length: int = 12) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def _collapse_ws(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


# --- DOM-Knoten --------------------------------------------------------------

class Node:
    __slots__ = (
        "tag", "attrs", "classlist", "existing_id",
        "start", "starttag_len", "end", "void",
        "parent", "children", "text_parts",
        "depth", "sibling_index",
        "cdd_id", "template_id", "template_hash", "exact_hash", "dom_path",
    )

    def __init__(self, tag, attrs, start, starttag_len, void):
        self.tag = tag
        self.attrs = attrs                      # dict name->value (first wins)
        self.classlist = (attrs.get("class") or "").split()
        self.existing_id = attrs.get(ATTR_NAME)  # idempotenz: vorhandene cdd-id
        self.start = start                      # abs. offset des '<'
        self.starttag_len = starttag_len        # len(get_starttag_text())
        self.end = None                         # abs. offset hinter dem schliessenden Tag
        self.void = void
        self.parent = None
        self.children = []                      # nur Element-Kinder (Node)
        self.text_parts = []                    # direkter Textinhalt
        self.depth = 0
        self.sibling_index = 1                  # 1-basiert je Tag-Name unter dem Parent
        self.cdd_id = None
        self.template_id = None
        self.template_hash = None
        self.exact_hash = None
        self.dom_path = ""

    @property
    def direct_text(self) -> str:
        return _collapse_ws("".join(self.text_parts))


# --- Parser ------------------------------------------------------------------

class DomParser(HTMLParser):
    """Baut einen leichten DOM-Baum mit absoluten Quell-Offsets auf."""

    def __init__(self, raw: str):
        super().__init__(convert_charrefs=False)
        self.raw = raw
        # Zeilen-Start-Offsets fuer (lineno, col) -> absolute Position.
        self._line_starts = [0]
        for i, ch in enumerate(raw):
            if ch == "\n":
                self._line_starts.append(i + 1)
        self.roots: list[Node] = []
        self._stack: list[Node] = []
        self.all_nodes: list[Node] = []

    def _abs(self) -> int:
        lineno, col = self.getpos()
        return self._line_starts[lineno - 1] + col

    def _attrs_to_dict(self, attrs):
        d = {}
        for name, value in attrs:
            if name not in d:
                d[name] = value if value is not None else ""
        return d

    def _open(self, tag, attrs, void):
        start = self._abs()
        starttag_len = len(self.get_starttag_text() or "")
        node = Node(tag, self._attrs_to_dict(attrs), start, starttag_len, void)
        parent = self._stack[-1] if self._stack else None
        node.parent = parent
        node.depth = (parent.depth + 1) if parent else 0
        if parent is not None:
            same_tag = [c for c in parent.children if c.tag == tag]
            node.sibling_index = len(same_tag) + 1
            parent.children.append(node)
        else:
            same_tag = [c for c in self.roots if c.tag == tag]
            node.sibling_index = len(same_tag) + 1
            self.roots.append(node)
        self.all_nodes.append(node)
        return node

    # -- HTMLParser-Callbacks --
    def handle_starttag(self, tag, attrs):
        if tag in VOID_TAGS:
            node = self._open(tag, attrs, void=True)
            node.end = node.start + node.starttag_len
        else:
            node = self._open(tag, attrs, void=False)
            self._stack.append(node)

    def handle_startendtag(self, tag, attrs):  # <input ... />
        node = self._open(tag, attrs, void=True)
        node.end = node.start + node.starttag_len

    def handle_endtag(self, tag):
        end_pos = self._abs()
        # Ende des schliessenden Tags = naechstes '>' nach end_pos.
        gt = self.raw.find(">", end_pos)
        close_end = (gt + 1) if gt != -1 else end_pos
        # Toleranz fuer ausgelassene/verschachtelte End-Tags: bis zum Match poppen.
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i].tag == tag:
                for j in range(len(self._stack) - 1, i - 1, -1):
                    n = self._stack.pop()
                    if n.end is None:
                        n.end = close_end if j == i else end_pos
                return
        # kein passendes offenes Tag -> ignorieren

    def handle_data(self, data):
        if self._stack and data.strip():
            self._stack[-1].text_parts.append(data)

    def close(self):
        super().close()
        # nicht geschlossene Knoten bis Dateiende ausdehnen
        for n in self._stack:
            if n.end is None:
                n.end = len(self.raw)
        self._stack.clear()


# --- Hashing / Signaturen ----------------------------------------------------

def _is_visible(node: Node) -> bool:
    return node.tag not in SKIP_TAGS


def _visible_children(node: Node):
    return [c for c in node.children if _is_visible(c)]


def template_signature(node: Node) -> str:
    """Skelett-Signatur: tag + sortierte class-Liste + Kind-Struktur.
    IGNORIERT Text, ids und sonstige Attribute -> gleiche Bausteine mit anderem
    Text bekommen dieselbe Signatur (Kern der strukturellen Deduplizierung)."""
    classes = ".".join(sorted(node.classlist))
    kids = "".join(template_signature(c) for c in _visible_children(node))
    return f"{node.tag}[{classes}]({kids})"


def exact_signature(node: Node) -> str:
    """Wie template_signature, aber MIT normalisiertem Text -> erkennt literal
    identische Subtrees (echte Duplikate inkl. gleichem Inhalt)."""
    classes = ".".join(sorted(node.classlist))
    kids = "".join(exact_signature(c) for c in _visible_children(node))
    return f"{node.tag}[{classes}]:{node.direct_text}({kids})"


def max_depth_below(node: Node) -> int:
    vis = _visible_children(node)
    if not vis:
        return 0
    return 1 + max(max_depth_below(c) for c in vis)


def text_sample(node: Node, limit: int = 60) -> str:
    txt = node.direct_text
    if not txt:
        # ersten nicht-leeren Kind-Text nehmen
        for c in _visible_children(node):
            t = text_sample(c, limit)
            if t:
                return t
        return ""
    return txt[:limit]


# --- Verarbeitung eines Prototyp-Ordners -------------------------------------

def find_html_files(root: str) -> list[str]:
    files = []
    for dirpath, _dirs, filenames in os.walk(root):
        for fn in sorted(filenames):
            if fn.lower().endswith((".html", ".htm")):
                files.append(os.path.join(dirpath, fn))
    return sorted(files)


def assign_cdd_id(node: Node, rel_path: str) -> str:
    """Deterministische, stabile ID. Aendert sich nur, wenn sich die strukturelle
    Position (dom_path) des Elements aendert -> ideal fuer Delta-Tracking."""
    if node.existing_id:
        return node.existing_id
    return "cdd-" + _sha(f"{rel_path}::{node.dom_path}", 8)


def build_dom_path(node: Node) -> str:
    parts = []
    cur = node
    while cur is not None:
        seg = cur.tag
        # Index nur anfuegen, wenn es Geschwister gleichen Tags gibt.
        siblings_scope = cur.parent.children if cur.parent else None
        if siblings_scope is not None:
            same = [c for c in siblings_scope if c.tag == cur.tag]
            if len(same) > 1:
                seg = f"{cur.tag}[{cur.sibling_index}]"
        parts.append(seg)
        cur = cur.parent
    return ">".join(reversed(parts))


def process_prototype(prototype_dir: str, out_dir: str) -> dict:
    prototype_dir = os.path.abspath(prototype_dir)
    out_dir = os.path.abspath(out_dir)
    indexed_dir = os.path.join(out_dir, "indexed-prototypes")
    os.makedirs(indexed_dir, exist_ok=True)

    html_files = find_html_files(prototype_dir)
    if not html_files:
        raise SystemExit(f"Keine HTML-Dateien unter {prototype_dir} gefunden.")

    files_report = []
    file_hash_seen: dict[str, str] = {}
    # Globale Sammlung aller sichtbaren Knoten ueber alle Dateien.
    all_records: list[dict] = []
    # Gruppierung nach template_hash (strukturelle Identitaet).
    template_groups: dict[str, list[dict]] = {}

    for path in html_files:
        rel_path = os.path.relpath(path, prototype_dir).replace(os.sep, "/")
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()

        file_sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        exact_dup_of = file_hash_seen.get(file_sha)
        if exact_dup_of is None:
            file_hash_seen[file_sha] = rel_path

        parser = DomParser(raw)
        parser.feed(raw)
        parser.close()

        visible = [n for n in parser.all_nodes if _is_visible(n)]

        # IDs, Pfade und Hashes vergeben.
        for node in visible:
            node.dom_path = build_dom_path(node)
            node.cdd_id = assign_cdd_id(node, rel_path)
            node.template_hash = _sha(template_signature(node))
            node.exact_hash = _sha(exact_signature(node))

        # Indizierte HTML-Kopie schreiben (cdd-id injizieren).
        indexed_html = inject_ids(raw, visible)
        out_path = os.path.join(indexed_dir, rel_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(indexed_html)

        # Records aufbauen.
        for node in visible:
            child_components = _visible_children(node)
            record = {
                "cddId": node.cdd_id,
                "file": rel_path,
                "tag": node.tag,
                "classList": node.classlist,
                "domPath": node.dom_path,
                "depth": node.depth,
                "templateHash": node.template_hash,
                "exactHash": node.exact_hash,
                "textSample": text_sample(node),
                "signals": {
                    "childElementCount": len(child_components),
                    "childTags": [c.tag for c in child_components],
                    "maxDepthBelow": max_depth_below(node),
                    "isInteractive": node.tag in INTERACTIVE_TAGS,
                    "isFormContainer": node.tag == "form",
                    "isSectioning": node.tag in SECTIONING_TAGS,
                    "hasDirectText": bool(node.direct_text),
                    "textLength": len(node.direct_text),
                },
                # Komposition (vom Agenten fuer molecule/organism-Regeln genutzt):
                "childComponentTemplateHashes": sorted({c.template_hash for c in child_components}),
                "_node": node,  # interne Referenz, vor Serialisierung entfernt
            }
            all_records.append(record)
            template_groups.setdefault(node.template_hash, []).append(record)

        files_report.append({
            "path": rel_path,
            "sha256": file_sha,
            "visibleElements": len(visible),
            "exactDuplicateOf": exact_dup_of,
        })

    components, duplicate_groups = build_components(template_groups)
    stats = {
        "files": len(files_report),
        "visibleElements": len(all_records),
        "uniqueTemplates": len(components),
        "duplicateGroups": len(duplicate_groups),
        "duplicateInstances": sum(g["occurrences"] - 1 for g in components if g["occurrences"] > 1),
    }

    report = {
        "$comment": (
            "Generiert von deduplicate_and_parse.py (Aufgabe 1). 'classification' ist "
            "bewusst leer (null) - die Atomic-Design-Einstufung trifft der Agent gemaess "
            "SKILL.md. Konsolidierung: pro 'templateHash' nur die 'canonicalCddId' "
            "implementieren; alle weiteren 'instances' referenzieren diese."
        ),
        "meta": {
            "generatedBy": "deduplicate_and_parse.py",
            "generatedAt": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "attribute": ATTR_NAME,
            "targetFramework": "react-native",
            "prototypeRoot": os.path.relpath(prototype_dir, os.getcwd()).replace(os.sep, "/"),
            "stats": stats,
        },
        "files": files_report,
        "duplicateGroups": duplicate_groups,
        "components": components,
    }
    return report, out_dir, indexed_dir, stats


def build_components(template_groups: dict[str, list[dict]]):
    """Erzeugt pro template_hash genau einen Komponenten-Eintrag (kanonisch =
    erste Instanz in Dokument-Reihenfolge) plus alle Instanzen."""
    components = []
    duplicate_groups = []
    # deterministische Reihenfolge: nach Datei+domPath der ersten Instanz
    ordered = sorted(
        template_groups.items(),
        key=lambda kv: (kv[1][0]["file"], kv[1][0]["domPath"]),
    )
    for idx, (thash, records) in enumerate(ordered, start=1):
        canonical = records[0]
        template_id = f"tmpl-{idx:03d}"
        instances = []
        for rec in records:
            instances.append({
                "cddId": rec["cddId"],
                "file": rec["file"],
                "domPath": rec["domPath"],
                "exactHash": rec["exactHash"],
                "isExactDuplicateOfCanonical": rec["exactHash"] == canonical["exactHash"],
                "textSample": rec["textSample"],
            })
        component = {
            "templateId": template_id,
            "templateHash": thash,
            "canonicalCddId": canonical["cddId"],
            "tag": canonical["tag"],
            "classList": canonical["classList"],
            "occurrences": len(records),
            "signals": canonical["signals"] | {
                "childComponentTemplateHashes": canonical["childComponentTemplateHashes"],
            },
            "classification": {
                "category": None,        # "atom" | "molecule" | "organism"  (Agent)
                "componentName": None,    # z.B. "PrimaryButton"            (Agent)
                "reactNative": None,      # z.B. "Pressable"                (Agent)
                "status": "pending",     # pending|classified|implemented   (Agent)
            },
            "instances": instances,
        }
        components.append(component)
        if len(records) > 1:
            duplicate_groups.append({
                "templateId": template_id,
                "templateHash": thash,
                "canonicalCddId": canonical["cddId"],
                "occurrences": len(records),
                "memberCddIds": [r["cddId"] for r in records],
            })
    return components, duplicate_groups


# --- ID-Injektion in den Rohtext --------------------------------------------

def inject_ids(raw: str, visible: list[Node]) -> str:
    """Fuegt ` cdd-id="..."` direkt hinter dem Tag-Namen ein. Arbeitet auf
    absoluten Offsets und wendet Einfuegungen von hinten nach vorne an, damit
    fruehere Offsets gueltig bleiben. Idempotent (vorhandene cdd-id -> skip)."""
    insertions = []  # (offset, text)
    for node in visible:
        if node.existing_id:
            continue  # schon markiert
        insert_at = node.start + 1 + len(node.tag)  # hinter '<' + tagname
        insertions.append((insert_at, f' {ATTR_NAME}="{node.cdd_id}"'))
    insertions.sort(key=lambda x: x[0], reverse=True)
    out = raw
    for offset, text in insertions:
        out = out[:offset] + text + out[offset:]
    return out


# --- Serialisierung ----------------------------------------------------------

def strip_internal(obj):
    """Entfernt interne '_node'-Referenzen vor dem JSON-Dump."""
    if isinstance(obj, dict):
        return {k: strip_internal(v) for k, v in obj.items() if k != "_node"}
    if isinstance(obj, list):
        return [strip_internal(v) for v in obj]
    return obj


def main(argv=None):
    ap = argparse.ArgumentParser(description="CDD Pre-Processing: ID-Injektion + Deduplizierung.")
    ap.add_argument("--prototype-dir", required=True,
                    help="Ordner mit den HTML-Prototypen, z.B. docs/ui/prototypes/workout-tracker")
    ap.add_argument("--out-dir", default="cdd-output",
                    help="Zielordner fuer indexed-prototypes/ und deduplicated-components.json")
    args = ap.parse_args(argv)

    report, out_dir, indexed_dir, stats = process_prototype(args.prototype_dir, args.out_dir)

    json_path = os.path.join(out_dir, "deduplicated-components.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(strip_internal(report), fh, ensure_ascii=False, indent=2)

    print("CDD Pre-Processing abgeschlossen.")
    print(f"  Dateien verarbeitet : {stats['files']}")
    print(f"  Sichtbare Knoten    : {stats['visibleElements']}")
    print(f"  Unique Templates    : {stats['uniqueTemplates']}")
    print(f"  Duplikat-Gruppen    : {stats['duplicateGroups']}")
    print(f"  Eingesparte Instanzen: {stats['duplicateInstances']}")
    print(f"  Indizierte HTML     : {os.path.relpath(indexed_dir, os.getcwd())}")
    print(f"  JSON-Output         : {os.path.relpath(json_path, os.getcwd())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
