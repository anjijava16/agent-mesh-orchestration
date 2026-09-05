export default function TracePanel({ trace, runMeta }) {
  if (trace.length === 0) {
    return (
      <p className="muted">
        Nothing running. Agent hand-offs, tool calls and timings appear here live while a turn executes.
      </p>
    )
  }

  return (
    <>
      {runMeta && (
        <div className="file-row" style={{ marginBottom: 14 }}>
          <div className="file-row__meta" style={{ flexWrap: 'wrap' }}>
            <span>runtime: {runMeta.framework}</span>
            <span>model: {runMeta.model}</span>
            {runMeta.memories > 0 && <span>{runMeta.memories} memories recalled</span>}
            {runMeta.duration_ms != null && <span>{runMeta.duration_ms} ms</span>}
            {runMeta.tokens > 0 && <span>{runMeta.tokens} tokens</span>}
          </div>
        </div>
      )}

      <div className="trace">
        {trace.map((row, i) => (
          <div className={`trace__row trace__row--${row.kind}`} key={i}>
            <div className="trace__head">
              <span className="trace__agent">{row.agent}</span>
              <span className={row.kind === 'tool' ? 'trace__tool' : 'muted'}>{row.label}</span>
              {row.ms != null && <span className="trace__ms">{row.ms} ms</span>}
            </div>
            {row.detail && <div className="trace__detail">{String(row.detail).slice(0, 320)}</div>}
          </div>
        ))}
      </div>
    </>
  )
}
