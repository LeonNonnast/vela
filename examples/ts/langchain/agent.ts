import { readFileSync } from "node:fs";
import * as readline from "node:readline";
import { ChatAnthropic } from "@langchain/anthropic";
import { createReactAgent } from "@langchain/langgraph/prebuilt";
import { HumanMessage } from "@langchain/core/messages";
import { createVelaToolkit } from "vela-sdk/adapters/langchain";

const workflowYaml = readFileSync("./workflows/project-setup.yaml", "utf-8");

const { tools } = createVelaToolkit({
  workflows: [workflowYaml],
});

const llm = new ChatAnthropic({ model: "claude-sonnet-4-20250514" });
const agent = createReactAgent({ llm, tools });

// Interactive loop
const rl = readline.createInterface({ input: process.stdin, output: process.stdout });

console.log("Vela + LangChain Agent");
console.log('Type a message. Type "exit" to quit.\n');

function ask() {
  rl.question("You: ", async (input) => {
    if (input.toLowerCase() === "exit") {
      rl.close();
      return;
    }
    const result = await agent.invoke({
      messages: [new HumanMessage(input)],
    });
    const messages = result.messages;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i]._getType() === "ai" && messages[i].content) {
        console.log(`Agent: ${messages[i].content}\n`);
        break;
      }
    }
    ask();
  });
}
ask();
