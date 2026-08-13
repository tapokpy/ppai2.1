from app.models.sqlalchemy.engineering_doc import EngineeringDoc
from app.models.sqlalchemy.showroom_media import ShowroomMedia
from app.services.rag_engine import RAGEngine

ENGINEERING_DOC_SOURCE = "engineering_doc"
SHOWROOM_MEDIA_SOURCE = "showroom_media"


def index_engineering_doc(rag_engine: RAGEngine, doc: EngineeringDoc) -> None:
    """Indexes a CAD drawing's metadata (not the drawing file itself) into
    the same Chroma collection project docs use, tagged with a distinct
    `source`, so a RAG query can surface it alongside regular knowledge-
    base answers — e.g. "найди чертежи с рамкой 1000x500". Called right
    after the owning handler commits the EngineeringDoc row (cad.py's
    generation flow, documents.py's upload flow)."""
    lines = [f"Чертёж «{doc.project_name}» ({doc.doc_type})."]
    lines.append("Сгенерирован." if doc.is_generated else "Загружен пользователем.")

    extracted = doc.extracted_data or {}
    if extracted.get("dimensions"):
        lines.append(f"Размеры: {', '.join(extracted['dimensions'][:10])}")
    if extracted.get("texts"):
        lines.append(f"Текст на чертеже: {', '.join(extracted['texts'][:10])}")

    text = "\n".join(lines)
    rag_engine.upsert_documents(
        texts=[text],
        metadatas=[{"source": ENGINEERING_DOC_SOURCE, "doc_id": doc.id, "project_name": doc.project_name}],
        ids=[f"{ENGINEERING_DOC_SOURCE}:{doc.id}"],
    )


def index_showroom_media(rag_engine: RAGEngine, media: ShowroomMedia) -> None:
    """Same idea as index_engineering_doc, for downloaded showroom clips —
    lets RAG answer things like "какой ролик сейчас про запуск завода"."""
    text = f"Видеоролик «{media.title}» в медиатеке шоурума."
    rag_engine.upsert_documents(
        texts=[text],
        metadatas=[{"source": SHOWROOM_MEDIA_SOURCE, "media_id": media.id, "title": media.title}],
        ids=[f"{SHOWROOM_MEDIA_SOURCE}:{media.id}"],
    )
