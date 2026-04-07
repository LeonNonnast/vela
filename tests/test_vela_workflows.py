"""Tests for bundled Vela YAML definitions (agent + workflows)."""

import os

from src.shared.services.workflow_loader import load_agent_file, load_workflows, load_agents

# Path to bundled vela module
VELA_MODULE_DIR = os.path.join(os.path.dirname(__file__), "..", "modules", "vela")
VELA_WORKFLOWS_DIR = os.path.join(VELA_MODULE_DIR, "workflows")
VELA_AGENTS_DIR = os.path.join(VELA_MODULE_DIR, "agents")


class TestVelaAgent:
    """Test the vela.yaml agent definition."""

    def test_vela_agent_loads(self):
        agent = load_agent_file(os.path.join(VELA_AGENTS_DIR, "vela.yaml"))
        assert agent is not None
        assert agent.id == "vela"
        assert agent.name == "Vela — Workspace Navigator"

    def test_vela_agent_has_persona(self):
        agent = load_agent_file(os.path.join(VELA_AGENTS_DIR, "vela.yaml"))
        assert agent.persona
        assert len(agent.persona) > 10

    def test_vela_agent_has_workflows(self):
        agent = load_agent_file(os.path.join(VELA_AGENTS_DIR, "vela.yaml"))
        assert "vela" in agent.workflows
        assert "create-agent" in agent.workflows
        assert "create-workflow" in agent.workflows

    def test_vela_agent_has_tools(self):
        agent = load_agent_file(os.path.join(VELA_AGENTS_DIR, "vela.yaml"))
        assert "vela_validate" in agent.tools
        assert "vela_save" in agent.tools
        assert "vela_status" in agent.tools

    def test_all_agents_load(self):
        agents = load_agents(VELA_AGENTS_DIR)
        assert len(agents) >= 1
        assert "vela" in agents


class TestVelaWorkflows:
    """Test all bundled workflow YAML definitions."""

    def test_all_workflows_load(self):
        workflows = load_workflows(VELA_WORKFLOWS_DIR)
        assert len(workflows) >= 6

    def test_hub_workflow(self):
        workflows = load_workflows(VELA_WORKFLOWS_DIR)
        assert "vela@1.0.0" in workflows
        hub = workflows["vela@1.0.0"]
        assert hub.name == "Vela Navigator"
        # Hub should have choice step as first
        assert hub.steps[0].type == "choice"
        assert len(hub.steps[0].options) == 8

    def test_create_agent_workflow(self):
        workflows = load_workflows(VELA_WORKFLOWS_DIR)
        assert "create-agent@1.0.0" in workflows
        wf = workflows["create-agent@1.0.0"]
        assert len(wf.steps) == 6

    def test_create_workflow_workflow(self):
        workflows = load_workflows(VELA_WORKFLOWS_DIR)
        assert "create-workflow@1.0.0" in workflows
        wf = workflows["create-workflow@1.0.0"]
        assert len(wf.steps) == 6

    def test_create_resource_workflow(self):
        workflows = load_workflows(VELA_WORKFLOWS_DIR)
        assert "create-resource@1.0.0" in workflows
        wf = workflows["create-resource@1.0.0"]
        assert len(wf.steps) == 4

    def test_setup_project_workflow(self):
        workflows = load_workflows(VELA_WORKFLOWS_DIR)
        assert "setup-project@1.0.0" in workflows
        wf = workflows["setup-project@1.0.0"]
        assert len(wf.steps) == 3

    def test_team_management_workflow(self):
        workflows = load_workflows(VELA_WORKFLOWS_DIR)
        assert "team-management@1.0.0" in workflows
        wf = workflows["team-management@1.0.0"]
        # Should have cyclic navigation (aktion-waehlen -> actions -> aktion-waehlen)
        assert wf.steps[0].type == "choice"
        assert any(s.next == "aktion-waehlen" for s in wf.steps if s.next)

    def test_all_workflows_have_steps(self):
        workflows = load_workflows(VELA_WORKFLOWS_DIR)
        for key, wf in workflows.items():
            assert len(wf.steps) > 0, f"Workflow {key} has no steps"
