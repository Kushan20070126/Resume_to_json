import fitz
from fastapi import HTTPException, UploadFile

from app.core.config import get_settings


class PDFService:
    ALLOWED_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}

    def __init__(self) -> None:
        self.settings = get_settings()

    async def read_pdf_bytes(self, file: UploadFile) -> bytes:
        content_type = (file.content_type or "").lower()
        if content_type not in self.ALLOWED_CONTENT_TYPES and not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Invalid file type. Please upload a PDF file.")

        pdf_bytes = await file.read()
        if not pdf_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        max_bytes = self.settings.max_upload_size_mb * 1024 * 1024
        if len(pdf_bytes) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"PDF exceeds max size of {self.settings.max_upload_size_mb} MB.",
            )

        return pdf_bytes

    def extract_text_from_pdf_bytes(self, pdf_bytes: bytes) -> tuple[str, int]:
        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                pages = [doc.load_page(i).get_text("text").strip() for i in range(len(doc))]
            extracted_text = "\n".join(page for page in pages if page)
            return extracted_text, len(pages)
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=400, detail=f"Could not parse PDF: {exc}") from exc
