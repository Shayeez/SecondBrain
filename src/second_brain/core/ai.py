import logging
import base64
import httpx
from google import genai
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from second_brain.config import (
    GEMINI_API_KEY,
    LOCAL_LLM_BASE_URL,
    LOCAL_LLM_MODEL,
    LOCAL_LLM_API_KEY,
    USE_LOCAL_LLM
)
from datetime import datetime

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GEMINI_API_KEY)

llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite", 
    google_api_key=GEMINI_API_KEY, 
    temperature=0.3
)

def query_local_llm(prompt: str, system_prompt: str = "", timeout: float = 30.0) -> str:
    """Invokes the local LLM on the VPS via OpenAI-compatible HTTP endpoint."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    url = f"{LOCAL_LLM_BASE_URL}/chat/completions"
    payload = {
        "model": LOCAL_LLM_MODEL,
        "messages": messages,
        "temperature": 0.2,
    }

    with httpx.Client(timeout=timeout) as http_client:
        res = http_client.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LOCAL_LLM_API_KEY}"
            },
            json=payload
        )
        res.raise_for_status()
        data = res.json()
        return data["choices"][0]["message"]["content"].strip()


import re

def slugify(text: str, max_length: int = 40) -> str:
    """Converts a string into a filesystem-safe kebab-case slug."""
    text = text.lower().strip()
    text = re.sub(r'[\r\n\t]+', ' ', text)
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text).strip('-')
    return text[:max_length].rstrip('-') or "note"

def process_thought(text: str = "", media_path: str = None):
    """Uses LLM to summarize, tag, classify into PARA, and describe text, images, audio, or documents (PDFs)."""
    
    instructions = f"""
    Analyze the following input. If it is an image, audio, or document (such as a PDF), extract the text, analyze all key information/tables, summarize the core points, and describe the contents.
    First, determine the INTENT. If the user is explicitly asking a question about their notes/brain (e.g. "what did I say about X", "search for Y", "who is Z"), the intent is QUERY. Otherwise, the intent is SAVE.
    
    If INTENT is SAVE:
    1. Classify the note into ONE of the following PARA Framework categories:
       - Projects: Notes tied to short-term, specific goals or active initiatives with deadlines (e.g., tasks, sprints, event planning, active deliverables).
       - Areas: Long-term domains of responsibility to maintain over time with no end date (e.g., Health, Finances, Work/Career, Family, Routines, Home).
       - Resources: Topics of ongoing interest, reference materials, guides, reading notes, code snippets, bookmarks, general facts.
       - Archive: Inactive items from the other three categories, completed tasks, historical logs, or old reference.
    2. Provide a concise summary (max 5-7 words).
    3. Provide a clean kebab-case slug for filenames (lowercase, 2-5 words, hyphen-separated, e.g. "client-proposal-review", "grocery-checklist", "fastapi-auth-notes").
    4. Provide up to 3 relevant tags.
    5. Provide a detailed transcription/description.
    
    Format your response EXACTLY like this:
    Intent: SAVE
    Category: [Projects | Areas | Resources | Archive]
    Summary: [your summary]
    Slug: [clean-kebab-slug]
    Tags: [tag1, tag2, tag3]
    Description: [Full extracted text and visual/audio description]
    
    If INTENT is QUERY:
    Format your response EXACTLY like this:
    Intent: QUERY
    Query: [The exact question or search term the user is asking, cleanly extracted]
    """
    
    raw_content = ""
    model_used = f"Local VPS Qwen ({LOCAL_LLM_MODEL})"
    # Route 1: Multimodal media attached -> Send to Gemini
    if media_path:
        model_used = "Gemini Cloud (Multimodal)"
        uploaded_file = None
        try:
            uploaded_file = client.files.upload(file=media_path)
            prompt_parts = [instructions, uploaded_file]
            if text:
                prompt_parts.insert(1, f"User's caption/text: {text}")
            response = client.models.generate_content(
                model='gemini-3.5-flash-lite',
                contents=prompt_parts
            )
            raw_content = response.text
        finally:
            if uploaded_file:
                client.files.delete(name=uploaded_file.name)
    else:
        # Route 2: Pure text input -> Route to Local LLM on VPS for 100% token savings
        if USE_LOCAL_LLM:
            try:
                full_prompt = f"{instructions}\n\nUser's text:\n{text}"
                raw_content = query_local_llm(full_prompt, system_prompt="You are an automated note structuring assistant.")
                logger.info(f"Successfully processed thought via Local LLM ({LOCAL_LLM_MODEL})")
                model_used = f"Local VPS Qwen ({LOCAL_LLM_MODEL})"
            except Exception as e:
                logger.warning(f"Local LLM processing failed ({e}). Falling back to Gemini.")
                raw_content = ""

        # Fallback to Gemini if local LLM is disabled or encountered an error
        if not raw_content:
            try:
                model_used = "Gemini Cloud (Fallback)"
                prompt_parts = [instructions]
                if text:
                    prompt_parts.append(f"User's caption/text: {text}")
                response = client.models.generate_content(
                    model='gemini-3.5-flash-lite',
                    contents=prompt_parts
                )
                raw_content = response.text
            except Exception as e:
                logger.error(f"Cloud Gemini processing failed ({e}). Using offline heuristic fallback.")
                model_used = "Offline Heuristic Fallback"
                clean_preview = (text or "").strip().split("\n")[0][:40] or "Note"
                raw_content = f"""Intent: SAVE\nCategory: Resources\nSummary: {clean_preview}\nSlug: {slugify(clean_preview)}\nTags: note, quick\nDescription: {text}"""
        
    lines = raw_content.strip().split("\n")
    
    intent = "SAVE"
    category = "Resources"
    summary = "Note"
    slug = ""
    tags_str = "general"
    description = ""
    query = ""
    
    # Extract fields carefully
    for i, line in enumerate(lines):
        if line.startswith("Intent:"):
            intent = line.replace("Intent:", "").strip().upper()
        elif line.startswith("Category:"):
            cat_val = line.replace("Category:", "").strip().title()
            if cat_val in {"Projects", "Areas", "Resources", "Archive"}:
                category = cat_val
        elif line.startswith("Summary:"):
            summary = line.replace("Summary:", "").strip()
        elif line.startswith("Slug:"):
            slug = line.replace("Slug:", "").strip()
        elif line.startswith("Tags:"):
            tags_str = line.replace("Tags:", "").strip()
        elif line.startswith("Query:"):
            query = "\n".join(lines[i:]).replace("Query:", "").strip()
            break
        elif line.startswith("Description:"):
            description = "\n".join(lines[i:]).replace("Description:", "").strip()
            break
            
    if intent == "QUERY":
        clean_query = query.strip() or text.strip()
        return {"intent": "QUERY", "query": clean_query, "model_used": model_used}

    else:
        tags = [t.strip() for t in tags_str.strip("[]").split(",")]
        slug = slugify(slug or summary)
        final_content = f"{text}\n\nMedia Analysis:\n{description}".strip()
        return {
            "intent": "SAVE",
            "category": category,
            "summary": summary,
            "slug": slug,
            "tags": tags,
            "content": final_content,
            "model_used": model_used
        }

def generate_rag_answer(query: str, context_documents) -> str:
    """Generates an answer using the retrieved context, temporal awareness, and local/cloud routing."""
    
    # Combine the content of the retrieved documents with clear headers
    notes_parts = []
    for doc in context_documents:
        s = doc.metadata.get("summary", "Note")
        c = doc.metadata.get("category", "General")
        notes_parts.append(f"--- Note: {s} (Category: {c}) ---\n{doc.page_content}")
    context_text = "\n\n".join(notes_parts)
    
    # Capture the exact current date and time
    current_date = datetime.now().strftime("%B %d, %Y")
    
    # Clean, direct prompt optimized for both local LLM (Qwen) and Gemini
    prompt = f"""You are my personal Second Brain assistant. Today's date is {current_date}.
