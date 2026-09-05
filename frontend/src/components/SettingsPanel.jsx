/**
 * The operator console. Every control here maps to a field the backend already
 * understands, so nothing in this panel needs a server change to take effect.
 */
export default function SettingsPanel({ options, config, onChange, onSave, saving, dirty }) {
  if (!options) return <p className="muted">Loading configuration…</p>

  const providers = options.providers ?? []
  const activeProvider = providers.find((p) => p.id === config.provider)
  const models = activeProvider?.models ?? []

  const setField = (key) => (value) => onChange({ ...config, [key]: value })

  const toggleAgent = (name) => {
    const on = config.enabled_agents.includes(name)
    const next = on ? config.enabled_agents.filter((a) => a !== name) : [...config.enabled_agents, name]
    if (next.length === 0) return // the mesh needs at least one specialist
    onChange({ ...config, enabled_agents: next })
  }

  return (
    <>
      <div className="field">
        <label>Agent runtime</label>
        {(options.frameworks ?? []).map((fw) => {
          const selected = config.framework === fw.id
          return (
            <button
              key={fw.id}
              className={`choice ${selected ? 'choice--on' : ''} ${fw.installed ? '' : 'choice--off'}`}
              onClick={() => fw.installed && setField('framework')(fw.id)}
              disabled={!fw.installed}
            >
              <span className="choice__name">
                {fw.display_name}
                {!fw.installed && <span className="choice__flag">not installed</span>}
              </span>
              <span className="choice__desc">{fw.note || fw.description}</span>
            </button>
          )
        })}
      </div>

      <div className="field">
        <label>Provider</label>
        <select
          value={config.provider}
          onChange={(e) => {
            const provider = e.target.value
            const first = providers.find((p) => p.id === provider)?.models?.[0]?.id
            onChange({ ...config, provider, model: first ?? config.model })
          }}
        >
          {providers.map((p) => (
            <option key={p.id} value={p.id} disabled={!p.configured}>
              {p.id}
              {p.configured ? '' : ' — no API key'}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label>Model</label>
        <select value={config.model} onChange={(e) => setField('model')(e.target.value)}>
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
        {config.framework === 'claude_agent_sdk' && config.provider !== 'anthropic' && (
          <p className="field__note" style={{ color: 'var(--alert)' }}>
            The Claude Agent SDK runs Claude models. Pick an Anthropic model, or switch runtime.
          </p>
        )}
      </div>

      <div className="field">
        <label>
          Temperature — <span style={{ color: 'var(--signal)' }}>{config.temperature.toFixed(2)}</span>
        </label>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={config.temperature}
          onChange={(e) => setField('temperature')(parseFloat(e.target.value))}
        />
        <p className="field__note">
          Retrieval-grounded answers want this low. Above ~0.5 the writer starts paraphrasing sources
          instead of citing them.
        </p>
      </div>

      <div className="field">
        <label>Max tokens</label>
        <input
          type="number"
          min="256"
          max="32000"
          step="256"
          value={config.max_tokens}
          onChange={(e) => setField('max_tokens')(parseInt(e.target.value || '4096', 10))}
        />
      </div>

      <div className="field">
        <label>Active specialists</label>
        {(options.agents ?? []).map((agent) => {
          const on = config.enabled_agents.includes(agent.name)
          return (
            <button
              key={agent.name}
              className={`choice ${on ? 'choice--on' : ''}`}
              onClick={() => toggleAgent(agent.name)}
            >
              <span className="choice__name">
                {agent.display_name}
                <span className="choice__flag" style={{ color: on ? 'var(--ok)' : 'var(--ink-faint)' }}>
                  {on ? 'on' : 'off'}
                </span>
              </span>
              <span className="choice__desc">{agent.description}</span>
            </button>
          )
        })}
      </div>

      <div className="field">
        <label>Memory & retrieval</label>
        <div className="toggle">
          <span>Long-term memory (OpenSearch)</span>
          <input
            type="checkbox"
            checked={config.use_long_term_memory}
            onChange={(e) => setField('use_long_term_memory')(e.target.checked)}
          />
        </div>
        <div className="toggle">
          <span>Hybrid search (BM25 + kNN)</span>
          <input
            type="checkbox"
            checked={config.use_hybrid_search}
            onChange={(e) => setField('use_hybrid_search')(e.target.checked)}
          />
        </div>
        <p className="field__note">
          Short-term history always persists to Postgres. Long-term memory distils durable facts after the
          turn and recalls them semantically in later conversations.
        </p>
      </div>

      <button className="btn btn--primary" style={{ width: '100%' }} onClick={onSave} disabled={saving || !dirty}>
        {saving ? 'Saving…' : dirty ? 'Save configuration' : 'Saved'}
      </button>
    </>
  )
}
