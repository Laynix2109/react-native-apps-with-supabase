---
name: cdd-manager
description: >-
  MANAGER/ORCHESTRATOR-Skill der CDD-Pipeline (Orchestrator-Worker-Muster).
  Steuert die Konvertierung eines HTML-Prototyps nach React Native: delegiert
  das Pre-Processing an cdd-worker-preprocessor, klassifiziert die Komponenten
  deterministisch nach Atomic Design (Atome/Molekuele/Organismen), konsolidiert
  Duplikate, pflegt das Gedaechtnis workflow-progress.json (Delta- & Dependency-
  Tracking) und uebergibt die Bauliste an cdd-builder. Verwende diesen Skill fuer
  "UI nach React Native konvertieren", "Atomic Design klassifizieren",
  "CDD-Analyse", "Komponenten konsolidieren", "Konvertierung orchestrieren".
license: MIT
---

# CDD Manager — Orchestrator, Klassifizierung & Checkpointing (Teilaufgabe 2 & 3)

**Rolle:** Manager (das „Gehirn"). Du koordinierst die Pipeline und triffst alle
*semantischen* Entscheidungen. Du liest **nie** rohes HTML — du arbeitest nur auf
kompaktem JSON. Schwerstarbeit delegierst du an Worker.

## Progressive Disclosure / Arbeitsteilung

LLMs haben Token-Limits. Deshalb drei spezialisierte Agenten mit je kleinem Kontext:

```
cdd-worker-preprocessor   →   cdd-manager (DU)   →   cdd-builder
  (parst, dedupliziert)        (klassifiziert,         (generiert die
   liefert Fakten-JSON)         konsolidiert,           React-Native-.tsx)
                                orchestriert,
                                Gedaechtnis)
```

Du siehst nie HTML, der Builder sieht nie HTML, der Worker klassifiziert nie.
Jeder Schritt haelt nur das, was er braucht.

---

## Pipeline — deine Schritte

### Schritt 0 — Pre-Processing delegieren
Rufe den **`cdd-worker-preprocessor`** auf (er fuehrt das Skript aus). Ergebnis:
`deduplicated-components.json` (Fakten) + `indexed-prototypes/` (HTML mit cdd-ids).
Du arbeitest ab jetzt **ausschliesslich** auf diesem JSON.

### Schritt 1 — Reihenfolge: Blaetter zuerst
Sortiere `components` aufsteigend nach `signals.maxDepthBelow` (post-order). So
sind die Kind-Bauteile bereits eingestuft, wenn du ein Eltern-Bauteil bewertest
und seine `childComponentTemplateHashes` nachschlaegst.

### Schritt 2 — Atomic-Design-Regeln (deterministisch, erste Regel gewinnt)

**Regel A — ATOM:** `signals.childElementCount == 0` (Blatt) ODER
(`signals.isInteractive` und `signals.maxDepthBelow <= 1`).
→ mappt auf genau **eine** RN-Primitive. Bsp.: `button`, `input`, `label`, `h1`-`h6`,
`p`, `span`, `a`, `img`, dekoratives Icon-`div`.

**Regel B — MOLEKÜL:** sonst, wenn **ALLE** Kind-Bauteile bereits **Atome** sind
→ flache Gruppe von Atomen. Bsp.: Formularfeld (`label`+`input`), Card-Header
(`title`+`badge`), Textblock.

**Regel C — ORGANISMUS:** sonst (mind. ein Kind ist Molekül/Organismus)
→ komponiert Gruppen. Bsp.: `form` mit Feldern + Button, Card-Liste, App-Bar,
eine Card mit eigenem Header-Molekül.

**Sonderfall Screen-Root:** `main`/`body` mit Klasse `…screen…` → Organismus mit
`role: "screen"` (wird als Screen/Container behandelt, nicht als wiederverwendbare
Komponente).

> Gleicher `templateHash` ⇒ **immer** gleiche Kategorie. Begruende jede Einstufung
> ueber konkrete `cdd-id`s, nie ueber vage Positionen → keine Halluzinationen.

### Schritt 3 — Web→Native Mapping
React Native kennt kein `<div>`/`<span>`. Trage je Komponente die Primitive ein:

| HTML | React Native |
| --- | --- |
| `div`, `section`, `header`, `nav`, `main`, `article`, `footer`, `ul`, `li` | `View` |
| `p`, `h1`–`h6`, `label`, `span`(Text), `small`, `strong` | `Text` |
| `button`, `a`(Aktion) | `Pressable` (Label als `<Text>`) |
| `input`, `textarea` | `TextInput` |
| `img` | `Image` |

### Schritt 4 — Konsolidierung (Teilaufgabe 3)
Nutze `duplicateGroups`. Jede Gruppe = **eine** Komponente. Nur die
`canonicalCddId` wird gebaut; alle weiteren Instanzen sind **Verwendungen**, deren
Unterschiede (Text, `href`) zu **Props** werden. → aus 7 `btn-primary` wird **ein**
`PrimaryButton` mit `label`-Prop, nicht 7 Komponenten. Vergib `componentName`
(PascalCase) und Zielpfad (wiederverwendet → `packages/shared-components/src/`).

### Schritt 5 — Gedaechtnis schreiben & an Builder uebergeben
Schreibe `workflow-progress.json` (Struktur: siehe
`references/workflow-progress.template.json`) und uebergib die **Bauliste**
(Komponenten mit `status: pending/needs-review`, in Dependency-Reihenfolge) an
den **`cdd-builder`**. Nach dessen Rueckmeldung setzt du `status: implemented`.

---

## workflow-progress.json — dein Checkpoint-System

Pflichtfelder: `currentState` (phase, Zaehler, lastRun) · `fileHashes` (sha256 je
Datei) · `components` (je `templateId`: category, componentName, reactNative,
canonicalCddId, occurrences, `dependsOn`, `usedBy`, templateHash, status) ·
`dependencyGraph` · `deltaLog`.

### Delta-Update-Protokoll — bei geaenderten Datei-Hashes
1. **Unveraenderte `sha256`** → Datei komplett ueberspringen, Komponenten bleiben
   `implemented` (kein Token-Verbrauch, kein Rebuild).
2. **Geaenderte Datei** → `templateHash`-Mengen diffen:
   - neuer `templateHash` → neue Komponente, `status: pending`.
   - `templateHash` weg → `status: deprecated`.
   - gleicher `templateHash`, nur `exactHash`/Instanzen anders → **nur Text/Inhalt**
     geaendert → **KEINE Neugenerierung** (Text ist ein Prop); nur Instanzen updaten.
   - gleich + gleiche Instanzen → unveraendert.
3. Kaskade anwenden (s.u.), Lauf in `deltaLog`, `lastRun` erhoehen.

### Dependency-Tracking (Bonus) — nur das Geaenderte neu bauen
Die `cdd-id` ist DOM-Pfad-basiert und damit stabil: eine Struktur-Aenderung
betrifft nur das Element + seine Vorfahren. Aendert sich der `templateHash` eines
**Atoms** (z.B. `PrimaryButton`), setze ueber die transitive `usedBy`-Huelle **nur**
die abhaengigen Komponenten (Molekül → Organismus) auf `status: needs-review`.
Alles andere bleibt `implemented`. → der `cdd-builder` generiert ausschliesslich
das tatsaechlich Betroffene neu (minimale Kosten).

---

## Uebergabe-Vertrag an cdd-builder

Pro zu bauender Komponente lieferst du: `componentName`, `category`, `reactNative`-
Primitive, `canonicalCddId` (Anker im indizierten HTML), `dependsOn` (was zuerst
existieren muss), Instanzen/Props. Mehr braucht ein guenstiges LLM nicht, um die
Komponente zu implementieren — ohne je das HTML zu sehen.
