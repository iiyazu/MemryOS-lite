"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { RpcCard } from "@/components/rpc-card";
import { useXmuseStore } from "@/store/use-xmuse-store";

export function KnowledgeClient() {
  const { knowledgeMatches, knowledgeQuery, loadInitial, searchKnowledge } = useXmuseStore();
  const [query, setQuery] = useState(knowledgeQuery);
  useEffect(() => {
    void loadInitial();
  }, [loadInitial]);

  const selected = knowledgeMatches[0]?.entry;
  const rail = (
    <>
      <section className="panel panel-pad">
        <h3>查询质量</h3>
        <div className="kv"><dt>top_k</dt><dd>5</dd></div>
        <div className="kv"><dt>source</dt><dd className="mono">xmuse/error_knowledge.json</dd></div>
      </section>
      <RpcCard
        title="调用形状"
        payload={{ method: "tools/call", params: { name: "query_knowledge", arguments: { query, top_k: 5 } } }}
      />
    </>
  );

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    await searchKnowledge(query);
  }

  return (
    <AppShell rail={rail} context="knowledge">
      <header className="topbar">
        <div>
          <p className="eyebrow">error_knowledge search</p>
          <h1>知识库 Explorer</h1>
          <p className="lead">让重复错误变少：按关键词检索 pit、root cause、fix、prevention，并查看命中条目能否解释当前 lane。</p>
        </div>
        <form className="toolbar" onSubmit={submit}>
          <input className="input" style={{ width: 260 }} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 mypy / ruff / gate..." />
          <button className="btn primary" type="submit">Search</button>
        </form>
      </header>
      <section className="split">
        <div className="panel panel-pad">
          <div className="section-head"><h2>Matches</h2><span className="mono">get_error_knowledge</span></div>
          <div className="timeline">
            {knowledgeMatches.map((match) => (
              <article className="knowledge-row" key={match.entry.id}>
                <span className="row">
                  <span className="row-left"><span className="dot ok" /><strong>{match.entry.pit}</strong></span>
                  <span className="pill">score {match.score}</span>
                </span>
                <p className="muted">Root cause: {match.entry.root_cause}.</p>
                <code className="mono">fix: {match.entry.fix}</code>
              </article>
            ))}
          </div>
        </div>
        <div className="panel panel-pad">
          <div className="section-head"><h2>Selected entry</h2><span className="pill"><span className="dot bad" />gate</span></div>
          {selected ? (
            <dl>
              <div className="kv"><dt>pit</dt><dd>{selected.pit}</dd></div>
              <div className="kv"><dt>trigger</dt><dd>{selected.trigger}</dd></div>
              <div className="kv"><dt>fix</dt><dd>{selected.fix}</dd></div>
              <div className="kv"><dt>lesson</dt><dd>{selected.lesson}</dd></div>
            </dl>
          ) : (
            <p className="muted">没有匹配条目。</p>
          )}
        </div>
      </section>
    </AppShell>
  );
}
