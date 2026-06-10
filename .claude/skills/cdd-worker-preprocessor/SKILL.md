---
name: cdd-worker-preprocessor
description: >-
  WORKER-Skill der CDD-Pipeline. Verrichtet die mechanische Schwerstarbeit an
  HTML-Prototypen: injiziert in jeden sichtbaren Knoten eine stabile cdd-id,
  erkennt Duplikate per Content-Hashing und liefert eine kompakte JSON-Struktur.
  Bewertet NICHTS (keine Atomic-Design-Einstufung). Verwende diesen Skill, wenn
  ein HTML-Prototyp dedupliziert/geparst, cdd-ids/data-agent-ids injiziert oder
  deduplicated-components.json erzeugt werden soll. Wird typischerweise vom
  cdd-manager als Schritt 0 aufgerufen.
license: MIT
---

# CDD Worker — Pre-Processing (Teilaufgabe 1)

**Rolle:** Worker (der „Muskel"). Du bist deterministisch und mechanisch. Du
liest das rohe HTML, der `cdd-manager` (das „Gehirn") tut es nicht — er hat nur
Token fuer kompaktes JSON. Deine einzige Aufgabe: HTML rein, Fakten-JSON raus.

> **Du beurteilst nichts.** Du sagst nicht, ob etwas ein Atom oder Molekuel ist.
> Das entscheidet der `cdd-manager`. Du lieferst nur messbare Struktur-Signale.

## Was du tust

Fuehre das gebuendelte Skript aus:

```bash
python .claude/skills/cdd-worker-preprocessor/scripts/deduplicate_and_parse.py \
    --prototype-dir <pfad-zum-prototyp-ordner> \
    --out-dir <pfad-fuer-output>
```

Das Skript erledigt drei Dinge:

1. **ID-Injektion (Traceability).** Jeder sichtbare HTML-Knoten bekommt
   `cdd-id="cdd-xxxxxxxx"` (== das „data-agent-id" der Abgabe). Die ID wird aus
   dem DOM-Pfad abgeleitet → **deterministisch und stabil** ueber Laeufe hinweg.
   Idempotent: vorhandene cdd-ids werden wiederverwendet.
2. **Deduplizierung (Content-Hashing)** auf drei Ebenen:
   - identische Dateien → `sha256` der Rohdatei
   - literal identische Elemente → `exactHash` (Skelett **inkl.** Text)
   - **strukturgleiche Bausteine** → `templateHash` (Skelett **ohne** Text)
3. **JSON-Output ohne Bewertung** → `deduplicated-components.json` mit
   `classification.category = null` plus indizierte HTML-Kopien.

## Output (relativ zu `--out-dir`)

- `indexed-prototypes/…` — die Prototypen MIT injizierten cdd-ids (= die ZIP-faehige,
  fuer die Konvertierung vorbereitete Fassung).
- `deduplicated-components.json` — die einzige Faktenquelle fuer den Manager.

### Die zwei Hashes (der Kern der Deduplizierung)

| Hash | enthaelt | wofuer |
| --- | --- | --- |
| `templateHash` | Tag + CSS-Klassen + Kind-Struktur, **OHNE Text** | gruppiert gleiche Bausteine mit anderem Text (z.B. dieselbe Card 12× mit anderem Titel) → **eine** Komponente |
| `exactHash` | dasselbe **MIT** Text | erkennt literal identische Knoten |

Pro `templateHash` entsteht **ein** Eintrag in `components[]` mit `occurrences`
und allen `instances`. Strukturgleiche Vorkommen werden so konsolidiert, bevor der
Manager ueberhaupt klassifiziert.

### Signale pro Komponente (neutrale Fakten, kein Urteil)

`tag`, `classList`, `childElementCount`, `childTags`,
`childComponentTemplateHashes` (Kompositions-Graph), `isInteractive`,
`isSectioning`, `maxDepthBelow`, `hasDirectText`, `textLength`.

Struktur des JSON: siehe `cdd-manager/references/deduplicated-components.template.json`.

## Vertrag mit dem Manager

Wenn du fertig bist, gib den Pfad der `deduplicated-components.json` und der
`indexed-prototypes/` an den `cdd-manager` zurueck. Klassifizierung, Konsolidierungs-
Entscheidungen und das Gedaechtnis (`workflow-progress.json`) sind **seine** Sache.

## Leitplanken

- Dependency-frei (nur Python-Standardbibliothek) — laeuft ohne `pip install`.
- Original-HTML byte-genau erhalten, nur das `cdd-id`-Attribut kommt hinzu.
- Niemals klassifizieren, niemals raten. Nur parsen, hashen, ausgeben.
