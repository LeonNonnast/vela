"""LangChain ReAct agent with Vela workflow tools."""

import asyncio

from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent

from vela_sdk.langchain import VelaToolkit

# Load workflows from YAML and get LangChain-compatible tools
toolkit = VelaToolkit(workflows_dir="./workflows/")
tools = toolkit.get_tools()

# Create a ReAct agent with Claude and Vela tools
llm = ChatAnthropic(model="claude-sonnet-4-20250514")
agent = create_react_agent(llm, tools)


async def main():
    print("Vela + LangChain Agent")
    print('Type a message. Type "exit" to quit.\n')

    while True:
        user_input = input("You: ")
        if user_input.lower() in ("quit", "exit"):
            break

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": user_input}]}
        )

        # Print the last AI message
        for msg in reversed(result["messages"]):
            if msg.type == "ai" and msg.content:
                print(f"Agent: {msg.content}\n")
                break


if __name__ == "__main__":
    asyncio.run(main())
