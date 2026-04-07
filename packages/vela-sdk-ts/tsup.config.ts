import { defineConfig } from "tsup";

export default defineConfig({
  entry: {
    index: "src/index.ts",
    "adapters/fastmcp": "src/adapters/fastmcp.ts",
    "adapters/mcp-sdk": "src/adapters/mcp-sdk.ts",
  },
  format: ["esm", "cjs"],
  dts: true,
  clean: true,
  sourcemap: true,
  splitting: false,
  external: ["fastmcp", "@modelcontextprotocol/sdk"],
});
