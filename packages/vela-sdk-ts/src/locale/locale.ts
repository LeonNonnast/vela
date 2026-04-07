/**
 * Locale system for user-facing strings in the vela-sdk.
 *
 * Template placeholders use {name} syntax — same as the Python original.
 */

// ---------------------------------------------------------------------------
// Locale interface
// ---------------------------------------------------------------------------

export interface Locale {
  // --- response_builder: build_next_action ---
  workflowCompleted: string;
  alreadyCaptured: string;
  stillOpen: string;

  // Execute step
  executeTaskThenCall: string;
  executePrefixTag: string;
  /** next_action when execute step has delegate: "subagent" */
  executeDelegateSubagent: string;

  // Dialog step
  dialogAutoStart: string;
  dialogAutoProcess: string;
  dialogStart: string;
  dialogConverse: string;

  // Elicitable captures
  elicitAuto: string;
  elicitManual: string;

  // Choice step
  choiceAuto: string;
  choiceManual: string;

  // Confirm step
  confirmAuto: string;
  confirmManual: string;

  // Workflow (sub-workflow) step
  subWorkflowStart: string;
  subWorkflowActiveRunsHint: string;
  subWorkflowEnrichedNextAction: string;

  // Fallback (default input)
  fallbackAuto: string;
  fallbackManual: string;

  // --- response_builder: build_run_options ---
  newSession: string;

  // --- session_elicitor ---
  sessionChoiceMessage: string;

  // --- auto_advance: elicit_step_captures ---
  currentValueHint: string;

  // --- integration ---
  workflowStartCancelled: string;

  // Prompt: resumed session headings
  promptResumedSession: string;
  promptRunId: string;
  promptCurrentStep: string;
  promptParameters: string;
  promptCapturedData: string;
  promptStillOpen: string;
  promptNextAction: string;

  // Prompt: new workflow next action
  promptCallAdvanceWithParams: string;
  promptCallAdvance: string;

  // Prompt: auto-mode instructions
  promptAutoMode: string;
}

// ---------------------------------------------------------------------------
// English locale
// ---------------------------------------------------------------------------

