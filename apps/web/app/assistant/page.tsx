"use client";

import { useState } from "react";
import { PageHead } from "@/components/PageHead";
import { Failure } from "@/components/States";
import { api } from "@/lib/api";

type Section = { kind: string; text: string };

export default function AssistantPage() {
  const [question, setQuestion] = useState("Which stocks have confirmed high-volume breakouts?");
  const [error, setError] = useState("");
  const [data, setData] = useState<{ sections: Section[]; narrative?: string | null; disclaimer: string; model_used: boolean } | null>(null);

  return (
    <div className="grid gap-4">
      <PageHead
        kicker="Research"
        title="AI assistant"
        lede="Facts come from the scanner, the 52-week study, or the index monitor. A language model is used only to rephrase that JSON, and only when a key is configured. Pro plan."
      />
      <form className="panel grid gap-3 p-4" onSubmit={async (event) => {
        event.preventDefault();
        setError("");
        try {
          setData(await api("/api/v1/assistant/ask", { method: "POST", body: JSON.stringify({ question }) }));
        } catch (err) {
          setData(null);
          setError(err instanceof Error ? err.message : "Assistant failed");
        }
      }}>
        <textarea value={question} onChange={(event) => setQuestion(event.target.value)} rows={3} />
        <button type="submit">Ask</button>
      </form>
      {error && <Failure error={error} />}
      {data && (
        <section className="grid gap-3">
          {data.sections.map((section, index) => (
            <article key={index} className="panel p-4">
              <div className="text-xs uppercase text-gold">{section.kind}</div>
              <p className="mt-1 whitespace-pre-wrap text-sm">{section.text}</p>
            </article>
          ))}
          {data.narrative && <article className="panel p-4"><div className="text-xs uppercase text-gold">Model rephrase</div><p className="mt-1 text-sm whitespace-pre-wrap">{data.narrative}</p></article>}
          <p className="text-xs text-mute">{data.disclaimer} Model used: {data.model_used ? "yes" : "no"}.</p>
        </section>
      )}
    </div>
  );
}
