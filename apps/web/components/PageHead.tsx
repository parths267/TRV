export function PageHead({
  kicker,
  title,
  lede,
  aside,
}: {
  kicker?: string;
  title: string;
  lede?: string;
  aside?: React.ReactNode;
}) {
  return (
    <header className="page-head">
      <div className="min-w-0">
        {kicker && <div className="page-kicker">{kicker}</div>}
        <h1 className="page-title">{title}</h1>
        {lede && <p className="page-lede">{lede}</p>}
      </div>
      {aside}
    </header>
  );
}
