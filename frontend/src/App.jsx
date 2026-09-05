import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Composer from './components/Composer.jsx'
import FilesPanel from './components/FilesPanel.jsx'
import SettingsPanel from './components/SettingsPanel.jsx'
import TracePanel from './components/TracePanel.jsx'
import Transcript from './components/Transcript.jsx'
import { useChat } from './hooks/useChat.js'
import { api } from './lib/api.js'

const TABS = [
  { id: 'trace', label: 'Trace' },
  { id: 'config', label: 'Config' },
  { id: 'files', label: 'Files' }
]

const POLL_MS = 3000

export default function App() {
  const chat = useChat()
  const [options, setOptions] = useState(null)
  const [config, setConfig] = useState(null)
  const [savedConfig, setSavedConfig] = useState(null)
  const [saving, setSaving] = useState(false)
  const [tab, setTab] = useState('trace')
  const [threads, setThreads] = useState([])
  const [files, setFiles] = useState([])
  const [attached, setAttached] = useState([])
  const [health, setHealth] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [bootError, setBootError] = useState(null)
  const pollRef = useRef(null)

  // ---- boot -------------------------------------------------------------
  useEffect(() => {
    ;(async () => {
      try {
        const [opts, stored] = await Promise.all([api.options(), api.getSettings()])
        setOptions(opts)
        const initial = {
          framework: stored.framework,
          provider: stored.provider,
          model: stored.model,
          temperature: stored.temperature,
          max_tokens: stored.max_tokens,
          enabled_agents: stored.enabled_agents?.length ? stored.enabled_agents : opts.agents.map((a) => a.name),
          use_long_term_memory: stored.use_long_term_memory,
          use_hybrid_search: stored.use_hybrid_search
        }
        setConfig(initial)
        setSavedConfig(initial)
      } catch (err) {
        setBootError(err.message)
      }
      refreshThreads()
      refreshFiles()
      refreshHealth()
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const refreshThreads = useCallback(async () => {
    try {
      setThreads((await api.conversations()).items ?? [])
    } catch {
      /* the sidebar is not worth an error banner */
    }
  }, [])

  const refreshFiles = useCallback(async () => {
    try {
      setFiles((await api.files()).items ?? [])
    } catch {
      /* ignore */
    }
  }, [])

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await api.health())
    } catch {
      setHealth({ status: 'unreachable' })
    }
  }, [])

  // Poll only while something is mid-ingestion. An idle console makes no requests.
  const pending = useMemo(
    () => files.some((f) => !['indexed', 'failed'].includes(f.status)),
    [files]
  )
  useEffect(() => {
    clearInterval(pollRef.current)
    if (pending) pollRef.current = setInterval(refreshFiles, POLL_MS)
    return () => clearInterval(pollRef.current)
  }, [pending, refreshFiles])

  // ---- actions ----------------------------------------------------------
  const send = async (text) => {
    await chat.send(text, config, attached.map((f) => f.id))
    refreshThreads()
    refreshHealth()
  }

  const openThread = async (id) => {
    try {
      const detail = await api.conversation(id)
      chat.reset(
        id,
        detail.messages
          .filter((m) => m.role === 'user' || m.role === 'assistant')
          .map((m) => ({
            role: m.role,
            content: m.content,
            citations: m.metadata?.citations ?? [],
            streaming: false
          }))
      )
    } catch (err) {
      chat.reset()
    }
  }

  const saveConfig = async () => {
    setSaving(true)
    try {
      await api.saveSettings(config)
      setSavedConfig(config)
    } finally {
      setSaving(false)
    }
  }

  const upload = async (file) => {
    setUploading(true)
    try {
      await api.upload(file, chat.conversationId)
      await refreshFiles()
    } catch (err) {
      alert(err.message)
    } finally {
      setUploading(false)
    }
  }

  const toggleAttach = (file) =>
    setAttached((prev) =>
      prev.some((f) => f.id === file.id) ? prev.filter((f) => f.id !== file.id) : [...prev, file]
    )

  const dirty = useMemo(
    () => JSON.stringify(config) !== JSON.stringify(savedConfig),
    [config, savedConfig]
  )

  const dependencyDot = () => {
    if (!health) return 'dot'
    if (health.status === 'healthy') return 'dot dot--ok'
    if (health.status === 'unreachable') return 'dot dot--bad'
    return 'dot dot--warn'
  }

  if (bootError) {
    return (
      <div className="empty">
        <h2>Backend unreachable</h2>
        <p>{bootError}</p>
        <p className="muted">Check that the API is up: docker compose ps backend</p>
      </div>
    )
  }

  if (!config) return <div className="empty"><p>Starting console…</p></div>

  const frameworkLabel =
    options?.frameworks?.find((f) => f.id === config.framework)?.display_name ?? config.framework

  return (
    <div className="shell">
      {/* ------------------------------------------------------- left rail */}
      <aside className="rail">
        <div className="rail__brand">
          <div className="rail__mark">
            Agent<span>Mesh</span>
          </div>
          <div className="rail__sub">multi-agent console</div>
        </div>

        <button className="btn btn--wide" style={{ marginTop: 12 }} onClick={() => chat.reset()}>
          + New thread
        </button>

        <div className="section-label">
          <span>Threads</span>
          <span>{threads.length}</span>
        </div>

        <div className="rail__list">
          {threads.length === 0 && <p className="muted" style={{ padding: '0 8px' }}>No threads yet.</p>}
          {threads.map((t) => (
            <button
              key={t.id}
              className={`thread ${chat.conversationId === t.id ? 'thread--active' : ''}`}
              onClick={() => openThread(t.id)}
            >
              <span className="thread__title">{t.title}</span>
              <span className="thread__meta">
                {t.framework} · {t.total_tokens || 0} tok
              </span>
            </button>
          ))}
        </div>
      </aside>

      {/* ----------------------------------------------------------- stage */}
      <main className="stage">
        <div className="statusbar">
          <span className="status-chip">
            <span className={dependencyDot()} />
            <b>{health?.status ?? '…'}</b>
          </span>
          <span className="status-chip">
            runtime <b>{frameworkLabel}</b>
          </span>
          <span className="status-chip">
            model <b>{config.model}</b>
          </span>
          <span className="statusbar__spacer" />
          {chat.running && (
            <span className="status-chip">
              <span className="dot dot--warn" /> <b>running</b>
            </span>
          )}
          {health?.breakers &&
            Object.entries(health.breakers)
              .filter(([, b]) => b.state !== 'closed')
              .map(([name, b]) => (
                <span className="status-chip" key={name}>
                  <span className="dot dot--bad" /> <b>{name}: {b.state}</b>
                </span>
              ))}
        </div>

        <Transcript messages={chat.messages} error={chat.error} framework={frameworkLabel} />

        <Composer
          onSend={send}
          onStop={chat.stop}
          running={chat.running}
          attachments={attached}
          onDetach={(id) => setAttached((prev) => prev.filter((f) => f.id !== id))}
          framework={frameworkLabel}
        />
      </main>

      {/* ------------------------------------------------------- inspector */}
      <aside className="inspector">
        <div className="tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`tab ${tab === t.id ? 'tab--active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
              {t.id === 'files' && files.length > 0 ? ` (${files.length})` : ''}
            </button>
          ))}
        </div>

        <div className="inspector__body">
          {tab === 'trace' && <TracePanel trace={chat.trace} runMeta={chat.runMeta} />}
          {tab === 'config' && (
            <SettingsPanel
              options={options}
              config={config}
              onChange={setConfig}
              onSave={saveConfig}
              saving={saving}
              dirty={dirty}
            />
          )}
          {tab === 'files' && (
            <FilesPanel
              files={files}
              onUpload={upload}
              onDelete={async (id) => {
                await api.deleteFile(id)
                setAttached((prev) => prev.filter((f) => f.id !== id))
                refreshFiles()
              }}
              onReingest={async (id) => {
                await api.reingest(id)
                refreshFiles()
              }}
              onAttach={toggleAttach}
              attachedIds={attached.map((f) => f.id)}
              busy={uploading}
            />
          )}
        </div>
      </aside>
    </div>
  )
}
