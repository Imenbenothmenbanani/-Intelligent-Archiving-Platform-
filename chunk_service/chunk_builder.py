# chunk_builder.py

import os
import re
import html as html_module
import json
from typing import List, Dict
from pathlib import Path
from transformers import AutoTokenizer

# ---------------------------
# Text Cleaning
# ---------------------------

def clean_block_content(content: str, label: str = "") -> str:
    """
    Strip all HTML tags, markdown image syntax, heading markers, and
    HTML entities from a block's content so only plain readable text
    remains.  This prevents <div>, <img>, and markdown code from
    entering the chunk corpus.

    Steps
    -----
    1. Remove HTML tags  (<div …>, <img …>, </div>, etc.)
    2. Remove markdown image syntax  ![alt](src)
    3. Strip leading markdown heading markers  (# ## ###)
    4. Unescape HTML entities  (&amp; → & etc.)
    5. Drop blank lines and strip each line
    """
    if not content:
        return ""

    # 1. Remove all HTML tags
    text = re.sub(r"<[^>]+>", " ", content)

    # 2. Remove markdown image syntax  ![alt](url)
    text = re.sub(r"!\[.*?\]\(.*?\)", " ", text)

    # 3. Strip leading markdown heading markers (#, ##, ###, …)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)

    # 4. Unescape HTML entities
    text = html_module.unescape(text)

    # 5. Collapse whitespace — keep meaningful line breaks
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]           # drop blank lines
    text  = "\n".join(lines)

    return text.strip()


# ---------------------------
# Helper functions
# ---------------------------

def normalize_text(text: str) -> str:
    """Clean OCR text: remove extra spaces, normalize line breaks."""
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def count_tokens(text: str, tokenizer) -> int:
    """Count tokens using the specified tokenizer."""
    return len(tokenizer.encode(text, add_special_tokens=False))

def merge_blocks(blocks: List[Dict]) -> Dict:
    """Merge multiple blocks into a single chunk with combined bbox and polygons."""
    all_bboxes = [b['block_bbox'] for b in blocks if b.get("block_bbox")]
    if not all_bboxes:
        bbox = [0, 0, 0, 0]
    else:
        min_x = min([b[0] for b in all_bboxes])
        min_y = min([b[1] for b in all_bboxes])
        max_x = max([b[2] for b in all_bboxes])
        max_y = max([b[3] for b in all_bboxes])
        bbox = [min_x, min_y, max_x, max_y]

    return {"blocks": blocks, "bbox": bbox}

def split_text_with_overlap(text: str, tokenizer, max_tokens: int, overlap: int) -> List[str]:
    """Split text into chunks with overlap using tokens."""
    tokens = tokenizer.encode(text, add_special_tokens=False)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = tokenizer.decode(chunk_tokens)
        chunks.append(chunk_text)
        if end == len(tokens):
            break
        start += max_tokens - overlap
    return chunks

# ---------------------------
# Main function
# ---------------------------

def build_chunks(
    ocr_json: Dict,
    document_id: str,
    max_tokens: int = 500,
    min_tokens: int = 150,
    overlap_ratio: float = 0.2,
    dry_run: bool = False,
    output_dir: str = "./chunks"
) -> Dict:
    """
    Build per-page, per-document JSON chunk file ready for embeddings.
    Uses Qwen3 tokenizer for token counting.

    All block content is cleaned of HTML tags, markdown image syntax,
    and heading markers before being chunked — only plain text enters
    the corpus.
    """
    # Use Qwen3 tokenizer for token counting
    tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-Embedding-0.6B")

    # Group blocks by page
    page_blocks = {}
    for block in ocr_json.get("parsing_res_list", []):
        page_idx = block.get("page_index") or 1
        page_blocks.setdefault(page_idx, []).append(block)

    all_chunks = []
    for page_num, blocks in page_blocks.items():
        # Sort safely by block_order
        blocks_sorted = sorted(
            blocks,
            key=lambda b: (b.get("block_order") is None, b.get("block_order") or 0)
        )

        # Merge consecutive text blocks with paragraph_title or image
        logical_sections = []
        current_section = []

        for block in blocks_sorted:
            label = block.get("block_label")
            if label in ["text", "paragraph_title", "image", "doc_title", "ocr"]:
                current_section.append(block)
            else:
                if current_section:
                    logical_sections.append(current_section)
                    current_section = []
        if current_section:
            logical_sections.append(current_section)

        # Build chunks per section
        chunk_index = 1
        overlap_tokens = int(max_tokens * overlap_ratio)

        for section_blocks in logical_sections:
            merged = merge_blocks(section_blocks)

            # ── Clean content before joining ──────────────────────────
            texts = []
            for b in section_blocks:
                raw = b.get("block_content", "")
                label = b.get("block_label", "")
                cleaned = clean_block_content(raw, label)
                if cleaned:
                    texts.append(cleaned)

            section_text   = " ".join(texts)
            section_text   = normalize_text(section_text)

            if not section_text:
                continue  # skip entirely empty sections after cleaning

            section_tokens = count_tokens(section_text, tokenizer)

            if section_tokens <= max_tokens:
                chunks_text = [section_text]
            else:
                chunks_text = split_text_with_overlap(
                    section_text, tokenizer, max_tokens, overlap_tokens
                )

            for chunk_text in chunks_text:
                chunk_id = f"{document_id}_p{page_num}_c{chunk_index}"
                chunk_data = {
                    "chunk_id":           chunk_id,
                    "document_id":        document_id,
                    "page":               page_num,
                    "chunk_index":        chunk_index,
                    "text":               chunk_text,
                    "token_count":        count_tokens(chunk_text, tokenizer),
                    "bbox":               merged["bbox"],
                    "block_ids":          [b.get("block_id") for b in section_blocks],
                    "block_bboxes":       [b.get("block_bbox") for b in section_blocks if b.get("block_bbox")],
                    "contains_image_ocr": any(b.get("block_label") == "image" for b in section_blocks),
                }

                if dry_run:
                    print(f"Chunk {chunk_id}: {chunk_data['token_count']} tokens | {chunk_text[:60]!r}")

                all_chunks.append(chunk_data)
                chunk_index += 1

    document_chunks = {
        "document_id": document_id,
        "chunk_count": len(all_chunks),
        "chunks":      all_chunks,
    }

    if not dry_run:
        os.makedirs(output_dir, exist_ok=True)
        out_file = Path(output_dir) / f"{document_id}_chunks.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(document_chunks, f, ensure_ascii=False, indent=2)

    return document_chunks