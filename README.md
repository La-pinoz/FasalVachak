# KrishiSeva - Agricultural Voice Assistant

KrishiSeva is an AI-powered voice assistant designed to help farmers diagnose crop diseases and get management advice over a telephone call. The system currently focuses on **Rice (Dhaan)** and **Cotton (Kapas)** crops. It operates entirely in spoken Hindi.

## Architecture & Codebase Structure

The application is built using Python, LiveKit for real-time WebRTC audio, Deepgram for Speech-to-Text (STT), a custom TTS solution (Rime), and Groq for ultra-low latency LLM inference.

### Directory Structure

```text
.
├── server.py               # Main entry point (LiveKit WebRTC agent)
├── dialogue/
│   └── session.py          # Core dialogue state machine & logic
├── llm/
│   ├── client.py           # Groq API client integration
│   ├── prompts.py          # LLM prompt templates
│   └── translation.py      # Translation utilities
├── kb/
│   ├── database.py         # Knowledge base loader
│   ├── rice.json           # Rice disease database
│   ├── cotton.json         # Cotton disease database
├── rag/
│   ├── ingest.py           # ChromaDB ingestion script (legacy/optional)
│   └── retriever.py        # Knowledge base retrieval functions
├── requirements.txt        # Python dependencies
└── ...
```

### Component Breakdown

#### 1. `server.py`
The main entry point of the application. It bootstraps a LiveKit agent that connects to a Twilio/LiveKit room.
- Plays an initial Hindi greeting.
- Subscribes to the farmer's audio track and streams it to **Deepgram STT**.
- Once the STT returns a final transcript, it passes the text to the `DialogueManager`.
- The response from the `DialogueManager` is converted to speech via **Rime TTS** and played back to the farmer.

#### 2. `dialogue/session.py` (`DialogueManager`)
The heart of the application. It maintains the conversational state machine with the following phases:
- **`crop_detection` (Phase 0)**: Analyzes the initial input to determine if the farmer is talking about Rice, Cotton, or something else.
- **`symptom_diagnosis` (Phase 1)**: The core diagnostic loop. It asks clarifying questions to the farmer to disambiguate between possible diseases. It tracks unresolved questions so it doesn't repeatedly ask the farmer something they don't know.
- **`followup` / `followup_elicit` (Phase 2 & 3)**: After a diagnosis is made, it answers follow-up questions from the farmer (e.g., about treatments, yield loss, spread) strictly using the knowledge base to prevent hallucinations.

#### 3. `llm/` (Language Model Integration)
- **`client.py`**: Initializes the `AsyncGroq` client for ultra-low latency LLM inference. Provides helper functions for fast classifications and complex reasoning.
- **`prompts.py`**: Contains all the system prompts. It enforces strict rules, like only using the provided knowledge base (`FOLLOWUP_QA_PROMPT`), returning structured outputs (`DISAMBIGUATION_PROMPT`), and classifying yes/no intents (`QUESTION_RESOLUTION_PROMPT` & `INTENT_CLASSIFICATION_PROMPT`).

#### 4. `kb/` (Knowledge Base)
- **`database.py`**: Loads `cotton.json` and `rice.json` into a master dictionary in memory (`FULL_KB_DICT`).
- **`*.json` files**: Structured agricultural data containing disease names, causal organisms, symptoms, favourable conditions, and management strategies.

#### 5. `rag/` (Retrieval)
- **`retriever.py`**: Provides the `DialogueManager` with all possible disease candidates for a given crop (`get_all_candidates`) and fetches detailed records for a specific disease (`get_disease_record`). It currently uses a closed-list approach (passing all candidates to the LLM) rather than top-k similarity search to ensure accurate diagnosis.
- **`ingest.py`**: Script to ingest the knowledge base into a ChromaDB vector store.