export function enLocale(): Locale {
  return {
    workflowCompleted: "Workflow completed. No further action needed.",
    alreadyCaptured:
      " Already captured: {captured_json}. Still open: {missing_keys}.",
    stillOpen: "Still open",

    executePrefixTag: "[AUTOMATION MODE] ",
    executeTaskThenCall:
      '{prefix_tag}Execute the task in the prompt, then IMMEDIATELY call ' +
      '`{tool_name}(run_id="{run_id}", ' +
      'output="<your summary>")`.{partial_hint}',
    executeDelegateSubagent:
      "DELEGATE: This step must be executed by a **subagent**. " +
      "Do NOT execute this task yourself. The host application will spawn a " +
      "separate agent session for this step. " +
      "The response contains `delegate`, `delegate_instructions`, and `delegate_tools` " +
      "with all details for the subagent.",

    dialogAutoStart:
      "[AUTOMATION MODE] Start the dialog autonomously. " +
      'Call `{tool_name}(run_id="{run_id}")` immediately. ' +
      "The engine will deliver the first phase \u2014 process it without user input.",
    dialogAutoProcess:
      "[AUTOMATION MODE] Process the dialog phase from the prompt autonomously. " +
      "Synthesize a response from the available context. Then immediately call " +
      '`{tool_name}(run_id="{run_id}", ' +
      'output="<your summary>")`.',
    dialogStart:
      'Call `{tool_name}(run_id="{run_id}")` ' +
      "to start the dialog. The engine will deliver the first phase with instructions.",
    dialogConverse:
      "Have a conversation with the user according to the phase instructions in the prompt. " +
      "When the phase is complete, summarize the result and call " +
      '`{tool_name}(run_id="{run_id}", ' +
      'output="<summary>")`.',

    elicitAuto:
      '[AUTOMATION MODE] Call `{tool_name}(run_id="{run_id}")` immediately. ' +
      "Only required captures will be collected via elicitation dialog \u2014 " +
      "optional captures will be skipped.{partial_hint}",
    elicitManual:
      'Call `{tool_name}(run_id="{run_id}")` NOW. ' +
      "The engine will ask the user automatically via elicitation dialog \u2014 " +
      "do NOT ask questions yourself.{partial_hint}",

    choiceAuto:
      "[AUTOMATION MODE] Choose the most suitable option based on the workflow context. " +
      "Valid values: {options_str}. " +
      'Call `{tool_name}(run_id="{run_id}", ' +
      'output="<chosen key>")` immediately.',
    choiceManual:
      "Show the user the options from the prompt. " +
      'Then call `{tool_name}(run_id="{run_id}", ' +
      'output="<chosen key>")`. ' +
      "Valid values: {options_str}.",

    confirmAuto:
      "[AUTOMATION MODE] Check the confirmation autonomously based on the prompt. " +
      'Call `{tool_name}(run_id="{run_id}", output="confirmed")`, ' +
      "unless the proposed action is obviously wrong.",
    confirmManual:
      "Show the user the prompt and ask for confirmation. " +
      'Then call `{tool_name}(run_id="{run_id}", ' +
      'output="confirmed")` or `output="rejected"`.',

    subWorkflowStart:
      "Sub-workflow `{wf_ref}` is starting. " +
      "Check `sub_workflow.params` for parameters (required, identity, defaults, resolved_value). " +
      "Check `sub_workflow.active_runs` \u2014 RESUME if identity parameters match! " +
      'Call `{tool_name}(run_id="{run_id}")`.',
    subWorkflowActiveRunsHint:
      "\n\nWARNING: {count} active run(s) found! " +
      "Check if identity parameters match \u2014 then RESUME instead of starting a new run.",
    subWorkflowEnrichedNextAction:
      "Sub-workflow `{wf_ref}` is starting.\n" +
      "Parameters:\n{param_lines}{active_hint}\n\n" +
      'Call `{tool_name}(run_id="{run_id}")` to start the sub-workflow.',

    fallbackAuto:
      "[AUTOMATION MODE] Provide the input autonomously from the workflow context. " +
      'Call `{tool_name}(run_id="{run_id}", ' +
      'output="<input>")` immediately.{partial_hint}',
    fallbackManual:
      "Collect the input from the user, then call " +
      '`{tool_name}(run_id="{run_id}", ' +
      'output="<input>")`.{partial_hint}',

    newSession: "Start new session",

    sessionChoiceMessage:
      "Workflow '{wf_name}' \u2014 Choose an active session or start a new one:",

    currentValueHint: " [current: {existing_value}]",

    workflowStartCancelled: "Workflow start cancelled.",

    promptResumedSession: "## Resumed Session",
    promptRunId: "- **Run ID:** `{run_id}`",
    promptCurrentStep: "- **Current Step:** {step_label}",
    promptParameters: "- **Parameters:** {param_str}",
    promptCapturedData: "### Already captured data (current step)",
    promptStillOpen: "### Still open: {keys}",
    promptNextAction: "## Next Action",

    promptCallAdvanceWithParams:
      "Call `{tool_name}` with " +
      '`workflow_id="{wf_id}"` and `params=\'{params_json}\'` ' +
      "to start the workflow.",
    promptCallAdvance:
      "Call `{tool_name}` with " +
      '`workflow_id="{wf_id}"` to start the workflow.',

    promptAutoMode:
      "## Automatic Workflow Mode\n" +
      "- Call `{tool_name}` and follow the `next_action` in the response **IMMEDIATELY**.\n" +
      "- Do **NOT** ask the user for permission \u2014 the engine controls the dialog via elicitation.\n" +
      "- For execute steps: Perform the task and then immediately call advance.\n" +
      "- Repeat until the workflow is completed.",
  };
}

