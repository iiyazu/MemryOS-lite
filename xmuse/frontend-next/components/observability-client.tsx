"use client";

import { useEffect, useMemo } from "react";
import { AppShell } from "@/components/app-shell";
import { RpcCard } from "@/components/rpc-card";
import { statusTone } from "@/components/status";
import type { LaneStatus } from "@/lib/types";
import { useXmuseStore } from "@/store/use-xmuse-store";

const filters: Array<{ label: string; value: LaneStatus | "all" }> = [
  { label: "All", value: "all" },
  { label: "Running", value: "dispatched" },
  { label: "Failed gate", value: "gate_failed" },
  { label: "Reviewed", value: "reviewed" }
];

export function ObservabilityClient() {
  const { lanes, laneFilter, selectedLaneId, loadInitial, setLaneFilter, selectLane, knowledgeMatches } = useXmuseStore();
  useEffect(() => {
    void loadInitial();
  }, [loadInitial]);

  const visible = useMemo(
    () => lanes.filter((lane) => laneFilter === "all" || lane.status === laneFilter),
    [laneFilter, lanes]
  );
  const selected = lanes.find((lane) => lane.feature_id === selectedLaneId);

  const rail = (
    <>
      <section className="panel panel-pad">
        <h3>异常告警</h3>
        <div className="kv">
          <dt>
            <span className="dot bad" /> gate
          </dt>
          <dd>error-knowledge-bounds blocking gate failed</dd>
        </div>
        <div className="kv">
          <dt>
            <span className="dot warn" /> loop
          </dt>
          <dd>retry_count 接近上限时提示人工介入</dd>
        </div>
      </section>
      <RpcCard
        title="调用形状"
        payload={{ method: "tools/call", params: { name: "list_lanes", arguments: {} } }}
      />
    </>
  );

  return (
    <>
      <AppShell rail={rail}>
        <header className="topbar">
          <div>
            <p className="eyebrow">God collaboration timeline</p>
            <h1>Observability Dashboard</h1>
            <p className="lead">聚焦决策质量：哪些 lane 在推进，哪些在 rework 循环，知识库是否正在减少重复错误。</p>
          </div>
          <div className="toolbar">
            {filters.map((filter) => (
              <button
                className={`chip ${laneFilter === filter.value ? "active" : ""}`}
                key={filter.value}
                onClick={() => setLaneFilter(filter.value)}
                type="button"
              >
                {filter.label}
              </button>
            ))}
          </div>
        </header>
        <section className="grid cols-3" style={{ marginBottom: 14 }}>
          <article className="panel panel-pad metric">
            <span className="metric-label">Active lanes</span>
            <strong className="metric-value">{lanes.length.toString().padStart(2, "0")}</strong>
            <span className="muted">1 gate failure requires review</span>
          </article>
          <article className="panel panel-pad metric">
            <span className="metric-label">Decision balance</span>
            <strong className="metric-value">2 / 1 / 1</strong>
            <span className="muted">review · rework · pending</span>
          </article>
          <article className="panel panel-pad metric">
            <span className="metric-label">Knowledge hits</span>
            <strong className="metric-value">{knowledgeMatches.length.toString().padStart(2, "0")}</strong>
            <span className="muted">query_knowledge returned matches</span>
          </article>
        </section>
        <section className="split">
          <div className="panel panel-pad">
            <div className="section-head">
              <h2>协作时间线</h2>
              <span className="mono">list_lanes → structuredContent.lanes</span>
            </div>
            <div className="timeline">
              {visible.map((lane) => (
                <button className="timeline-item" key={lane.feature_id} onClick={() => selectLane(lane.feature_id)} type="button">
                  <span className="row">
                    <span className="row-left">
                      <span className={`dot ${statusTone(lane.status)}`} />
                      <strong className="title-line">{lane.god} · {lane.prompt}</strong>
                    </span>
                    <span className="mono">{lane.elapsed}</span>
                  </span>
                  <span className="muted">{lane.decision_reason}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="panel panel-pad">
            <div className="section-head">
              <h2>知识命中趋势</h2>
              <span className="pill">
                <span className="dot ok" />
                stable
              </span>
            </div>
            <div className="chart" aria-label="Knowledge hit trend">
              {[38, 52, 44, 70, 82, 64].map((height, index) => (
                <span className="bar" style={{ height: `${height}%` }} key={height}>
                  <i style={{ height: `${[55, 62, 48, 70, 76, 60][index]}%` }} />
                </span>
              ))}
            </div>
            <dl>
              <div className="kv">
                <dt>Signal</dt>
                <dd>同类 mypy / gate artifact 错误可复用知识条目</dd>
              </div>
              <div className="kv">
                <dt>Risk</dt>
                <dd>rework 超过 2 次后应直接标记 failed</dd>
              </div>
            </dl>
          </div>
        </section>
      </AppShell>
      <div className={`drawer-scrim ${selected ? "open" : ""}`} onClick={() => selectLane(null)} />
      <aside className={`drawer ${selected ? "open" : ""}`}>
        <div className="section-head">
          <h2>{selected?.feature_id ?? "Lane"}</h2>
          <button className="btn" onClick={() => selectLane(null)} type="button">Close</button>
        </div>
        {selected ? (
          <dl>
            <div className="kv"><dt>Status</dt><dd><span className="pill"><span className={`dot ${statusTone(selected.status)}`} />{selected.status}</span></dd></div>
            <div className="kv"><dt>Branch</dt><dd className="mono">{selected.branch}</dd></div>
            <div className="kv"><dt>Gate profile</dt><dd>{selected.gate_profile}</dd></div>
            <div className="kv"><dt>Decision</dt><dd>{selected.decision_reason}</dd></div>
            <div className="kv"><dt>JSON-RPC</dt><dd className="mono">tools/call:get_lane → {`{ lane_id: "${selected.feature_id}" }`}</dd></div>
          </dl>
        ) : null}
      </aside>
    </>
  );
}
