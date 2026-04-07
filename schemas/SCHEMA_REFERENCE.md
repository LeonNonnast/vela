# Vela Schema Reference

> Vollständige Felddokumentation für alle YAML-Definitionen.
> Abgeleitet aus Pydantic-Modellen + JSON-Schema — Stand 2026-03-28.

---

## Vollständigkeit-Check: workflow.schema.yaml vs. Pydantic

| Feld | Im YAML-Schema | Im Pydantic-Modell | Status |
|---|---|---|---|
| `id`, `name`, `version`, `description` | ✅ | ✅ | OK |
| `params[].application` | ❌ fehlt | ✅ (`bool`, default `false`) | **Lücke** |
| `context.auto` | ✅ | ✅ | OK |
| `lifecycle.*` | ✅ | ✅ | OK |
| `on_error.*` | ✅ | ✅ | OK |
| `steps[].notes` | ✅ | ✅ | OK |
| `steps[].fetch` | ✅ | ✅ | OK |
| `tools[]` (Workflow-Level) | ✅ | ✅ | OK |
| `capture[].suggest` | ✅ | ✅ | OK |
| `steps[].delegate` | ✅ | ✅ | OK |

---

## DB-Speicherbarkeit

Alle drei Typen (Workflows, Agents, Resources) können in der DB gespeichert werden:

| Tabelle | Zweck |
|---|---|
| `ModuleSource` | Repräsentiert ein Modul (provider = `github` / `local` / `db`) |
| `CachedModuleFile` | Speichert den YAML-Inhalt als `content`-String + `file_type` + `file_path` |

**Provider-Verhalten:**
- `github` — YAML von GitHub API gefetcht, in `CachedModuleFile` gecacht
- `local` — YAML in DB gespeichert; zusätzlich Filesystem-Pfad zurückgegeben (für Claude)
- `db` — YAML ausschließlich in DB gespeichert, kein Filesystem

---

## WorkflowDefinition

Dateiname: `{id}@{version}.yaml` — z.B. `my-workflow@1.0.0.yaml`

| Feld | Typ | Required | Default | Beschreibung | Auswirkung |
|---|---|---|---|---|---|
| `id` | `string` `^[a-z0-9-]+$` | ✅ | — | Eindeutige ID, wird MCP-Prompt `vela_{id}` | Bestimmt Auffindbarkeit und MCP-Name |
| `version` | `string` semver | ❌ | `"1.0.0"` | Auch im Dateinamen kodiert | Mehrere Versionen koexistieren; neueste wird genutzt |
| `name` | `string` | ✅ | — | Anzeigename im MCP-Listing | Erscheint in Prompt-Überschriften |
| `description` | `string` | ❌ | `""` | Kurzbeschreibung für MCP-Auswahl | Angezeigt bei vela_list_workflows |
| `params` | `list[ParamDefinition]` | ❌ | `[]` | Workflow-Parameter | Konfigurieren den Run, erreichbar als `{{params.X}}` |
| `context` | `ContextAutoDefinition` | ❌ | `null` | Auto-Context-Quellen | MCP-Layer injiziert automatisch Kontext |
| `lifecycle` | `LifecycleDefinition` | ❌ | `null` | Laufzeit-Regeln | Auto-Archiv, Auto-Cancel, Pause-Erlaubnis |
| `tools` | `list[ToolRequirement]` | ❌ | `[]` | Externe MCP-Tools die dieser Workflow benötigt | Im Response als `required_tools` mitgeliefert; im Prompt als Übersicht angezeigt |
| `resources` | `list[ResourceReference]` | ❌ | `[]` | Workflow-weite Ressourcen | In alle Step-Prompts verfügbar (Step-Ressourcen überschreiben) |
| `steps` | `list[AnyStepDefinition]` | ✅ | — | Geordnete Step-Liste | Ausführungsreihenfolge; erster Step wird bei Start gesetzt |

---

## ParamDefinition

