import { readFileSync } from "node:fs";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { VelaWorkflows } from "vela-sdk";
import { OfficialSdkAdapter } from "vela-sdk/adapters/mcp-sdk";

const workflowYaml = readFileSync("./workflows/project-setup.yaml", "utf-8");

const mcpServer = new McpServer(
  { name: "project-assistant", version: "1.0.0" },
  { capabilities: {} },
);

const vela = new VelaWorkflows({
  server: new OfficialSdkAdapter(mcpServer),
  workflows: [workflowYaml],
});

const transport = new StdioServerTransport();
await mcpServer.connect(transport);
