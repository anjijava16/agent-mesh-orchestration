import { useCallback, useRef, useState } from 'react'
import { streamChat } from '../lib/api'

/**
 * Owns one conversation's live state.
 *
 * The stream produces two independent things: prose (goes into the last
 * assistant turn) and telemetry (goes into the trace panel). Keeping them in
 * separate pieces of state is what stops a burst of tool events from
 * re-rendering the whole transcript.
 */
export function useChat() {
  const [messages, setMessages] = useState([])
  const [trace, setTrace] = useState([])
  const [running, setRunning] = useState(false)
  const [conversationId, setConversationId] = useState(null)
  const [error, setError] = useState(null)
  const [runMeta, setRunMeta] = useState(null)
  const abortRef = useRef(null)

  const reset = useCallback((id = null, history = []) => {
    abortRef.current?.abort()
    setConversationId(id)
    setMessages(history)
    setTrace([])
    setError(null)
    setRunMeta(null)
    setRunning(false)
  }, [])

  const stop = useCallback(() => {
    abortRef.current?.abort()
    setRunning(false)
  }, [])

  const send = useCallback(
    async (text, config, documentIds = []) => {
      if (!text.trim() || running) return

      const controller = new AbortController()
      abortRef.current = controller

      setError(null)
      setRunning(true)
      setTrace([])
      setMessages((prev) => [
        ...prev,
        { role: 'user', content: text },
        { role: 'assistant', content: '', citations: [], streaming: true }
      ])

      const push = (row) => setTrace((prev) => [...prev, { ...row, at: Date.now() }])

      try {
        await streamChat(
          {
            message: text,
            conversation_id: conversationId,
            framework: config.framework,
            provider: config.provider,
            model: config.model,
            temperature: config.temperature,
            max_tokens: config.max_tokens,
            enabled_agents: config.enabled_agents,
            use_long_term_memory: config.use_long_term_memory,
            document_ids: documentIds
          },
          {
            signal: controller.signal,
            onEvent: (event) => {
              const { type, data = {}, agent } = event

              switch (type) {
                case 'run_started':
                  if (data.conversation_id) setConversationId(data.conversation_id)
                  setRunMeta({ framework: data.framework, model: data.model, memories: data.memories_recalled })
                  push({ kind: 'agent', agent: 'orchestrator', label: `run started · ${data.framework ?? ''}` })
                  break

                case 'plan':
                  push({ kind: 'agent', agent: 'orchestrator', label: 'plan', detail: (data.plan || []).join(' → ') })
                  break

                case 'handoff':
                  push({ kind: 'agent', agent: agent ?? 'orchestrator', label: `→ ${data.to}`, detail: data.instruction })
                  break

                case 'agent_started':
                  push({ kind: 'agent', agent, label: 'started' })
                  break

                case 'agent_finished':
                  push({ kind: 'agent', agent, label: 'finished', detail: data.summary })
                  break

                case 'tool_call':
                  push({ kind: 'tool', agent, label: data.tool, detail: JSON.stringify(data.input ?? {}) })
                  break

                case 'tool_result':
                  push({ kind: 'tool', agent, label: `${data.tool ?? 'result'} ✓`, detail: data.output, ms: data.duration_ms })
                  break

                case 'token':
                  setMessages((prev) => {
                    const next = [...prev]
                    const last = next[next.length - 1]
                    if (last?.role === 'assistant') last.content += data.text ?? ''
                    return next
                  })
                  break

                case 'citation':
                  setMessages((prev) => {
                    const next = [...prev]
                    const last = next[next.length - 1]
                    if (last?.role === 'assistant') {
                      const seen = new Set(last.citations.map((c) => c.marker))
                      last.citations = [
                        ...last.citations,
                        ...(data.citations || []).filter((c) => c.marker && !seen.has(c.marker))
                      ]
                    }
                    return next
                  })
                  break

                case 'error':
                  setError(data.message ?? 'The run failed.')
                  push({ kind: 'error', agent: agent ?? 'system', label: 'error', detail: data.message })
                  break

                case 'run_finished':
                  setRunMeta((prev) => ({ ...(prev || {}), duration_ms: data.duration_ms, tokens: data.total_tokens }))
                  push({
                    kind: 'agent',
                    agent: 'orchestrator',
                    label: 'run finished',
                    ms: data.duration_ms,
                    detail: data.total_tokens ? `${data.total_tokens} tokens` : undefined
                  })
                  break

                default:
                  break
              }
            }
          }
        )
      } catch (err) {
        if (err.name !== 'AbortError') setError(err.message)
      } finally {
        setMessages((prev) => {
          const next = [...prev]
          const last = next[next.length - 1]
          if (last?.role === 'assistant') last.streaming = false
          return next
        })
        setRunning(false)
      }
    },
    [conversationId, running]
  )

  return { messages, trace, running, error, runMeta, conversationId, send, stop, reset, setMessages }
}