| Feld | Typ | Required | Default | Beschreibung | Auswirkung |
|---|---|---|---|---|---|
| `name` | `string` | ✅ | — | Key für `{{params.name}}` | Template-Zugriff in Prompts |
| `label` | `string` | ❌ | `null` | Anzeigename | UI-Label bei Elicitation |
| `description` | `string` | ❌ | `null` | Erläuterung | Tooltips, Dokumentation |
| `required` | `bool` | ❌ | `false` | Muss bei Start übergeben werden | Fehler wenn fehlend und kein Default |
| `default` | `Any` | ❌ | `null` | Fallback-Wert | Wird bei Run-Start gesetzt wenn Param fehlt |
| `identity` | `bool` | ❌ | `false` | Teil des eindeutigen Run-Keys | Gleiche identity-Params → gleicher Run (Resume statt Neu) |
| `application` | `bool` | ❌ | `false` | Applikations-Kontext-Param | Reserviert für MCP-Layer-Nutzung (noch nicht implementiert) |
| `resolve` | `bool` | ❌ | `false` | Wert aus Memories auflösen | MCP-Layer sucht bei Start in Memories nach dem Wert |

---

## ToolRequirement

Deklariert ein externes MCP-Tool, das der Workflow benötigt. Workflow-Level `tools` werden im Prompt als Übersicht angezeigt und im Response als `required_tools` mitgeliefert. Step-Level `tools` (einfache `list[string]`) referenzieren Tool-Namen aus dieser Liste.

| Feld | Typ | Required | Default | Beschreibung | Auswirkung |
|---|---|---|---|---|---|
| `name` | `string` | ✅ | — | Tool-Name wie vom MCP-Server exponiert | Muss dem tatsächlichen Tool-Namen entsprechen |
| `server` | `string` | ❌ | `null` | Connector-ID / MCP-Server-Namespace | Identifiziert den Server (z.B. `"github"`, `"jira"`) |
| `description` | `string` | ❌ | `null` | Warum der Workflow dieses Tool braucht | Im Prompt als Kontext angezeigt |
| `required` | `bool` | ❌ | `true` | Ob der Workflow ohne dieses Tool funktioniert | `false` = nice-to-have; im Prompt als [optional] markiert |

**Beispiel:**
```yaml
tools:
  - name: create_issue
    server: github
    description: GitHub Issues für Findings erstellen
  - name: search_code
    server: github
    required: false
    description: Optional — Code durchsuchen für Kontext
```

---

## LifecycleDefinition

| Feld | Typ | Required | Default | Beschreibung | Auswirkung |
|---|---|---|---|---|---|
| `auto_archive_after` | `string` (z.B. `"30d"`) | ❌ | `null` | Zeit bis Archivierung nach Abschluss | Hintergrundprozess räumt abgeschlossene Runs auf |
| `auto_cancel_after` | `string` (z.B. `"90d"`) | ❌ | `null` | Inaktivitäts-Timeout | Pausierte/aktive Runs werden nach Ablauf abgebrochen |
| `allow_pause` | `bool` | ❌ | `true` | Ob Run pausiert werden darf | Verhindert Unterbrechung bei kritischen Workflows |

---

## BaseStepDefinition (gemeinsam für alle Step-Typen)

