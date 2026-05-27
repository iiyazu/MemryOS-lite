import type { ToolName } from "@/lib/types";

type JsonRpcResult<T> = {
  jsonrpc: "2.0";
  id: number | string;
  result?: {
    content?: Array<{ type: string; text: string }>;
    structuredContent?: T;
  };
  error?: {
    code: number;
    message: string;
  };
};

type RpcClientOptions = {
  endpoint?: string;
  fetcher?: typeof fetch;
  idFactory?: () => number;
};

export function createRpcClient(options: RpcClientOptions = {}) {
  const endpoint = options.endpoint ?? "http://localhost:8100/mcp";
  const fetcher = options.fetcher ?? fetch;
  const idFactory = options.idFactory ?? Date.now;

  return {
    async call<T = unknown>(name: ToolName, args: Record<string, unknown> = {}): Promise<T> {
      const payload = {
        jsonrpc: "2.0",
        id: idFactory(),
        method: "tools/call",
        params: { name, arguments: args }
      };

      const response = await fetcher(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status} while calling ${name}`);
      }

      const data = (await response.json()) as JsonRpcResult<T>;
      if (data.error) {
        throw new Error(data.error.message);
      }

      return data.result?.structuredContent as T;
    }
  };
}
