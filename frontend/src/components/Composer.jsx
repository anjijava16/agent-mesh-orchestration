import { useEffect, useRef, useState } from 'react'

export default function Composer({ onSend, onStop, running, attachments, onDetach, framework }) {
  const [text, setText] = useState('')
  const areaRef = useRef(null)

  useEffect(() => {
    const el = areaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 190)}px`
  }, [text])

  const submit = () => {
    if (!text.trim() || running) return
    onSend(text.trim())
    setText('')
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="composer">
      <div className="composer__inner">
        {attachments.length > 0 && (
          <div className="composer__attached">
            {attachments.map((doc) => (
              <span className="pill pill--live" key={doc.id}>
                {doc.filename}
                <button onClick={() => onDetach(doc.id)} title="Remove from this turn">
                  ×
                </button>
              </span>
            ))}
          </div>
        )}

        <div className="composer__box">
          <textarea
            ref={areaRef}
            rows={1}
            value={text}
            placeholder="Ask the mesh…"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={running}
          />
          {running ? (
            <button className="btn" onClick={onStop}>
              Stop
            </button>
          ) : (
            <button className="btn btn--primary" onClick={submit} disabled={!text.trim()}>
              Send
            </button>
          )}
        </div>

        <div className="composer__hint">
          <span>Enter to send · Shift+Enter for a newline</span>
          <span>{framework}</span>
        </div>
      </div>
    </div>
  )
}
