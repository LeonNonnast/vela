# Vela Workflow Execution Logic

> Analysiert aus Engine-Code — Stand 2026-03-28
> Quellen: `packages/vela-sdk/src/vela_sdk/engine/`

---

## 1. NEXT-Logik — Wie bestimmt die Engine den nächsten Step?

### Prioritätsreihenfolge (`_resolve_next`)

```
1. choice option.next  (nur bei type=choice, wenn output == option.key und option.next gesetzt)
2. step.next           (explizit im YAML gesetzt)
3. sequenziell         (nächster Step in der steps-Array-Reihenfolge)
4. None                → Workflow completed
```

### Code (workflow_engine.py, `_resolve_next`)

```python
def _resolve_next(current_step, output, workflow_def):
    # 1. Choice branching
    if current_step.type == CHOICE and output and current_step.options:
        for opt in current_step.options:
            if opt.key == output and opt.next:
                return opt.next

    # 2. Explicit next
    if current_step.next:
        return current_step.next

    # 3. Sequential fallback
    step_ids = [s.id for s in workflow_def.steps]
    idx = step_ids.index(current_step.id)
    if idx + 1 < len(step_ids):
        return step_ids[idx + 1]

    return None  # → Workflow complete
```

### Wichtige Konsequenzen

| Szenario | Verhalten |
|---|---|
| Choice ohne `option.next` | Fällt auf `step.next` oder sequenziell durch |
| Choice mit `option.next` nur auf einigen Optionen | Optionen ohne `next` → sequenziell |
| `step.next` gesetzt UND Choice-Option hat `next` | Option.next **gewinnt** |
| Letzter Step ohne `next` | Workflow wird als COMPLETED markiert |
| `next` zeigt auf nicht-existente ID | `_get_step` gibt None → Workflow completed |
| Back-Edge (`next: früherer-step`) | Funktioniert — echter Loop möglich |

---

## 2. Step-Typen — Engine-Verhalten im Detail

### `freeform`
- User/Claude gibt Freitext ein
- Output wird per `_parse_step_output` in `state_data` geschrieben (via `capture`)
- Weiterleitung per `_resolve_next`

### `choice`
- User wählt eine Option — output = `option.key`
- `_resolve_next` prüft zuerst ob die gewählte Option ein `next` hat
- Wenn kein `option.next`: fällt auf `step.next` oder sequenziell durch
- Achtung: Der Output muss exakt dem `key` entsprechen (case-sensitive)

### `confirm`
- Verhält sich wie `freeform` in der Engine
- Kein spezieller Branching-Code — `next` muss explizit gesetzt werden
- Typisch: `next` bei Ja-Bestätigung, kein eigenes "Nein"-Routing

### `execute`
- Claude führt Aktionen aus (Tools, Code, etc.)
- Engine-seitig identisch mit `freeform`: verarbeitet Output + Captures, dann `_resolve_next`
- Das `instructions`-Feld wird **nicht** von der Engine ausgewertet — es ist Prompt-Content für Claude
- `delegate: subagent` ist im Schema vorhanden, aber in der Engine noch nicht implementiert

### `dialog`
- Hat **eigene State-Machine** via `DialogHandler`
- Interne Zustände in `state_data`: `_dialog_phase` (aktuelle Phase-ID), `_dialog_phases_output` (Dict phase_id → output)
- **Phase-Fortschritt:**
  1. Erster `advance`-Aufruf (kein `_dialog_phase`): initialisiert Phase 1, gibt Phase-Prompt zurück
  2. Jeder weitere `advance`: speichert Output der aktuellen Phase, rückt zu nächster Phase vor
  3. Nach letzter Phase: merged alle Phase-Outputs, schreibt in Captures, ruft `_resolve_next` auf
- Phasen-Quelle: explizite `phases` überschreiben `mode`-Lookup
- Wenn keine Phasen definiert: verhält sich wie `freeform`

```
Dialog-State-Transitions:
  advance() ──► kein _dialog_phase → Phase 1 initialisieren → Prompt zurückgeben
  advance() ──► Phase 1 aktiv     → Phase 2 → Prompt zurückgeben
  advance() ──► letzte Phase      → merge outputs → next step
```

### `workflow` (Sub-Workflow)
- Engine **pausiert** den Parent-Run (`PAUSED`)
- Gibt `AdvanceResult(sub_workflow_ref=..., sub_workflow_params=...)` zurück
- MCP-Layer (`WorkflowModule._start_sub_workflow`) startet automatisch den Child-Run
- MCP-Layer (`WorkflowModule._resume_parent`) resumt automatisch den Parent wenn Child completed
- Funktioniert rekursiv (Sub-Sub-Workflows)
- `params_mapping` bildet Parent-State-Keys auf Sub-Workflow-Param-Keys ab

