"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { DiffBlock } from "@/components/diff-block";
import { RpcCard } from "@/components/rpc-card";
import { useXmuseStore } from "@/store/use-xmuse-store";

type Tab = "report" | "diff" | "logs";

export function LaneAuditClient() {
  const { lanes, diff, loadInitial, updateLaneStatus } = useXmuseStore();
  const [tab, setTab] = useState<Tab>("report");
  useEffect(() => {
    void loadInitial();
  }, [loadInitial]);

  const lane = lanes.find((item) => item.feature_id === "error-knowledge-bounds");
  const report = lane?.gate_report;

  const rail = (
    <>
      <section className="panel panel-pad">
        <h3>合法状态转换</h3>
        <div className="kv"><dt>gate_failed</dt><dd>failed / reworking</dd></div>
        <div className="kv"><dt>reworking</dt><dd>dispatched</dd></div>
      </section>
      <RpcCard
        title="调用形状"
        payload={{
          method: "tools/call",
          params: { name: "get_gate_report", arguments: { lane_id: "error-knowledge-bounds" } }
        }}
      />
    </>
  );

  return (
    <AppShell rail={rail} context="lane audit">
      <header className="topbar">
        <div>
          <p className="eyebrow">Single lane lifecycle</p>
          <h1>Lane 决策审计</h1>
          <p className="lead">从状态机、God 决策、gate 报告到 git diff，回答“为什么这条 lane 被 merge / rework / abandon”。</p>
        </div>
        <button className="btn primary" onClick={() => updateLaneStatus("error-knowledge-bounds", "reworking")} type="button">
          Advance status
        </button>
      </header>
      <section className="grid cols-3" style={{ marginBottom: 14 }}>
        <article className="panel panel-pad metric">
          <span className="metric-label">Current lane</span>
          <strong className="metric-value" style={{ fontSize: 18 }}>error-knowledge-bounds</strong>
          <span className="pill"><span className="dot bad" />{lane?.status ?? "gate_failed"}</span>
        </article>
        <article className="panel panel-pad metric">
          <span className="metric-label">Retry count</span>
          <strong className="metric-value">01</strong>
          <span className="muted">max 2 rework loops</span>
        </article>
        <article className="panel panel-pad metric">
          <span className="metric-label">Gate profile</span>
          <strong className="metric-value" style={{ fontSize: 22 }}>xmuse-core</strong>
          <span className="muted">blocking_passed: false</span>
        </article>
      </section>
      <section className="split">
        <div className="panel panel-pad">
          <div className="section-head">
            <h2>Evidence</h2>
            <div className="tabs">
              {(["report", "diff", "logs"] as Tab[]).map((item) => (
                <button className={`tab ${tab === item ? "active" : ""}`} key={item} onClick={() => setTab(item)} type="button">
                  {item === "report" ? "Gate" : item === "diff" ? "Diff" : "Logs"}
                </button>
              ))}
            </div>
          </div>
          {tab === "report" ? (
            <dl>
              <div className="kv"><dt>passed</dt><dd>{String(report?.passed ?? false)}</dd></div>
              <div className="kv"><dt>blocking</dt><dd>{String(report?.blocking_passed ?? false)}</dd></div>
              <div className="kv"><dt>warnings</dt><dd>{report?.warnings.join("; ")}</dd></div>
              <div className="kv"><dt>resolution</dt><dd className="mono">explicit_lane_profile → xmuse-core</dd></div>
            </dl>
          ) : null}
          {tab === "diff" ? <DiffBlock diff={diff} /> : null}
          {tab === "logs" ? (
            <pre className="code">{`== logs/gates/error-knowledge-bounds/report.json ==
warning: missing pytest path
decision: rework
context: preserve bounded store behavior and add nullable gate artifact handling`}</pre>
          ) : null}
        </div>
        <div className="panel panel-pad">
          <div className="section-head"><h2>Decision chain</h2><span className="mono">get_lane</span></div>
          <div className="timeline">
            <div className="timeline-item"><span className="row-left"><span className="dot accent" /><strong>Planner God</strong></span><span className="muted">Dispatched because storage bounds are isolated and testable.</span></div>
            <div className="timeline-item"><span className="row-left"><span className="dot bad" /><strong>Gate</strong></span><span className="muted">Blocking gate failed; artifact path absent.</span></div>
            <div className="timeline-item"><span className="row-left"><span className="dot warn" /><strong>Review God</strong></span><span className="muted">Rework requested with explicit nullable artifact handling.</span></div>
          </div>
        </div>
      </section>
    </AppShell>
  );
}
