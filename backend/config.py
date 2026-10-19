"""Central configuration for Sahitya Setu.

Every tunable lives here: paths, model names, chunking parameters, retrieval
depths and API keys. Nothing else in the codebase should read os.environ
directly.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:  # dotenv is optional; real env vars still work
    pass


# ---------------------------------------------------------------- paths -----
BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.getenv("SS_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
CHROMA_DIR = DATA_DIR / "chroma"
BM25_DIR = DATA_DIR / "bm25"
DB_PATH = DATA_DIR / "sahitya_setu.db"
# Final text of every page as indexed (after OCR and header removal), read by
# qa/pages.py to place citations on exact pages.
PAGES_DIR = DATA_DIR / "pages"

for _d in (DATA_DIR, UPLOAD_DIR, CHROMA_DIR, BM25_DIR, PAGES_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------ pdf extraction ------
# A page with fewer than this many extractable characters is treated as a
# scanned image and routed through Tesseract instead of PyMuPDF.
DIGITAL_TEXT_MIN_CHARS = int(os.getenv("SS_DIGITAL_TEXT_MIN_CHARS", 60))
# A page whose letters are more than this fraction Latin-1/Latin Extended was
# typeset in a legacy non-Unicode Gujarati font and is OCR'd instead. Such
# pages measure 0.46-0.97; OCR'd and Unicode Gujarati measure ~0.
LEGACY_GLYPH_RATIO = float(os.getenv("SS_LEGACY_GLYPH_RATIO", 0.3))
# Tesseract language spec. "guj+eng" reads the mixed Gujarati/English that
# real books carry (English proper nouns, page furniture, quoted text);
# a "+"-joined spec loads both models for the same pass.
OCR_LANG = os.getenv("SS_OCR_LANG", "guj+eng")
OCR_DPI = int(os.getenv("SS_OCR_DPI", 300))
# Optional: absolute path to the tesseract binary if it is not on PATH.
TESSERACT_CMD = os.getenv("SS_TESSERACT_CMD", "")
# Optional: absolute path to poppler's bin dir (pdf2image dependency).
POPPLER_PATH = os.getenv("SS_POPPLER_PATH", "")


# ------------------------------------------------------------ chunking ------
CHUNK_SIZE_TOKENS = int(os.getenv("SS_CHUNK_SIZE", 400))
CHUNK_OVERLAP_TOKENS = int(os.getenv("SS_CHUNK_OVERLAP", 50))


# ---------------------------------------------------------- embeddings ------
EMBEDDING_MODEL = os.getenv("SS_EMBEDDING_MODEL", "intfloat/multilingual-e5-base")
EMBEDDING_DIM = 768
EMBEDDING_BATCH_SIZE = int(os.getenv("SS_EMBEDDING_BATCH_SIZE", 16))
# e5 models are trained with these instruction prefixes; dropping them costs
# several points of retrieval accuracy.
E5_QUERY_PREFIX = "query: "
E5_PASSAGE_PREFIX = "passage: "


# ----------------------------------------------------------- retrieval ------
BM25_TOP_K = int(os.getenv("SS_BM25_TOP_K", 10))
VECTOR_TOP_K = int(os.getenv("SS_VECTOR_TOP_K", 10))
FINAL_TOP_K = int(os.getenv("SS_FINAL_TOP_K", 5))
# Reciprocal Rank Fusion smoothing constant (60 is the value from the original
# Cormack et al. paper and the usual default).
RRF_K = int(os.getenv("SS_RRF_K", 60))


# ------------------------------------------------------- langgraph qa -------
MAX_QUERY_REWRITES = int(os.getenv("SS_MAX_QUERY_REWRITES", 2))
MAX_RETRIES = MAX_QUERY_REWRITES  # name used in the project brief
# How many of the top-k chunks must be graded relevant to proceed to answering.
MIN_RELEVANT_CHUNKS = int(os.getenv("SS_MIN_RELEVANT_CHUNKS", 1))


# ------------------------------------------------------------------ llm -----
# Flip this single line to swap the whole system between providers.
LLM_PROVIDER = os.getenv("SS_LLM_PROVIDER", "gemini")  # "gemini" | "groq"
# If the primary provider errors or is rate limited, retry once on the other.
LLM_AUTO_FALLBACK = os.getenv("SS_LLM_AUTO_FALLBACK", "true").lower() == "true"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# The project brief specifies Gemini 1.5 Flash, but 1.5 and 2.0 Flash have
# both been shut down. 3.8 Flash is Google's current stable Flash model;
# override with SS_GEMINI_MODEL to use another.
GEMINI_MODEL = os.getenv("SS_GEMINI_MODEL", "gemini-3.8-flash")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# Likewise llama-3.1-70b-versatile was decommissioned by Groq, and
# llama-3.3-70b-versatile is no longer served to new keys. gpt-oss-120b is a
# Groq production model and the one the Step 3 QA evaluation passed with.
GROQ_MODEL = os.getenv("SS_GROQ_MODEL", "openai/gpt-oss-120b")

LLM_TEMPERATURE = float(os.getenv("SS_LLM_TEMPERATURE", 0.1))
LLM_MAX_OUTPUT_TOKENS = int(os.getenv("SS_LLM_MAX_OUTPUT_TOKENS", 2048))
LLM_MAX_RETRIES = int(os.getenv("SS_LLM_MAX_RETRIES", 3))
# Retry pacing for 429/5xx. The provider's own retry hint (Retry-After header,
# Gemini's RetryInfo) takes precedence over the exponential backoff.
LLM_RETRY_BASE_DELAY = float(os.getenv("SS_LLM_RETRY_BASE_DELAY", 2))
# A 429 that gives no hint still waits this long: free tiers count requests
# per minute, so an immediate retry lands in the same exhausted window.
LLM_RATE_LIMIT_MIN_WAIT = float(os.getenv("SS_LLM_RATE_LIMIT_MIN_WAIT", 10))
# Give up rather than wait longer than this for one retry.
LLM_MAX_RETRY_WAIT = float(os.getenv("SS_LLM_MAX_RETRY_WAIT", 60))


# ------------------------------------------------------- summarization ------
# Chunks are grouped into batches of roughly this many tokens before being sent
# to the LLM for the map step of the hierarchical summary.
SUMMARY_MAP_BATCH_TOKENS = int(os.getenv("SS_SUMMARY_MAP_BATCH_TOKENS", 6000))
SUMMARY_LANGUAGE = os.getenv("SS_SUMMARY_LANGUAGE", "gujarati")
# Seconds to pause between summarisation calls. Gemini's free tier allows
# 15 requests/minute and a long book fires dozens of calls back to back.
SUMMARY_REQUEST_DELAY = float(os.getenv("SS_SUMMARY_REQUEST_DELAY", 4.5))


# ---------------------------------------------------------------- misc ------
NOT_FOUND_MESSAGE = (
    "આ પ્રશ્નનો ઉત્તર આપેલા પુસ્તકમાં મળ્યો નથી."
    "  (This question could not be answered from the uploaded book.)"
)
CORS_ORIGINS = os.getenv("SS_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
MAX_UPLOAD_MB = int(os.getenv("SS_MAX_UPLOAD_MB", 100))
