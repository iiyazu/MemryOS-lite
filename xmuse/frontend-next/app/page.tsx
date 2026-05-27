import Link from "next/link";

export default function HomePage() {
  return (
    <main className="launcher">
      <Link className="brand" href="/observability">
        <span className="mark">x</span>
        <span>
          <strong>xmuse</strong>
          <span>God collaboration observability</span>
        </span>
      </Link>
      <div className="topbar">
        <div>
          <p className="eyebrow">Desktop prototype · JSON-RPC over HTTP POST</p>
          <h1>观察 God 们是否真正把事情做对。</h1>
          <p className="lead">
            面向本地单用户开发者的深色控制台。入口只做导航，三块核心能力分别独立成屏：协作可观测性、Lane 决策审计、错误知识库探索。
          </p>
        </div>
        <Link className="btn primary" href="/observability">
          Open dashboard
        </Link>
      </div>
      <section className="launcher-grid">
        <Link className="panel screen-card" href="/observability">
          <div>
            <span className="pill">
              <span className="dot accent" />
              Observability
            </span>
            <h2 style={{ marginTop: 16 }}>God 协作时间线</h2>
            <p className="lead">查看 lane 状态分布、异常提示、知识命中趋势，以及每个 God 的关键决策。</p>
          </div>
          <div className="status-map" aria-hidden="true">
            <span className="status-cell ok" />
            <span className="status-cell work" />
            <span className="status-cell hot" />
            <span className="status-cell" />
            <span className="status-cell work" />
            <span className="status-cell ok" />
          </div>
        </Link>
        <Link className="panel screen-card" href="/lane-audit">
          <div>
            <span className="pill">
              <span className="dot warn" />
              Audit
            </span>
            <h2 style={{ marginTop: 16 }}>Lane 决策审计</h2>
            <p className="lead">按单条 lane 追踪生命周期、gate 报告、rework context、diff 变更与状态推进。</p>
          </div>
          <code className="mono">tools/call:get_diff</code>
        </Link>
        <Link className="panel screen-card" href="/knowledge">
          <div>
            <span className="pill">
              <span className="dot ok" />
              Knowledge
            </span>
            <h2 style={{ marginTop: 16 }}>错误知识库 Explorer</h2>
            <p className="lead">搜索 error_knowledge，查看 root cause、fix、prevention 与命中质量。</p>
          </div>
          <code className="mono">query_knowledge({`{ query, top_k }`})</code>
        </Link>
      </section>
    </main>
  );
}