| Feld | Typ | Required | Default | Beschreibung | Auswirkung |
|---|---|---|---|---|---|
| `id` | `string` | ✅ | — | Eindeutige ID innerhalb des Workflows | Ziel für `next`-Referenzen; Template-Zugriff via `{{steps.id.key}}` |
| `name` | `string` | ❌ | `null` | Anzeigename (z.B. `"Schritt 3/7 — Daten prüfen"`) | Erscheint in Prompt-Überschrift und Fortschrittsanzeige |
| `type` | `StepType` | ✅ | — | Step-Typ (siehe unten) | Bestimmt Engine-Verhalten vollständig |
| `prompt` | `string` | ❌ | `""` | Anweisung/Frage an User/Claude | Supports `{{params.X}}`, `{{steps.X.Y}}`, `{{state.X}}` |
| `depends_on` | `list[DependsOnDefinition]` | ❌ | `[]` | Felder aus vorherigen Steps | Injiziert Werte als Kontext-Block in Prompt; kein Blocking |
| `fetch` | `list[FetchDefinition]` | ❌ | `[]` | Server-seitige Daten vor Ausführung | Ergebnis via `{{fetch.key}}` im Prompt verfügbar |
| `tools` | `list[string]` | ❌ | `[]` | MCP-Tools für Claude in diesem Step | Einschränkung des Tool-Zugriffs pro Step |
| `capture` | `list[CaptureDefinition]` | ❌ | `[]` | Strukturierte Output-Felder | Schreibt Werte in `state_data`, erreichbar in späteren Steps |
| `next` | `string` | ❌ | `null` | Expliziter nächster Step (Step-ID) | Überschreibt sequenzielle Reihenfolge; bei Choice von `option.next` überschreibbar |
| `notes` | `bool` | ❌ | `true` | Notizen erlaubt | Ermöglicht `_notes`-Feld in State |
| `on_error` | `OnErrorDefinition` | ❌ | `null` | Fehlerbehandlung | Retry, Fallback-Step oder Abbruch |
| `resources` | `list[ResourceReference]` | ❌ | `[]` | Step-spezifische Ressourcen | Merged mit Workflow-Ressourcen (Step gewinnt bei Konflikt) |

---

## Step-Typen

### `freeform`
Freie Texteingabe. Keine zusätzlichen Felder.

**Einsatz:** Daten sammeln, Beschreibungen, beliebige Eingaben.

---

### `choice`

| Feld | Typ | Required | Default | Beschreibung | Auswirkung |
|---|---|---|---|---|---|
| `options` | `list[ChoiceOption]` | ❌ | `[]` | Auswahloptionen | User wählt eine — Output muss exakt dem `key` entsprechen |

#### ChoiceOption

| Feld | Typ | Required | Default | Beschreibung | Auswirkung |
|---|---|---|---|---|---|
| `key` | `string` | ✅ | — | Maschinenlesbarer Wert (Output) | Wird mit `step_output` verglichen für `next`-Routing |
| `label` | `string` | ✅ | — | Anzeigename | Erscheint in Prompt-Optionsliste |
| `description` | `string` | ❌ | `null` | Erläuterung | Erscheint hinter dem Label |
| `next` | `string` | ❌ | `null` | Step-ID bei Auswahl dieser Option | **Höchste Priorität** in `_resolve_next` |

---

### `confirm`
Ja/Nein-Bestätigung. Keine zusätzlichen Felder.

**Einsatz:** Zusammenfassungen bestätigen, irreversible Aktionen absichern.
**Hinweis:** Kein nativer Nein-Branch — bei Nein muss `next` explizit gesetzt werden oder ein `choice`-Step verwendet werden.

---

### `execute`

| Feld | Typ | Required | Default | Beschreibung | Auswirkung |
|---|---|---|---|---|---|
| `instructions` | `string` | ❌ | `null` | Detaillierte Ausführungsanweisungen für Claude | Ergänzt `prompt`; kein Engine-Sonderverhalten |
| `delegate` | `"subagent"` | ❌ | `null` | Delegierung an Sub-Agenten | Schema vorhanden, noch nicht implementiert |

**Einsatz:** Code ausführen, Files schreiben, Tools aufrufen, Berechnungen.

---

### `dialog`

| Feld | Typ | Required | Default | Beschreibung | Auswirkung |
|---|---|---|---|---|---|
| `mode` | `string` | ❌ | `null` | Vordefinierter Dialog-Modus | Liefert Standard-Phasendefinitionen wenn kein `phases` gesetzt |
| `goal` | `string` | ❌ | `null` | Übergeordnetes Ziel des Dialogs | Erscheint im Phase-Prompt-Header |
| `guidelines` | `list[string]` | ❌ | `[]` | Allgemeine Verhaltensrichtlinien | In jeden Phase-Prompt injiziert |
| `phases` | `list[DialogPhaseDefinition]` | ❌ | `[]` | Explizite Phasendefinitionen | **Überschreibt `mode`** wenn vorhanden |

#### Verfügbare `mode`-Werte

