import hashlib
import io
import uuid
from pathlib import Path
import pdfplumber
import fitz  # PyMuPDF
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

CHUNK_SIZE = settings.chunk_size
CHUNK_OVERLAP = settings.chunk_overlap


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _extract_text_blocks(pdf_path: Path) -> list[dict]:
    """Extract text blocks with page metadata using PyMuPDF."""
    blocks = []
    doc = fitz.open(str(pdf_path))
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")
        if text.strip():
            blocks.append({"page": page_num, "text": text, "type": "text"})
        else:
            # Page has no text layer - flag for OCR fallback
            blocks.append({"page": page_num, "text": "", "type": "scanned", "needs_ocr": True})
    doc.close()
    return blocks


def _extract_tables(pdf_path: Path) -> list[dict]:
    """Extract tables from each page using pdfplumber."""
    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_tables = page.extract_tables()
            for table_idx, table in enumerate(page_tables):
                if not table:
                    continue
                # Convert table rows to markdown-ish text for embedding
                rows_text = []
                for row in table:
                    clean_row = [str(cell or "").strip() for cell in row]
                    rows_text.append(" | ".join(clean_row))
                table_text = "\n".join(rows_text)
                if table_text.strip():
                    tables.append({
                        "page": page_num,
                        "table_index": table_idx,
                        "text": table_text,
                        "type": "table",
                        "row_count": len(table),
                    })
    return tables


def _ocr_page(pdf_path: Path, page_num: int) -> str:
    """OCR fallback for scanned pages. Returns empty string if tesseract unavailable."""
    try:
        import pytesseract
        from PIL import Image
        doc = fitz.open(str(pdf_path))
        page = doc[page_num - 1]
        pix = page.get_pixmap(dpi=200)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        text = pytesseract.image_to_string(img)
        doc.close()
        return text
    except Exception as e:
        logger.warning("ocr_failed", page=page_num, error=str(e))
        return ""


def _chunk_text(text: str, source_meta: dict) -> list[dict]:
    """
    Split text into chunks of ~CHUNK_SIZE tokens (approximated by word count * 1.3).
    Uses CHUNK_OVERLAP words of overlap to avoid splitting reasoning units.
    """
    words = text.split()
    approx_token_size = int(CHUNK_SIZE / 1.3)
    approx_overlap = int(CHUNK_OVERLAP / 1.3)

    chunks = []
    start = 0
    chunk_idx = 0
    while start < len(words):
        end = min(start + approx_token_size, len(words))
        chunk_words = words[start:end]
        chunk_text = " ".join(chunk_words)
        if chunk_text.strip():
            chunk_id = str(uuid.uuid4())
            chunks.append({
                "id": chunk_id,
                "text": chunk_text,
                "chunk_index": chunk_idx,
                **source_meta,
            })
            chunk_idx += 1
        start = end - approx_overlap
        if start >= end:
            break
    return chunks


def extract_and_chunk(pdf_path: Path, document_id: str, tenant_id: str) -> tuple[list[dict], bool]:
    """
    Main entry point. Returns (chunks, ocr_used).
    Each chunk: {id, text, page, type, chunk_index, document_id, tenant_id, ...}
    """
    logger.info("pdf_extract_start", document_id=document_id, path=str(pdf_path))
    ocr_used = False
    all_chunks = []

    # 1. Extract tables first (kept as whole units)
    tables = _extract_tables(pdf_path)
    for table in tables:
        # Large tables (>1500 tokens approx) split by row groups
        words = table["text"].split()
        if len(words) > 1150:  # ~1500 tokens
            row_lines = table["text"].split("\n")
            group_size = 20
            for g_start in range(0, len(row_lines), group_size):
                group = "\n".join(row_lines[g_start: g_start + group_size])
                all_chunks.append({
                    "id": str(uuid.uuid4()),
                    "text": group,
                    "page": table["page"],
                    "type": "table",
                    "table_index": table["table_index"],
                    "row_group": g_start // group_size,
                    "chunk_index": len(all_chunks),
                    "document_id": document_id,
                    "tenant_id": tenant_id,
                })
        else:
            all_chunks.append({
                "id": str(uuid.uuid4()),
                "text": table["text"],
                "page": table["page"],
                "type": "table",
                "table_index": table["table_index"],
                "chunk_index": len(all_chunks),
                "document_id": document_id,
                "tenant_id": tenant_id,
            })

    # 2. Extract prose text blocks
    text_blocks = _extract_text_blocks(pdf_path)
    for block in text_blocks:
        text = block["text"]
        if block.get("needs_ocr") and not text.strip():
            text = _ocr_page(pdf_path, block["page"])
            if text.strip():
                ocr_used = True

        if not text.strip():
            continue

        source_meta = {
            "page": block["page"],
            "type": "text",
            "document_id": document_id,
            "tenant_id": tenant_id,
        }
        chunks = _chunk_text(text, source_meta)
        # Fix chunk_index globally
        for chunk in chunks:
            chunk["chunk_index"] = len(all_chunks)
            all_chunks.append(chunk)

    logger.info("pdf_extract_done", document_id=document_id, chunk_count=len(all_chunks), ocr_used=ocr_used)
    return all_chunks, ocr_used
