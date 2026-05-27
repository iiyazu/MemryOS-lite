import { describe, expect, it, vi } from "vitest";
import { createRpcClient } from "@/lib/rpc-client";
import { createMockXmuseApi } from "@/lib/mock-api";

describe("createRpcClient", () => {
  it("posts tools/call payloads and returns structuredContent", async () => {
    const fetcher = vi.fn(async () =>
      new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 7,
          result: {
            content: [{ type: "text", text: "ok" }],
            structuredContent: { lanes: [{ feature_id: "lane-1", status: "pending" }] }
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    );

    const client = createRpcClient({ endpoint: "http://localhost:8100/mcp", fetcher, idFactory: () => 7 });
    const result = await client.call("list_lanes", {});

    expect(result).toEqual({ lanes: [{ feature_id: "lane-1", status: "pending" }] });
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8100/mcp",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: 7,
          method: "tools/call",
          params: { name: "list_lanes", arguments: {} }
        })
      })
    );
  });

  it("throws JSON-RPC error messages before reading result payloads", async () => {
    const fetcher = vi.fn(async () =>
      new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 8,
          error: { code: -32000, message: "cannot transition lane from pending to merged" }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    );

    const client = createRpcClient({ endpoint: "/mcp", fetcher, idFactory: () => 8 });

    await expect(client.call("update_lane_status", { lane_id: "lane", status: "merged" })).rejects.toThrow(
      "cannot transition lane from pending to merged"
    );
  });
});

describe("createMockXmuseApi", () => {
  it("filters lanes by status and searches knowledge entries case-insensitively", async () => {
    const api = createMockXmuseApi();

    const lanes = await api.listLanes({ status: "gate_failed" });
    const knowledge = await api.queryKnowledge({ query: "GATE REPORT", top_k: 2 });

    expect(lanes.map((lane) => lane.feature_id)).toEqual(["error-knowledge-bounds"]);
    expect(knowledge.matches[0]?.entry.id).toBe("ek-021");
    expect(knowledge.matches).toHaveLength(1);
  });
});