Use the Context Notes below to answer the user's question directly, concisely, and factually.

Context Notes:
{context_text}

User Question: {query}

Instructions:
- Answer directly based on the information provided in the Context Notes.
- Include specific deadlines, deliverables, dates, or details mentioned in the notes.
- If none of the notes contain relevant information to answer the question, simply reply: "I couldn't find any relevant notes in your Second Brain for that question."

Answer:"""
    
    raw_content = ""
    # Try Local LLM first if enabled
    if USE_LOCAL_LLM:
        try:
            raw_content = query_local_llm(prompt, system_prompt="You are a personal second brain retrieval assistant.")
            logger.info(f"Generated RAG answer via Local LLM ({LOCAL_LLM_MODEL})")
        except Exception as e:
            logger.warning(f"Local LLM RAG failed ({e}). Falling back to Gemini.")
            raw_content = ""

    # Fallback to Gemini if Local LLM is disabled or failed
    if not raw_content:
        try:
            response = llm.invoke(prompt)
            raw_content = response.content
            if isinstance(raw_content, list):
                raw_content = raw_content[0].get("text", "") if isinstance(raw_content[0], dict) else str(raw_content[0])
        except Exception as e:
            logger.error(f"Cloud Gemini RAG failed ({e}). Returning retrieved notes.")
            raw_content = f"Here is the relevant information retrieved from your Second Brain:\n\n{context_text}"
        
    return raw_content.strip()