| Mode | Phasen |
|---|---|
| `brainstorming` | Diverge → Converge → Synthesize |
| `requirements` | Context → Questions → Prioritize → Specify |
| `planning` | Goals → Breakdown → Dependencies → Approval |
| `review` | Understand → Evaluate → Decide |
| `freeform` | Keine Phasen — nur goal + guidelines |

#### DialogPhaseDefinition

| Feld | Typ | Required | Default | Beschreibung |
|---|---|---|---|---|
| `id` | `string` | ✅ | — | Eindeutige Phasen-ID |
| `name` | `string` | ❌ | `null` | Anzeigename |
| `guideline` | `string` | ✅ | — | Anweisung für diese Phase |

---

### `workflow` (Sub-Workflow)

| Feld | Typ | Required | Default | Beschreibung | Auswirkung |
|---|---|---|---|---|---|
| `workflow_ref` | `string` | ❌ | `null` | ID des aufzurufenden Workflows | Parent-Run wird PAUSED; Sub-Workflow wird gestartet |
| `params_mapping` | `dict[string, string]` | ❌ | `{}` | `{sub_param: parent_state_key}` | Übergibt State-Werte als Parameter an Sub-Workflow |

---

### `mcp_call`

| Feld | Typ | Required | Default | Beschreibung | Auswirkung |
|---|---|---|---|---|---|
| `mcp_tool` | `string` | ❌ | `null` | Tool-Name auf dem MCP-Server | Wird server-seitig **vor** `advance()` ausgeführt |
| `mcp_source` | `string` | ❌ | `null` | MCP-Server-Namespace | Bestimmt welcher Server angesprochen wird |
| `mcp_params` | `dict` | ❌ | `{}` | Parameter für den Tool-Aufruf | Supports Template-Auflösung |

**Wichtig:** Die Engine führt keinen MCP-Call aus — der MCP-Layer führt den Call aus und übergibt das Ergebnis als `step_output`.

---

## CaptureDefinition

| Feld | Typ | Required | Default | Beschreibung | Auswirkung |
|---|---|---|---|---|---|
| `key` | `string` | ✅ | — | State-Key für den Wert | Erreichbar als `{{steps.step_id.key}}` in späteren Steps |
| `label` | `string` | ❌ | `null` | Anzeigename in Elicitation-UI | Label beim Nachfragen |
| `type` | `string` | ❌ | `"string"` | `string` / `boolean` / `date` / `number` | Validation bei Elicitation |
| `required` | `bool` | ❌ | `false` | Muss vorhanden sein | Löst Elicitation aus wenn fehlend (je nach `elicit`) |
| `source` | `string` | ❌ | `"output"` | `output` = aus step_output; `param` = aus Workflow-Params | Bestimmt Quelle des Wertes |
| `input` | `string` | ❌ | `null` | `text` / `number` / `boolean` / `select` / `multi-select` / `confirm` | Steuert Elicitation-UI; ohne `input` nur Validation |
| `options` | `list[CaptureOption]` | ❌ | `[]` | Statische Optionen für `select`/`multi-select` | Liste der auswählbaren Werte |
| `suggest` | `bool` | ❌ | `false` | Claude generiert Optionen dynamisch | Nur sinnvoll bei `select`/`multi-select` |
| `placeholder` | `string` | ❌ | `null` | Platzhalter-Text | UI-Hinweis in Eingabefeld |
| `default` | `Any` | ❌ | `null` | Vorausgewählter Wert | Wird genutzt wenn kein Output vorhanden |
| `elicit` | `string` | ❌ | `"if_missing"` | `always` / `if_missing` / `never` | Steuert wann nachgefragt wird |

#### `elicit`-Verhalten

| Wert | Verhalten |
|---|---|
| `always` | UI immer zeigen, auch wenn Wert bereits vorhanden (z.B. zur Bestätigung) |
| `if_missing` | Nur nachfragen wenn Feld fehlt oder ungültig |
| `never` | Nie nachfragen — nur validieren; fehlende required-Felder führen zu Fehler |

---

## AgentDefinition

