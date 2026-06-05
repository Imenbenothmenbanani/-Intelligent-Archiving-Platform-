# Demo Application

The Intelligent Archiving Platform (IAP) is a document intelligence system that helps you search through archived documents using natural language. Upload a document, and the system automatically extracts text, breaks it into meaningful chunks, and indexes them for fast semantic search.

## What This Demo Does

This interactive demo showcases the complete document archiving and retrieval workflow:

1. **Upload documents** — PDF, images, or scanned documents
2. **Automatic text extraction** — OCR converts images and scans to searchable text
3. **Smart chunking** — Large documents are split into logical, searchable pieces
4. **Semantic indexing** — Documents are indexed for intelligent search
5. **Visual search** — Query your archive naturally and see results in an interactive 3D visualization

## Quick Start

### Prerequisites

- Python 3.11 or higher
- Poetry (Python package manager)
- All required backend services running (storage, OCR, embedding, etc.)

### Installation & Running

1. **Install dependencies:**
   ```bash
   poetry install
   ```

2. **Start the demo application:**
   ```bash
   poetry run uvicorn main:app --reload --port 8000
   ```

3. **Open in your browser:**
   Navigate to `http://localhost:8000`

You should see the demo interface with options to upload, search, and visualize your document archive.

## How It Works

### The Pipeline (Simplified)

```
Upload Document
       ↓
   OCR Extraction (convert images to text)
       ↓
Human Review (correct OCR if needed)
       ↓
Chunking (split into searchable pieces)
       ↓
Embedding (convert text to searchable vectors)
       ↓
Indexing (store in search database)
       ↓
Ready for Search!
```

### Searching Your Archive

1. **Enter a search query** — Natural language works best ("Find documents about contracts")
2. **Get smart results** — The system finds relevant chunks using semantic understanding + keyword matching
3. **Visualize results** — See where your query lands in the 3D embedding space
4. **Retrieve documents** — Download the original uploaded documents

## Tech Tips

### Performance

- **Large documents:** The system automatically handles multi-page documents by breaking them into manageable chunks (typically 200-500 words each)
- **Search speed:** Results appear in seconds thanks to hybrid indexing (keyword + semantic search)
- **First query:** Embedding the first query takes a bit longer; subsequent searches are faster

### Upload Tips

- **Image quality matters:** Clearer scans produce better OCR results
- **Supported formats:** PDF, PNG, JPG, and other common image formats
- **File size:** Works best with documents under 50MB

### Document Organization

- Each uploaded document gets a unique ID for tracking
- All document chunks are preserved, allowing you to trace search results back to their source
- The system maintains both the original file and extracted text for flexible retrieval

## Web Interface Features

- **Upload Panel** — Drag and drop documents or browse your computer
- **Search Bar** — Query your entire archive with natural language
- **Results Panel** — See matching chunks with highlighted page numbers and metadata
- **Visualization** — Interactive 3D plot showing how your query relates to indexed documents
- **Document Retrieval** — Click any result to download the original document
