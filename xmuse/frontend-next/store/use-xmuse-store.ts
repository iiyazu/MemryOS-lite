"use client";

import { create } from "zustand";
import { createMockXmuseApi } from "@/lib/mock-api";
import type { KnowledgeMatch, Lane, LaneStatus, XmuseApi } from "@/lib/types";

type XmuseState = {
  lanes: Lane[];
  selectedLaneId: string | null;
  laneFilter: LaneStatus | "all";
  knowledgeQuery: string;
  knowledgeMatches: KnowledgeMatch[];
  diff: string;
  loadInitial: (api?: XmuseApi) => Promise<void>;
  setLaneFilter: (status: LaneStatus | "all") => void;
  selectLane: (laneId: string | null) => void;
  searchKnowledge: (query: string, api?: XmuseApi) => Promise<void>;
  updateLaneStatus: (laneId: string, status: Lane["status"]) => void;
};

const defaultApi = createMockXmuseApi();

export const useXmuseStore = create<XmuseState>((set) => ({
  lanes: [],
  selectedLaneId: null,
  laneFilter: "all",
  knowledgeQuery: "gate report",
  knowledgeMatches: [],
  diff: "",
  async loadInitial(api = defaultApi) {
    const [lanes, knowledge, diff] = await Promise.all([
      api.listLanes(),
      api.queryKnowledge({ query: "gate report", top_k: 5 }),
      api.getDiff({ lane_id: "error-knowledge-bounds" })
    ]);
    set({ lanes, knowledgeMatches: knowledge.matches, diff: diff.diff });
  },
  setLaneFilter(status) {
    set({ laneFilter: status });
  },
  selectLane(laneId) {
    set({ selectedLaneId: laneId });
  },
  async searchKnowledge(query, api = defaultApi) {
    const result = await api.queryKnowledge({ query, top_k: 5 });
    set({ knowledgeQuery: query, knowledgeMatches: result.matches });
  },
  updateLaneStatus(laneId, status) {
    set((state) => ({
      lanes: state.lanes.map((lane) => (lane.feature_id === laneId ? { ...lane, status } : lane))
    }));
  }
}));