Dateiname: `{id}.yaml` — z.B. `code-reviewer.yaml`

| Feld | Typ | Required | Default | Beschreibung | Auswirkung |
|---|---|---|---|---|---|
| `id` | `string` | ✅ | — | Eindeutige Agent-ID | MCP-Prompt-Name |
| `name` | `string` | ✅ | — | Anzeigename | Erscheint in MCP-Listing |
| `persona` | `string` | ❌ | `""` | Persona-Text (role=assistant) | In **jeden** Step-Prompt des Agents injiziert; Schreibweise: `"Du bist..."` (nie `"Ich bin..."`) |
| `greeting` | `string` | ❌ | `null` | Begrüßungs-Anweisung (role=user) | Sagt dem LLM **wie** es grüßen soll, nicht der Text selbst |
| `workflows` | `list[string]` | ❌ | `[]` | Workflow-IDs die dieser Agent nutzt | Sichtbarkeit und Kontextualisierung |
| `tools` | `list[string]` | ❌ | `[]` | MCP-Tools immer verfügbar | Dauerhafter Tool-Zugriff über alle Steps |

---

## ResourceDefinition

Dateiname: `{id}.yaml` — z.B. `volere-template.yaml`

| Feld | Typ | Required | Default | Beschreibung | Auswirkung |
|---|---|---|---|---|---|
| `id` | `string` | ✅ | — | Eindeutige Resource-ID | Referenziert via `resources[].ref` in Workflows/Steps |
| `name` | `string` | ✅ | — | Anzeigename | Erscheint in MCP-Resource-Listing |
| `type` | `ResourceType` | ✅ | — | Typ (siehe unten) | Kategorisierung; beeinflusst MCP-URI |
| `description` | `string` | ❌ | `""` | Kurzbeschreibung | URI-Referenz-Anzeige im Prompt |
| `content` | `string` | ❌ | `""` | Eigentlicher Inhalt | Inline oder als URI verfügbar |
| `mime_type` | `string` | ❌ | `"text/plain"` | MIME-Typ des Inhalts | z.B. `"application/json"`, `"text/markdown"` |
| `tags` | `list[string]` | ❌ | `[]` | Freitext-Tags | Für Suche und Filterung |
| `uri_pattern` | `string` | ❌ | `null` | Eigene URI-Vorlage | Überschreibt Standard-URI `vela://{type}/{id}` |

#### `type`-Werte

| Wert | Verwendung |
|---|---|
| `schema` | JSON/YAML-Schemata, Validierungsregeln |
| `example` | Beispieldaten, Muster-Output |
| `scaffold` | Code-Templates, Boilerplates |
| `skill` | Wiederverwendbare Fähigkeiten/Anweisungen |
| `convention` | Code-Style, Namensregeln, Team-Konventionen |
| `reference` | Referenzmaterial, externe Docs |

#### Inline vs. URI-Referenz (ResourceReference)

| `inline` | Verhalten |
|---|---|
| `true` | Inhalt direkt in Prompt eingebettet |
| `false` | URI-Referenz — Claude kann mit `read_resource()` laden |
| omit / `null` | Auto: inline wenn Inhalt < 500 Zeichen, sonst URI |

---

## DependsOnDefinition

| Feld | Typ | Required | Beschreibung |
|---|---|---|---|
| `step` | `string` | ✅ | ID des vorherigen Steps |
| `fields` | `list[string]` | ✅ | Capture-Keys aus diesem Step die injiziert werden sollen |

**Wichtig:** Rein deklarativ — kein Blocking. Nur Prompt-Injection.

---

## OnErrorDefinition

| Feld | Typ | Required | Default | Beschreibung |
|---|---|---|---|---|
| `retry` | `int` | ❌ | `0` | Anzahl Wiederholungsversuche |
| `fallback` | `string` | ❌ | `null` | Step-ID als Fallback bei Fehler |
| `abort` | `bool` | ❌ | `false` | Workflow abbrechen bei Fehler |
| `message` | `string` | ❌ | `null` | Fehlermeldung für User |

**Priorität:** retry > fallback > abort
