"""Azure AI Agents integration for vela-sdk.

Provides a toolset that exposes Vela workflow tools as Azure AI Agent
function tools, plus a prompt advisor for session-level instructions.

Usage::

    from vela_sdk.azure_agents import VelaToolset

    toolset = VelaToolset(workflows_dir="./workflows/")

    # Option A: Get plain callables for FunctionTool
    functions = toolset.get_functions()

    # Option B: Get a ready-made Azure ToolSet
    azure_toolset = toolset.get_toolset()

    # Option C: Get prompt advisor text for additional_instructions
    advisor = toolset.get_prompt_advisor()
"""

from vela_sdk.azure_agents.toolkit import VelaToolset

__all__ = [
    "VelaToolset",
]
