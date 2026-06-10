---
name: cdd-builder
description: >-
  WORKER/IMPLEMENTER-Skill der CDD-Pipeline. Generiert aus den vom cdd-manager
  klassifizierten und konsolidierten Daten die fertigen React-Native-Komponenten
  (.tsx). Liest deduplicated-components.json (mit Klassifizierung) und
  workflow-progress.json, baut pro Komponente genau einmal eine RN-Komponente in
  Dependency-Reihenfolge (Atome → Molekuele → Organismen) und meldet den Status
  zurueck. Verwende diesen Skill fuer "React-Native-Komponente generieren",
  "klassifizierte CDD-Komponenten implementieren", ".tsx aus der CDD-Analyse bauen".
license: MIT
---

# CDD Builder — Implementierung der React-Native-Komponenten

**Rolle:** Worker / Implementer. Du bist bewusst „dumm und guenstig": Du triffst
keine Atomic-Design-Entscheidungen und liest **kein HTML**. Du folgst stur der
Bauliste, die der `cdd-manager` dir gibt. Genau deshalb genuegt dafuer ein
leichtgewichtiges/guenstiges LLM.

## Eingabe (deine einzige Faktenquelle)

- `deduplicated-components.json` — mit ausgefuellter `classification`
  (`category`, `componentName`, `reactNative`).
- `workflow-progress.json` — Status + `dependencyGraph` + `dependsOn`/`usedBy`.

Mehr brauchst du nicht. `canonicalCddId` ist dein Anker; das indizierte HTML
darfst du bei Bedarf nur nachschlagen, aber nicht parsen.

## Was du baust

1. **Baureihenfolge: Dependency-First.** Baue zuerst Komponenten ohne offene
   `dependsOn` (Atome), dann Molekuele, dann Organismen. So existieren Kind-
   Komponenten als Imports, bevor ein Elternteil sie nutzt.
2. **Auswahl:** nur Komponenten mit `status: pending` oder `needs-review`.
   `implemented` ueberspringst du (Konsolidierung & Delta hat der Manager schon
   erledigt — eine Komponente pro `templateHash`, nie Duplikate).
3. **Pro Komponente genau EINE Datei.** `componentName` = Dateiname (PascalCase).
   Zielpfad aus `reactNative.targetPath` (wiederverwendet →
   `packages/shared-components/src/<Name>.tsx`).
4. **Props** aus den Instanz-Unterschieden (Text/`href` → Prop, z.B. `label`,
   `title`). Kind-Komponenten aus `dependsOn` werden importiert und gerendert.

## Web→Native-Regeln (damit du autark bist)

| `reactNative`-Primitive | Bauweise |
| --- | --- |
| `View` | Layout-Container; `style` aus dem Theme |
| `Text` | **jeder** sichtbare Text MUSS in `<Text>` |
| `Pressable` | Button/Link; Label als verschachteltes `<Text>`; `onPress`-Prop |
| `TextInput` | `type` → `keyboardType`/`secureTextEntry`, `placeholder`-Prop |
| `Image` | `source`-Prop |

Harte Regeln: kein `<div>`/`<span>`/className; nackter Text ist verboten (immer
`<Text>`); Styles ueber `StyleSheet.create`; nutze vorhandene Theme-Tokens, wenn
ein `packages/shared-components/.../theme` existiert.

## Skelett

Vorlage: `references/component.template.tsx`. Halte dich an Props-Interface +
`StyleSheet.create`.

## Rueckmeldung an den Manager

Nach dem Bauen einer Komponente setze in `workflow-progress.json`
`components[<templateId>].status = "implemented"` und `lastChangedRun`. Wenn alle
Komponenten der Bauliste erledigt sind, melde an den `cdd-manager` zurueck. Bei
`needs-review`-Kaskaden baust du **nur** die vom Manager markierten Komponenten neu
— nie den ganzen Prototyp.
