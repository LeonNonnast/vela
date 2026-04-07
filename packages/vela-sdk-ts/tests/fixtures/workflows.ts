/**
 * Test workflow and agent YAML fixtures.
 */

export const SIMPLE_WORKFLOW_YAML = `
id: onboarding
version: "1.0.0"
name: User Onboarding
description: Onboard a new user step by step.
params:
  - name: user_name
    label: User Name
    required: true
  - name: role
    label: Role
    required: false
    default: member
steps:
  - id: welcome
    type: freeform
    name: Welcome
    prompt: "Welcome {{params.user_name}}! Please describe your goals."
    capture:
      - key: goals
        label: Goals
        source: output
  - id: confirm_role
    type: confirm
    name: Confirm Role
    prompt: "You will be assigned the role: {{params.role}}. Confirm?"
    depends_on:
      - step: welcome
        fields: [goals]
    capture:
      - key: role_confirmed
        source: output
`;

export const CHOICE_WORKFLOW_YAML = `
id: support-ticket
version: "1.0.0"
name: Support Ticket
description: Create a support ticket with category.
params: []
steps:
  - id: category
    type: choice
    name: Choose Category
    prompt: "Select the ticket category:"
    options:
      - key: bug
        label: Bug Report
        description: Report a software bug
      - key: feature
        label: Feature Request
        description: Request a new feature
      - key: question
        label: Question
        description: Ask a question
    capture:
      - key: category
        source: output
  - id: describe
    type: freeform
    name: Describe Issue
    prompt: "Please describe your {{state.category}}."
    capture:
      - key: description
        source: output
`;

export const AGENT_YAML = `
id: support-agent
name: Support Agent
persona: You are a helpful support agent that assists users with their issues.
greeting: Hello! How can I help you today?
workflows:
  - support-ticket
  - onboarding
tools:
  - search
`;

export const MINIMAL_WORKFLOW_YAML = `
id: minimal
version: "1.0.0"
name: Minimal Workflow
description: A minimal workflow for testing.
params: []
steps:
  - id: step1
    type: freeform
    name: Only Step
    prompt: "Do something."
    capture:
      - key: result
        source: output
`;
