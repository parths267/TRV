"use client";

export function Loading({ label = "Loading market data" }: { label?: string }) {
  return <div className="panel p-6 text-mute">{label}…</div>;
}

export function Failure({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="panel p-6">
      <div className="font-medium">This view could not be loaded.</div>
      <p className="mt-2 text-sm text-mute">{error}</p>
      {onRetry && (
        <button className="mt-4" type="button" onClick={onRetry}>Retry</button>
      )}
    </div>
  );
}

export function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="panel p-6">
      <div className="font-medium">{title}</div>
      <p className="mt-2 text-sm text-mute">{body}</p>
    </div>
  );
}