### `mcp_call`
- **Kein spezieller Engine-Code** — wird wie `freeform` behandelt
- Die eigentliche MCP-Tool-Ausführung geschieht **server-seitig vor** dem `advance()`-Aufruf
- `mcp_tool`, `mcp_source`, `mcp_params` werden vom MCP-Layer ausgewertet, nicht von der Engine
- Engine sieht nur das Ergebnis im `step_output`

---

## 3. State-Management

### State-Aufbau

```
state_data: dict[str, Any]  # flacher Key-Value Store

Schreibquellen:
  - capture[].key       ← aus step_output via _parse_step_output
  - _notes              ← aus notes-Parameter von advance()
  - _dialog_phase       ← interner Dialog-Tracking-Key
  - _dialog_phases_output ← Dict der Dialog-Phase-Outputs
  - _dialog_result      ← zusammengeführter Dialog-Output
```

### Capture-Parsing (`_parse_step_output`)

```
step_output ist JSON-Dict:
  → extrahiert pro capture.key den passenden Wert
  → fehlt key im JSON: schreibt gesamten output-String als Fallback

step_output ist plain String + 1 Capture:
  → schreibt String direkt für diesen key

step_output ist plain String + N Captures:
  → schreibt gesamten String für JEDEN key (alle bekommen dasselbe)
```

### Template-Kontext (`build_template_context`)

```
{{params.X}}           → run.params[X]
{{steps.step_id.key}}  → state_data[key] (wenn step capture[key] definiert hat)
{{state.key}}          → state_data[key] (direkter Zugriff)
{{fetch.key}}          → state_data[key] (nach server-seitigem fetch)
```

### `depends_on` — nur Prompt-Injektion, kein Blocking

- Prüft ob Felder im State vorhanden sind (`validate_depends_on`)
- Injiziert vorhandene Werte als Kontext-Block in den Prompt
- **Blockiert keinen Step** — rein deklarativ
- Fehlende Felder: werden als `(nicht erfasst)` angezeigt

### `params` → State

- Werden bei Run-Start in `run.params` gespeichert
- `identity: true` → wird für Run-Deduplication verwendet
- `resolve: true` → Engine sucht bei Start in Memories nach diesem Wert (Feature-Flag, Implementierung im MCP-Layer)

---

## 4. Run-Lifecycle

```
start_or_resume()
  ├─ identity_params vorhanden? → suche existing run
  │    └─ gefunden → return (existing_run, is_new=False)
  └─ neu anlegen
       ├─ resolve defaults
       ├─ store.create_run(first_step = steps[0].id)
       └─ return (new_run, is_new=True)

advance()
  ├─ status != ACTIVE/PAUSED → return completed=True
  ├─ current_step == None    → COMPLETED
  ├─ type == DIALOG          → DialogHandler.advance_dialog()
  ├─ type == WORKFLOW         → PAUSED + sub_workflow_ref
  ├─ next_step_id vorhanden  → update_step(next_step_id) + assemble_prompt
  └─ kein next               → COMPLETED
```

---

## 5. Identifizierte Lücken / Offene Punkte

| # | Thema | Beschreibung | Kritikalität |
|---|---|---|---|
| 1 | `delegate: subagent` | Im Schema vorhanden, Engine und MCP-Layer ignorieren es | Niedrig (Feature-Flag, nicht implementiert) |
| 2 | `mcp_call` Ausführung | Engine führt keinen MCP-Call aus — Claude/Agent ruft das Tool selbst auf; kein spezieller MCP-Layer-Code | Dokumentationslücke |
| 3 | `choice` ohne `next` | Wenn keine Option ein `next` hat und kein `step.next`: fällt sequenziell durch (bewusstes Design) | Niedrig |
| 4 | `_resolve_next` bei ungültiger ID | Zeigt auf nicht-existente Step-ID → Workflow completed statt Fehler | Mittel — `vela_validate` sollte prüfen |
| 5 | `confirm` Nein-Routing | Kein nativer Nein-Branch — Konvention: `choice` verwenden oder `next` explizit setzen | Dokumentationslücke |
| 6 | `context.auto` | Im Schema definiert (`active_project`, `recent_memories`, etc.) — nicht implementiert | Niedrig |

---

## 6. Empfehlungen

1. **Sub-Workflow-Resume dokumentieren** — im `WorkflowModule` nachvollziehen wie der Parent nach Abschluss des Sub-Workflows fortgesetzt wird
2. **`choice` ohne `next`-Optionen absichern** — in Validation prüfen oder in Docs als Antipattern markieren
3. **Ungültige `next`-IDs validieren** — `vela_validate` sollte prüfen ob alle referenzierten Step-IDs existieren
4. **`mcp_call`-Ausführungsreihenfolge dokumentieren** — im YAML-Schema klarstellen dass der MCP-Call vor `advance()` erfolgt