// ---------------------------------------------------------------------------
// German locale
// ---------------------------------------------------------------------------

export function deLocale(): Locale {
  return {
    workflowCompleted:
      "Workflow abgeschlossen. Keine weitere Aktion n\u00f6tig.",
    alreadyCaptured:
      " Bereits erfasst: {captured_json}. Noch offen: {missing_keys}.",
    stillOpen: "Noch offen",

    executePrefixTag: "[AUTOMATION MODE] ",
    executeTaskThenCall:
      "{prefix_tag}F\u00fchre die Aufgabe im Prompt aus, dann rufe SOFORT " +
      '`{tool_name}(run_id="{run_id}", ' +
      'output="<deine Zusammenfassung>")` auf.{partial_hint}',
    executeDelegateSubagent:
      "DELEGIEREN: Dieser Step muss von einem **Subagenten** ausgef\u00fchrt werden. " +
      "F\u00fchre diese Aufgabe NICHT selbst aus. Die Host-Anwendung startet eine " +
      "separate Agent-Session f\u00fcr diesen Step. " +
      "Die Antwort enth\u00e4lt `delegate`, `delegate_instructions` und `delegate_tools` " +
      "mit allen Details f\u00fcr den Subagenten.",

    dialogAutoStart:
      "[AUTOMATION MODE] Starte den Dialog autonom. " +
      'Rufe sofort `{tool_name}(run_id="{run_id}")` auf. ' +
      "Der Engine liefert die erste Phase \u2014 verarbeite sie ohne User-Eingabe.",
    dialogAutoProcess:
      "[AUTOMATION MODE] Verarbeite die Dialog-Phase aus dem Prompt autonom. " +
      "Synthetisiere eine Antwort aus dem verf\u00fcgbaren Kontext. Rufe dann sofort " +
      '`{tool_name}(run_id="{run_id}", ' +
      'output="<deine Zusammenfassung>")` auf.',
    dialogStart:
      'Rufe `{tool_name}(run_id="{run_id}")` auf ' +
      "um den Dialog zu starten. Der Engine liefert die erste Phase mit Anweisungen.",
    dialogConverse:
      "F\u00fchre ein Gespr\u00e4ch mit dem User gem\u00e4\u00df der Phase-Anweisung im Prompt. " +
      "Wenn die Phase abgeschlossen ist, fasse das Ergebnis zusammen und rufe " +
      '`{tool_name}(run_id="{run_id}", ' +
      'output="<Zusammenfassung>")` auf.',

    elicitAuto:
      '[AUTOMATION MODE] Rufe sofort `{tool_name}(run_id="{run_id}")` auf. ' +
      "Nur required Captures werden per Elicitation-Dialog abgefragt \u2014 " +
      "optionale Captures werden \u00fcbersprungen.{partial_hint}",
    elicitManual:
      'Rufe JETZT `{tool_name}(run_id="{run_id}")` auf. ' +
      "Der Engine fragt den User automatisch per Elicitation-Dialog \u2014 " +
      "stelle KEINE eigenen Fragen.{partial_hint}",

    choiceAuto:
      "[AUTOMATION MODE] W\u00e4hle die passendste Option basierend auf dem Workflow-Kontext. " +
      "G\u00fcltige Werte: {options_str}. " +
      'Rufe sofort `{tool_name}(run_id="{run_id}", ' +
      'output="<gew\u00e4hlter key>")` auf.',
    choiceManual:
      "Zeige dem User die Optionen aus dem Prompt. " +
      'Rufe dann `{tool_name}(run_id="{run_id}", ' +
      'output="<gew\u00e4hlter key>")` auf. ' +
      "G\u00fcltige Werte: {options_str}.",

    confirmAuto:
      "[AUTOMATION MODE] Pr\u00fcfe die Best\u00e4tigung autonom anhand des Prompts. " +
      'Rufe `{tool_name}(run_id="{run_id}", output="confirmed")` auf, ' +
      "au\u00dfer die vorgeschlagene Aktion ist offensichtlich falsch.",
    confirmManual:
      "Zeige dem User den Prompt und frage nach Best\u00e4tigung. " +
      'Rufe dann `{tool_name}(run_id="{run_id}", ' +
      'output="confirmed")` oder `output="rejected"` auf.',

    subWorkflowStart:
      "Sub-Workflow `{wf_ref}` wird gestartet. " +
      "Pr\u00fcfe `sub_workflow.params` f\u00fcr Parameter (required, identity, defaults, resolved_value). " +
      "Pr\u00fcfe `sub_workflow.active_runs` \u2014 bei passenden Identity-Parametern FORTSETZEN! " +
      'Rufe `{tool_name}(run_id="{run_id}")` auf.',
    subWorkflowActiveRunsHint:
      "\n\nACHTUNG: {count} aktive(r) Lauf/L\u00e4ufe gefunden! " +
      "Pr\u00fcfe ob Identity-Parameter matchen \u2014 dann FORTSETZEN statt neu starten.",
    subWorkflowEnrichedNextAction:
      "Sub-Workflow `{wf_ref}` wird gestartet.\n" +
      "Parameter:\n{param_lines}{active_hint}\n\n" +
      'Rufe `{tool_name}(run_id="{run_id}")` auf um den Sub-Workflow zu starten.',

    fallbackAuto:
      "[AUTOMATION MODE] Liefere die Eingabe autonom aus dem Workflow-Kontext. " +
      'Rufe sofort `{tool_name}(run_id="{run_id}", ' +
      'output="<eingabe>")` auf.{partial_hint}',
    fallbackManual:
      "Sammle die Eingabe vom User, dann rufe " +
      '`{tool_name}(run_id="{run_id}", ' +
      'output="<eingabe>")` auf.{partial_hint}',

    newSession: "Neue Session starten",

    sessionChoiceMessage:
      "Workflow '{wf_name}' \u2014 W\u00e4hle eine aktive Session oder starte neu:",

    currentValueHint: " [aktuell: {existing_value}]",

    workflowStartCancelled: "Workflow start abgebrochen.",

    promptResumedSession: "## Fortgesetzte Session",
    promptRunId: "- **Run-ID:** `{run_id}`",
    promptCurrentStep: "- **Aktueller Step:** {step_label}",
    promptParameters: "- **Parameter:** {param_str}",
    promptCapturedData: "### Bereits erfasste Daten (aktueller Step)",
    promptStillOpen: "### Noch offen: {keys}",
    promptNextAction: "## N\u00e4chste Aktion",

    promptCallAdvanceWithParams:
      "Rufe `{tool_name}` auf mit " +
      '`workflow_id="{wf_id}"` und `params=\'{params_json}\'` ' +
      "um den Workflow zu starten.",
    promptCallAdvance:
      "Rufe `{tool_name}` auf mit " +
      '`workflow_id="{wf_id}"` um den Workflow zu starten.',

    promptAutoMode:
      "## Automatischer Workflow-Modus\n" +
      "- Rufe `{tool_name}` auf und folge der `next_action` im Response **SOFORT**.\n" +
      "- Frage den User **NICHT** um Erlaubnis \u2014 der Engine steuert den Dialog per Elicitation.\n" +
      "- Bei Execute-Steps: F\u00fchre die Aufgabe aus und rufe dann sofort advance auf.\n" +
      "- Wiederhole bis der Workflow abgeschlossen ist.",
  };
}

// ---------------------------------------------------------------------------
// getLocale
// ---------------------------------------------------------------------------

export function getLocale(code: "en" | "de" = "en"): Locale {
  if (code === "de") {
    return deLocale();
  }
  return enLocale();
}
