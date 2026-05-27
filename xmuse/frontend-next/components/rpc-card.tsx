"use client";

import { useState } from "react";

export function RpcCard({ title, payload }: { title: string; payload: unknown }) {
  const [copied, setCopied] = useState(false);
  const text = JSON.stringify(payload, null, 2);
  async function copy() {
    await navigator.clipboard?.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }
  return (
    <section className="panel panel-pad">
      <div className="section-head">
        <h3>{title}</h3>
        <button className="btn" onClick={copy} type="button">
          {copied ? "Copied" : "Copy RPC"}
        </button>
      </div>
      <pre className="code">
        <code>{text}</code>
      </pre>
    </section>
  );
}
