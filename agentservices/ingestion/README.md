# Ingestion Services

Specialized document processing microservices (future).

## Planned Services

### pdf-processor (Port 8091)
Advanced PDF processing beyond simple text extraction:
- Layout-aware extraction
- Table detection and OCR
- Form field recognition
- Signature detection
- Metadata extraction (author, creation date, etc.)

### ocr-service (Port 8092)
Dedicated OCR processing:
- Tesseract + EasyOCR
- Multiple language support
- Handwriting recognition
- Image preprocessing
- Confidence scoring

### media-transcriber (Port 8093)
Audio/video transcription:
- Whisper integration
- Speaker diarization
- Timestamp generation
- Multi-language support
- Subtitle generation

### table-extractor (Port 8094)
Specialized table extraction:
- CSV/Excel parsing
- PDF table detection
- HTML table extraction
- Structure preservation
- Header detection

## Why Separate Services?

Current ingestion runs in Celery workers with all processing bundled. Separating allows:

1. **Independent scaling** - OCR-heavy workloads scale OCR service only
2. **Resource isolation** - GPU for OCR, CPU for text processing
3. **Technology choice** - Python for OCR, Go for high-throughput parsing
4. **Fault isolation** - OCR failure doesn't block text extraction
5. **Versioning** - Upgrade OCR model without touching main system

## Structure (When Implemented)

```
agentservices/ingestion/
├── pdf-processor/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   └── README.md
├── ocr-service/
│   ├── Dockerfile (with Tesseract)
│   ├── requirements.txt
│   ├── app/
│   └── README.md
├── media-transcriber/
│   ├── Dockerfile (with Whisper)
│   ├── requirements.txt
│   ├── app/
│   └── README.md
└── table-extractor/
    ├── Dockerfile
    ├── requirements.txt
    ├── app/
    └── README.md
```

## Integration Pattern

```python
# Current: Celery task does everything
@celery_app.task
def ingest_document(document_id):
    parse()  # All formats in one task
    chunk()
    embed()
    index()

# Future: Specialized services
@celery_app.task
def ingest_document(document_id):
    if is_pdf_with_tables:
        await pdf_processor_service.extract(document_id)
    if needs_ocr:
        await ocr_service.process(document_id)
    if is_audio:
        await media_transcriber.transcribe(document_id)
    
    chunk()
    embed()
    index()
```

## API Pattern

Each service exposes REST API:

```bash
POST /process
{
  "document_id": "uuid",
  "source_url": "s3://bucket/file.pdf",
  "options": {
    "extract_tables": true,
    "ocr_language": "eng+fra"
  }
}

Response:
{
  "document_id": "uuid",
  "status": "completed",
  "extracted_text": "...",
  "tables": [...],
  "metadata": {...},
  "duration_ms": 1234
}
```

## Implementation Priority

1. **pdf-processor** - High (most common format)
2. **ocr-service** - Medium (needed for scanned documents)
3. **table-extractor** - Medium (common in reports/finances)
4. **media-transcriber** - Low (niche use case)
