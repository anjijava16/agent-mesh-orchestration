import { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

function Turn({ message }) {
  const isUser = message.role === 'user'
  return (
    <article className={`turn turn--${isUser ? 'user' : 'assistant'}`}>
      <div className="turn__who">{isUser ? 'You' : 'Orchestrator'}</div>
      <div className="turn__body">
        {isUser ? (
          message.content
        ) : (
          <>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content || ''}</ReactMarkdown>
            {message.streaming && !message.content && <span className="cursor" />}
          </>
        )}
        {!isUser && message.citations?.length > 0 && (
          <div className="citations">
            {message.citations.map((c, i) => (
              <span className="citation" key={`${c.marker}-${i}`}>
                {c.marker ?? `${c.filename}${c.page ? ` p.${c.page}` : ''}`}
              </span>
            ))}
          </div>
        )}
      </div>
    </article>
  )
}

export default function Transcript({ messages, error, framework }) {
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  return (
    <div className="transcript">
      <div className="transcript__inner">
        {error && <div className="banner">{error}</div>}

        {messages.length === 0 && !error ? (
          <div className="empty">
            <h2>Five agents, one answer.</h2>
            <p>
              The orchestrator routes your question to a researcher, a retriever, an analyst, a compliance
              reviewer and a writer — then owns what comes back.
            </p>
            <p>
              Currently running on <b>{framework}</b>. Switch runtimes in the panel on the right; the agents,
              tools and prompts stay identical.
            </p>
          </div>
        ) : (
          messages.map((m, i) => <Turn key={i} message={m} />)
        )}
        <div ref={endRef} />
      </div>
    </div>
  )
}
