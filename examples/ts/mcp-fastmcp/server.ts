import { readFileSync } from "node:fs";
import { FastMCP } from "fastmcp";
import { VelaWorkflows } from "vela-sdk";
import { FastMcpAdapter } from "vela-sdk/adapters/fastmcp";

const workflowYaml = readFileSync("./workflows/project-setup.yaml", "utf-8");

const server = new FastMCP({ name: "project-assistant", version: "1.0.0" });

const vela = new VelaWorkflows({
  server: new FastMcpAdapter(server),
  workflows: [workflowYaml],
});

server.start({ transportType: "stdio" });
