"""Central configuration for Sahitya Setu.

Every tunable lives here: paths, model names, chunking parameters, retrieval
depths and API keys. Nothing else in the codebase should read os.environ
directly.
"""
import os
import re
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:  # dotenv is optional; real env vars still work
    pass


# ---------------------------------------------------------------- paths -----
BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.getenv("SS_DATA_DIR", BASE_DIR / "data"))
# Holds a PDF only while it is being ingested; cleared when the server starts.
TEMP_UPLOAD_DIR = DATA_DIR / "tmp_uploads"
# Supabase Postgres, through the session pooler (it works over IPv4).
DATABASE_URL = os.getenv("SS_DATABASE_URL", "")
# PDF storage. The project URL can be worked out from the database user,
# postgres.<project-ref>, so only the secret key has to be set.
_project_ref = re.search(r"//postgres\.([a-z0-9]+):", DATABASE_URL)
SUPABASE_URL = os.getenv(
    "SS_SUPABASE_URL",
    f"https://{_project_ref.group(1)}.supabase.co" if _project_ref else "",
).rstrip("/")
SUPABASE_SECRET = os.getenv("SS_SUPABASE_SECRET", "")

TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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
# How many of the top-k chunks must be graded relevant to proceed to answering.
MIN_RELEVANT_CHUNKS = int(os.getenv("SS_MIN_RELEVANT_CHUNKS", 1))


# ------------------------------------------------------------------ llm -----
# Flip this single line to swap the whole system between providers.
LLM_PROVIDER = os.getenv("SS_LLM_PROVIDER", "gemini")  # "gemini" | "groq"
# If the primary provider errors or is rate limited, retry once on the other.
LLM_AUTO_FALLBACK = os.getenv("SS_LLM_AUTO_FALLBACK", "true").lower() == "true"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Gemini 1.5 and 2.0 Flash have been shut down. 3.8 Flash is Google's current
# stable Flash model; override with SS_GEMINI_MODEL to use another.
GEMINI_MODEL = os.getenv("SS_GEMINI_MODEL", "gemini-3.8-flash")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# Likewise llama-3.1-70b-versatile was decommissioned by Groq, and
# llama-3.3-70b-versatile is no longer served to new keys. gpt-oss-120b is a
# Groq production model and the one the QA evaluation passed with.
GROQ_MODEL = os.getenv("SS_GROQ_MODEL", "openai/gpt-oss-120b")

LLM_TEMPERATURE = float(os.getenv("SS_LLM_TEMPERATURE", 0.1))
LLM_MAX_OUTPUT_TOKENS = int(os.getenv("SS_LLM_MAX_OUTPUT_TOKENS", 2048))
LLM_MAX_RETRIES = int(os.getenv("SS_LLM_MAX_RETRIES", 3))
# A request that hangs must fail, so the retry and the fallback provider get a turn.
LLM_REQUEST_TIMEOUT = float(os.getenv("SS_LLM_REQUEST_TIMEOUT", 60))
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
CORS_ORIGINS = os.getenv("SS_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
# The Supabase free plan refuses files over 50 MB.
MAX_UPLOAD_MB = int(os.getenv("SS_MAX_UPLOAD_MB", 50))

# Per-user hourly limits, because all users share one free LLM quota.
ASKS_PER_HOUR = int(os.getenv("SS_ASKS_PER_HOUR", 20))
SUMMARIES_PER_HOUR = int(os.getenv("SS_SUMMARIES_PER_HOUR", 5))
UPLOADS_PER_HOUR = int(os.getenv("SS_UPLOADS_PER_HOUR", 5))
# A live evaluation run uses up a whole day's quota, so the API only serves stored
# reports unless this is switched on.
ALLOW_LIVE_EVALUATION = os.getenv("SS_ALLOW_LIVE_EVALUATION", "false").lower() == "true"
