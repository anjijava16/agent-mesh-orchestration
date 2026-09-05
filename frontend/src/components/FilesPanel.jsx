import { useState } from 'react'

const BADGE = {
  indexed: 'badge--indexed',
  failed: 'badge--failed'
}

export default function FilesPanel({ files, onUpload, onDelete, onReingest, onAttach, attachedIds, busy }) {
  const [dragging, setDragging] = useState(false)

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    Array.from(e.dataTransfer.files).forEach(onUpload)
  }

  return (
    <>
      <label
        className={`drop ${dragging ? 'drop--over' : ''}`}
        style={{ display: 'block', cursor: 'pointer' }}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <input
          type="file"
          multiple
          hidden
          onChange={(e) => {
            Array.from(e.target.files).forEach(onUpload)
            e.target.value = ''
          }}
        />
        {busy ? 'Uploading…' : 'Drop files or click to upload'}
        <div style={{ marginTop: 5, fontSize: 10 }}>pdf · docx · xlsx · csv · md · txt · html · json</div>
      </label>

      {files.length === 0 ? (
        <p className="muted">
          No documents yet. Uploads go to object storage, then through Redis and Celery for parsing,
          chunking, embedding and indexing.
        </p>
      ) : (
        files.map((file) => {
          const attached = attachedIds.includes(file.id)
          const settled = file.status === 'indexed' || file.status === 'failed'
          return (
            <div className="file-row" key={file.id}>
              <div className="file-row__top">
                <span className="file-row__name" title={file.filename}>
                  {file.filename}
                </span>
                <span className={`badge ${BADGE[file.status] ?? 'badge--busy'}`}>{file.status}</span>
              </div>
              <div className="file-row__meta">
                <span>{(file.size_bytes / 1024).toFixed(0)} KB</span>
                {file.chunk_count > 0 && <span>{file.chunk_count} chunks</span>}
                {file.page_count > 0 && <span>{file.page_count} pages</span>}
              </div>
              {file.error && (
                <div className="file-row__meta" style={{ color: 'var(--alert)' }}>
                  {file.error.slice(0, 140)}
                </div>
              )}
              <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                {file.status === 'indexed' && (
                  <button className="btn btn--sm" onClick={() => onAttach(file)}>
                    {attached ? 'Detach' : 'Scope to turn'}
                  </button>
                )}
                {settled && (
                  <button className="btn btn--sm" onClick={() => onReingest(file.id)}>
                    Reingest
                  </button>
                )}
                <button className="btn btn--sm" onClick={() => onDelete(file.id)}>
                  Delete
                </button>
              </div>
            </div>
          )
        })
      )}
    </>
  )
}
