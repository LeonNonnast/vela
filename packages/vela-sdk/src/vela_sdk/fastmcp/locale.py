"""Locale system for user-facing strings in the vela-sdk."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Locale:
    """All user-facing strings used by the FastMCP integration layer."""

    # --- response_builder.py: build_next_action ---
    workflow_completed: str
    already_captured: str
    still_open: str

    # Execute step
    execute_task_then_call: str  # {prefix_tag}, {tool_name}, {run_id}, {partial_hint}
    execute_prefix_tag: str  # "[AUTOMATION MODE] " — only used when automation=True

    # Dialog step
    dialog_auto_start: str  # {tool_name}, {run_id}
    dialog_auto_process: str  # {tool_name}, {run_id}
    dialog_start: str  # {tool_name}, {run_id}
    dialog_converse: str  # {tool_name}, {run_id}

    # Elicitable captures
    elicit_auto: str  # {tool_name}, {run_id}, {partial_hint}
    elicit_manual: str  # {tool_name}, {run_id}, {partial_hint}

    # Choice step
    choice_auto: str  # {tool_name}, {run_id}, {options_str}
    choice_manual: str  # {tool_name}, {run_id}, {options_str}

    # Confirm step
    confirm_auto: str  # {tool_name}, {run_id}
    confirm_manual: str  # {tool_name}, {run_id}

    # Workflow (sub-workflow) step
    sub_workflow_start: str  # {wf_ref}, {tool_name}, {run_id}
    sub_workflow_active_runs_hint: str  # {count}
    sub_workflow_enriched_next_action: str  # {wf_ref}, {param_lines}, {active_hint}, {run_id}

    # Fallback (default input)
    fallback_auto: str  # {tool_name}, {run_id}, {partial_hint}
    fallback_manual: str  # {tool_name}, {run_id}, {partial_hint}

    # --- response_builder.py: build_run_options ---
    new_session: str

    # --- session_elicitor.py ---
    session_choice_message: str  # {wf_name}

    # --- auto_advance.py: elicit_step_captures ---
    current_value_hint: str  # {existing_value}

    # --- integration.py ---
    workflow_start_cancelled: str

    # Prompt: resumed session headings
    prompt_resumed_session: str
    prompt_run_id: str
    prompt_current_step: str
    prompt_parameters: str
    prompt_captured_data: str  # heading for captured data
    prompt_still_open: str  # "Noch offen: {keys}"
    prompt_next_action: str  # heading

    # Prompt: new workflow next action
    prompt_call_advance_with_params: str  # {tool_name}, {wf_id}, {params_json}
    prompt_call_advance: str  # {tool_name}, {wf_id}

    # Prompt: auto-mode instructions
    prompt_auto_mode: str  # {tool_name}

    @classmethod
    def en(cls) -> "Locale":
        """English locale (default)."""
        return cls(
            workflow_completed="Workflow completed. No further action needed.",
            already_captured=" Already captured: {captured_json}. Still open: {missing_keys}.",
            still_open="Still open",

            execute_prefix_tag="[AUTOMATION MODE] ",
            execute_task_then_call=(
                "{prefix_tag}Execute the task in the prompt, then IMMEDIATELY call "
                "`{tool_name}(run_id=\"{run_id}\", "
                "output=\"<your summary>\")`.{partial_hint}"
            ),

            dialog_auto_start=(
                "[AUTOMATION MODE] Start the dialog autonomously. "
                "Call `{tool_name}(run_id=\"{run_id}\")` immediately. "
                "The engine will deliver the first phase — process it without user input."
            ),
            dialog_auto_process=(
                "[AUTOMATION MODE] Process the dialog phase from the prompt autonomously. "
                "Synthesize a response from the available context. Then immediately call "
                "`{tool_name}(run_id=\"{run_id}\", "
                "output=\"<your summary>\")`."),
            dialog_start=(
                "Call `{tool_name}(run_id=\"{run_id}\")` "
                "to start the dialog. The engine will deliver the first phase with instructions."
            ),
            dialog_converse=(
                "Have a conversation with the user according to the phase instructions in the prompt. "
                "When the phase is complete, summarize the result and call "
                "`{tool_name}(run_id=\"{run_id}\", "
                "output=\"<summary>\")`."),

            elicit_auto=(
                "[AUTOMATION MODE] Call `{tool_name}(run_id=\"{run_id}\")` immediately. "
                "Only required captures will be collected via elicitation dialog — "
                "optional captures will be skipped.{partial_hint}"
            ),
            elicit_manual=(
                "Call `{tool_name}(run_id=\"{run_id}\")` NOW. "
                "The engine will ask the user automatically via elicitation dialog — "
                "do NOT ask questions yourself.{partial_hint}"
            ),

            choice_auto=(
                "[AUTOMATION MODE] Choose the most suitable option based on the workflow context. "
                "Valid values: {options_str}. "
                "Call `{tool_name}(run_id=\"{run_id}\", "
                "output=\"<chosen key>\")` immediately."
            ),
            choice_manual=(
                "Show the user the options from the prompt. "
                "Then call `{tool_name}(run_id=\"{run_id}\", "
                "output=\"<chosen key>\")`. "
                "Valid values: {options_str}."
            ),

            confirm_auto=(
                "[AUTOMATION MODE] Check the confirmation autonomously based on the prompt. "
                "Call `{tool_name}(run_id=\"{run_id}\", output=\"confirmed\")`, "
                "unless the proposed action is obviously wrong."
            ),
            confirm_manual=(
                "Show the user the prompt and ask for confirmation. "
                "Then call `{tool_name}(run_id=\"{run_id}\", "
                "output=\"confirmed\")` or `output=\"rejected\"`."
            ),

            sub_workflow_start=(
                "Sub-workflow `{wf_ref}` is starting. "
                "Check `sub_workflow.params` for parameters (required, identity, defaults, resolved_value). "
                "Check `sub_workflow.active_runs` — RESUME if identity parameters match! "
                "Call `{tool_name}(run_id=\"{run_id}\")`."
            ),

            sub_workflow_active_runs_hint=(
                "\n\nWARNING: {count} active run(s) found! "
                "Check if identity parameters match — then RESUME instead of starting a new run."
            ),
            sub_workflow_enriched_next_action=(
                "Sub-workflow `{wf_ref}` is starting.\n"
                "Parameters:\n{param_lines}{active_hint}\n\n"
                "Call `{tool_name}(run_id=\"{run_id}\")` to start the sub-workflow."
            ),

            fallback_auto=(
                "[AUTOMATION MODE] Provide the input autonomously from the workflow context. "
                "Call `{tool_name}(run_id=\"{run_id}\", "
                "output=\"<input>\")` immediately.{partial_hint}"
            ),
            fallback_manual=(
                "Collect the input from the user, then call "
                "`{tool_name}(run_id=\"{run_id}\", "
                "output=\"<input>\")`.{partial_hint}"
            ),

            new_session="Start new session",

            session_choice_message="Workflow '{wf_name}' — Choose an active session or start a new one:",

            current_value_hint=" [current: {existing_value}]",

            workflow_start_cancelled="Workflow start cancelled.",

            prompt_resumed_session="## Resumed Session",
            prompt_run_id="- **Run ID:** `{run_id}`",
            prompt_current_step="- **Current Step:** {step_label}",
            prompt_parameters="- **Parameters:** {param_str}",
            prompt_captured_data="### Already captured data (current step)",
            prompt_still_open="### Still open: {keys}",
            prompt_next_action="## Next Action",

            prompt_call_advance_with_params=(
                "Call `{tool_name}` with "
                "`workflow_id=\"{wf_id}\"` and `params='{params_json}'` "
                "to start the workflow."
            ),
            prompt_call_advance=(
                "Call `{tool_name}` with "
                "`workflow_id=\"{wf_id}\"` to start the workflow."
            ),

            prompt_auto_mode=(
                "## Automatic Workflow Mode\n"
                "- Call `{tool_name}` and follow the `next_action` in the response **IMMEDIATELY**.\n"
                "- Do **NOT** ask the user for permission — the engine controls the dialog via elicitation.\n"
                "- For execute steps: Perform the task and then immediately call advance.\n"
                "- Repeat until the workflow is completed."
            ),
        )

    @classmethod
    def de(cls) -> "Locale":
        """German locale (original production strings)."""
        return cls(
            workflow_completed="Workflow abgeschlossen. Keine weitere Aktion nötig.",
            already_captured=" Bereits erfasst: {captured_json}. Noch offen: {missing_keys}.",
            still_open="Noch offen",

            execute_prefix_tag="[AUTOMATION MODE] ",
            execute_task_then_call=(
                "{prefix_tag}Führe die Aufgabe im Prompt aus, dann rufe SOFORT "
                "`{tool_name}(run_id=\"{run_id}\", "
                "output=\"<deine Zusammenfassung>\")` auf.{partial_hint}"
            ),

            dialog_auto_start=(
                "[AUTOMATION MODE] Starte den Dialog autonom. "
                "Rufe sofort `{tool_name}(run_id=\"{run_id}\")` auf. "
                "Der Engine liefert die erste Phase — verarbeite sie ohne User-Eingabe."
            ),
            dialog_auto_process=(
                "[AUTOMATION MODE] Verarbeite die Dialog-Phase aus dem Prompt autonom. "
                "Synthetisiere eine Antwort aus dem verfügbaren Kontext. Rufe dann sofort "
                "`{tool_name}(run_id=\"{run_id}\", "
                "output=\"<deine Zusammenfassung>\")` auf."
            ),
            dialog_start=(
                "Rufe `{tool_name}(run_id=\"{run_id}\")` auf "
                "um den Dialog zu starten. Der Engine liefert die erste Phase mit Anweisungen."
            ),
            dialog_converse=(
                "Führe ein Gespräch mit dem User gemäß der Phase-Anweisung im Prompt. "
                "Wenn die Phase abgeschlossen ist, fasse das Ergebnis zusammen und rufe "
                "`{tool_name}(run_id=\"{run_id}\", "
                "output=\"<Zusammenfassung>\")` auf."
            ),

            elicit_auto=(
                "[AUTOMATION MODE] Rufe sofort `{tool_name}(run_id=\"{run_id}\")` auf. "
                "Nur required Captures werden per Elicitation-Dialog abgefragt — "
                "optionale Captures werden übersprungen.{partial_hint}"
            ),
            elicit_manual=(
                "Rufe JETZT `{tool_name}(run_id=\"{run_id}\")` auf. "
                "Der Engine fragt den User automatisch per Elicitation-Dialog — "
                "stelle KEINE eigenen Fragen.{partial_hint}"
            ),

            choice_auto=(
                "[AUTOMATION MODE] Wähle die passendste Option basierend auf dem Workflow-Kontext. "
                "Gültige Werte: {options_str}. "
                "Rufe sofort `{tool_name}(run_id=\"{run_id}\", "
                "output=\"<gewählter key>\")` auf."
            ),
            choice_manual=(
                "Zeige dem User die Optionen aus dem Prompt. "
                "Rufe dann `{tool_name}(run_id=\"{run_id}\", "
                "output=\"<gewählter key>\")` auf. "
                "Gültige Werte: {options_str}."
            ),

            confirm_auto=(
                "[AUTOMATION MODE] Prüfe die Bestätigung autonom anhand des Prompts. "
                "Rufe `{tool_name}(run_id=\"{run_id}\", output=\"confirmed\")` auf, "
                "außer die vorgeschlagene Aktion ist offensichtlich falsch."
            ),
            confirm_manual=(
                "Zeige dem User den Prompt und frage nach Bestätigung. "
                "Rufe dann `{tool_name}(run_id=\"{run_id}\", "
                "output=\"confirmed\")` oder `output=\"rejected\"` auf."
            ),

            sub_workflow_start=(
                "Sub-Workflow `{wf_ref}` wird gestartet. "
                "Prüfe `sub_workflow.params` für Parameter (required, identity, defaults, resolved_value). "
                "Prüfe `sub_workflow.active_runs` — bei passenden Identity-Parametern FORTSETZEN! "
                "Rufe `{tool_name}(run_id=\"{run_id}\")` auf."
            ),

            sub_workflow_active_runs_hint=(
                "\n\nACHTUNG: {count} aktive(r) Lauf/Läufe gefunden! "
                "Prüfe ob Identity-Parameter matchen — dann FORTSETZEN statt neu starten."
            ),
            sub_workflow_enriched_next_action=(
                "Sub-Workflow `{wf_ref}` wird gestartet.\n"
                "Parameter:\n{param_lines}{active_hint}\n\n"
                "Rufe `{tool_name}(run_id=\"{run_id}\")` auf um den Sub-Workflow zu starten."
            ),

            fallback_auto=(
                "[AUTOMATION MODE] Liefere die Eingabe autonom aus dem Workflow-Kontext. "
                "Rufe sofort `{tool_name}(run_id=\"{run_id}\", "
                "output=\"<eingabe>\")` auf.{partial_hint}"
            ),
            fallback_manual=(
                "Sammle die Eingabe vom User, dann rufe "
                "`{tool_name}(run_id=\"{run_id}\", "
                "output=\"<eingabe>\")` auf.{partial_hint}"
            ),

            new_session="Neue Session starten",

            session_choice_message="Workflow '{wf_name}' — Wähle eine aktive Session oder starte neu:",

            current_value_hint=" [aktuell: {existing_value}]",

            workflow_start_cancelled="Workflow start abgebrochen.",

            prompt_resumed_session="## Fortgesetzte Session",
            prompt_run_id="- **Run-ID:** `{run_id}`",
            prompt_current_step="- **Aktueller Step:** {step_label}",
            prompt_parameters="- **Parameter:** {param_str}",
            prompt_captured_data="### Bereits erfasste Daten (aktueller Step)",
            prompt_still_open="### Noch offen: {keys}",
            prompt_next_action="## Nächste Aktion",

            prompt_call_advance_with_params=(
                "Rufe `{tool_name}` auf mit "
                "`workflow_id=\"{wf_id}\"` und `params='{params_json}'` "
                "um den Workflow zu starten."
            ),
            prompt_call_advance=(
                "Rufe `{tool_name}` auf mit "
                "`workflow_id=\"{wf_id}\"` um den Workflow zu starten."
            ),

            prompt_auto_mode=(
                "## Automatischer Workflow-Modus\n"
                "- Rufe `{tool_name}` auf und folge der `next_action` im Response **SOFORT**.\n"
                "- Frage den User **NICHT** um Erlaubnis — der Engine steuert den Dialog per Elicitation.\n"
                "- Bei Execute-Steps: Führe die Aufgabe aus und rufe dann sofort advance auf.\n"
                "- Wiederhole bis der Workflow abgeschlossen ist."
            ),
        )


def get_locale(code: str = "en") -> Locale:
    """Get a Locale instance by language code.

    Args:
        code: Language code, either "en" (default) or "de".

    Returns:
        Locale instance with the requested language strings.
    """
    if code == "de":
        return Locale.de()
    return Locale.en()
