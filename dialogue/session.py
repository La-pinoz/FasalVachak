import re

from llm.prompts import CROP_DETECTION_PROMPT, DISAMBIGUATION_PROMPT, MANAGEMENT_PROMPT, FOLLOWUP_QA_PROMPT
from llm.client import get_fast_llm_completion, get_reasoning_completion
from llm.translation import translate_to_english
from rag.retriever import get_candidates, get_disease_record

MAX_DISAMBIGUATION_QUESTIONS = 2
MAX_FOLLOWUPS = 2

GENERIC_ERROR_REPLY = "Maaf kijiyega, thodi dikkat aa gayi. Kripya dobara boliye."


class DialogueManager:
    def __init__(self):
        self.phase = "crop_detection"
        self.crop = None
        self.symptoms_text = ""
        # NEW: accumulates farmer text while crop is still unknown
        self.pending_symptom_turns = []
        self.candidates_text = ""
        self.candidate_names = []
        self.qa_history = []
        self.questions_asked = 0
        self.identified_disease = None
        self.followups_asked = 0

        # (hindi_input, english_translation) pairs, for later glossary-building / debugging
        self.translation_log = []

    async def process_turn(self, farmer_text_hindi: str) -> str:
        # No point translating once the call is over.
        if self.phase == "completed":
            return "Yeh call samapt ho chuki hai. Naye sawaal ke liye kripya naya call karein."

        try:
            translated_text = await translate_to_english(farmer_text_hindi)
            self.translation_log.append((farmer_text_hindi, translated_text))
        except Exception as e:
            print(f"[DialogueManager] Translation failed: {e}")
            return GENERIC_ERROR_REPLY

        try:
            if self.phase == "crop_detection":
                return await self._handle_crop_detection(translated_text)
            elif self.phase == "symptom_diagnosis":
                return await self._handle_disambiguation(translated_text)
            elif self.phase == "followup":
                return await self._handle_followup(translated_text)
            else:
                return GENERIC_ERROR_REPLY
        except Exception as e:
            print(
                f"[DialogueManager] Unhandled error in phase={self.phase}: {e}")
            return GENERIC_ERROR_REPLY

    async def _handle_crop_detection(self, text_en: str) -> str:
        """Phase 0: Figure out the crop from what the farmer says (may take multiple turns)."""

        # Always bank this turn's text — it might contain symptom info even if
        # it doesn't (yet) reveal the crop.
        self.pending_symptom_turns.append(text_en)

        prompt = CROP_DETECTION_PROMPT.format(farmer_text=text_en)
        llm_decision = await get_fast_llm_completion(prompt, temperature=0.0)
        decision = llm_decision.strip().upper()

        if "RICE" in decision:
            self.crop = "rice"
        elif "COTTON" in decision:
            self.crop = "cotton"

        if not self.crop:
            return "Maaf kijiyega, main theek se samajh nahi paaya. Yeh dhaan ki samasya hai ya kapas ki?"

        # Crop is now known — combine EVERYTHING said so far (across however many
        # turns it took) into the symptom text used for retrieval, not just this
        # last confirmation message.
        self.symptoms_text = " ".join(self.pending_symptom_turns)
        self.phase = "symptom_diagnosis"

        self.candidates_text = get_candidates(self.crop, self.symptoms_text)
        self.candidate_names = self._parse_candidate_names(
            self.candidates_text)

        return await self._trigger_llm_turn()

    async def _handle_disambiguation(self, text_en: str) -> str:
        """Phase 1: Handles the farmer's answers to our clarifying questions (in English)."""
        self.qa_history.append(f"Farmer: {text_en}")
        self.questions_asked += 1
        return await self._trigger_llm_turn()

    async def _trigger_llm_turn(self) -> str:
        """The Reasoning Engine for Phase 1. Decides whether to ASK or ANSWER."""

        if self.questions_asked >= MAX_DISAMBIGUATION_QUESTIONS:
            forced_disease = self.candidate_names[0] if self.candidate_names else None
            if forced_disease:
                self.identified_disease = forced_disease
                return await self._generate_management_plan()
            return "Maaf kijiyega, lakshan ke aadhar par main sahi bimari nahi pehchaan paa raha hoon. Kripya krishi visheshagya se sampark karein."

        formatted_history = "\n".join(self.qa_history)
        prompt = DISAMBIGUATION_PROMPT.format(
            symptom_text=self.symptoms_text,
            candidates=self.candidates_text,
            qa_history=formatted_history,
            questions_asked_so_far=self.questions_asked,
            max_questions=MAX_DISAMBIGUATION_QUESTIONS
        )

        # Note: the ASK content the LLM produces here must be in Hindi (it's spoken to the
        # farmer directly) — make sure DISAMBIGUATION_PROMPT instructs this explicitly.
        llm_output = await get_reasoning_completion(prompt)
        action, content = self._parse_action_content(llm_output)

        if action is None:
            print(
                f"[DialogueManager] Could not parse reasoning output: {llm_output!r}")
            return "Maaf kijiye, main theek se samajh nahi paaya. Kya aap lakshan dobara bata sakte hain?"

        if action == "ASK":
            # Stored as-is (Hindi) in qa_history; DISAMBIGUATION_PROMPT reasons fine over
            # a mixed-language history since the farmer side is consistently English.
            self.qa_history.append(f"Agent: {content}")
            return content

        elif action == "ANSWER":
            self.identified_disease = content
            return await self._generate_management_plan()

        else:
            print(
                f"[DialogueManager] Unknown action '{action}' in output: {llm_output!r}")
            return "Maaf kijiye, main theek se samajh nahi paaya. Kya aap lakshan dobara bata sakte hain?"

    async def _generate_management_plan(self) -> str:
        """Phase 2: Fetch DB record, generate spoken treatment (in Hindi), transition to Phase 3."""

        kb_record = get_disease_record(self.identified_disease)

        if not kb_record:
            self.phase = "completed"
            return (
                f"Lagta hai yeh {self.identified_disease} hai, par mere paas iski poori dawai ki "
                f"jankari abhi nahi hai. Kripya kisi krishi visheshagya se sampark karein."
            )

        self.identified_disease = kb_record.get(
            "disease_name", self.identified_disease)

        prompt = MANAGEMENT_PROMPT.format(
            disease=self.identified_disease,
            kb_context=self._format_kb_record(kb_record)
        )

        treatment_audio_text = await get_fast_llm_completion(prompt, temperature=0.1)

        self.phase = "followup"
        closing_question = f"Kya apko {self.identified_disease} ke baare mein aur jaankari chahiye?"

        return f"{treatment_audio_text}\n\n{closing_question}"

    async def _handle_followup(self, text_en: str) -> str:
        """Phase 3: The Follow-Up Loop (farmer input already translated to English)."""

        intent_prompt = (
            f"Classify the user's intent as either YES or NO based on this text: "
            f"'{text_en}'. Only output YES or NO."
        )
        intent_response = await get_fast_llm_completion(intent_prompt, temperature=0.0)
        intent = intent_response.strip().upper()

        if "NO" in intent:
            self.phase = "completed"
            return "Theek hai. KrishiSeva mein call karne ke liye dhanyawad. Namaste!"

        self.followups_asked += 1
        if self.followups_asked > MAX_FOLLOWUPS:
            self.phase = "completed"
            return "Maaf kijiyega, is call ka samay samapt ho gaya hai. Aur jaankari ke liye kripya naya call karein. Dhanyawad!"

        kb_record = get_disease_record(self.identified_disease)
        qa_prompt = FOLLOWUP_QA_PROMPT.format(
            disease=self.identified_disease,
            kb_context=self._format_kb_record(kb_record),
            farmer_question=text_en
        )

        answer_text = await get_fast_llm_completion(qa_prompt, temperature=0.1)
        return f"{answer_text}\n\nKya apko iske baare mein aur kuch janna hai?"

    # ---------- helpers ----------

    @staticmethod
    def _parse_action_content(llm_output: str):
        match = re.search(
            r"ACTION:\s*(\w+)\s*\n+CONTENT:\s*(.*)",
            llm_output.strip(),
            re.IGNORECASE | re.DOTALL
        )
        if not match:
            return None, None
        action = match.group(1).strip().upper()
        content = match.group(2).strip()
        return action, content

    @staticmethod
    def _parse_candidate_names(candidates_text: str):
        names = []
        for line in candidates_text.splitlines():
            m = re.match(r"\s*\d+\.\s*([^:]+):", line)
            if m:
                names.append(m.group(1).strip())
        return names

    @staticmethod
    def _format_kb_record(kb_record: dict) -> str:
        if not kb_record:
            return "No knowledge base record available."

        bullets = kb_record.get("symptoms_bullets", [])
        symptoms = " ".join(bullets) if bullets else "Not available."

        lines = [
            f"Disease: {kb_record.get('disease_name', 'Unknown')}",
            f"Causal organism: {kb_record.get('causal_organism', 'Not available.')}",
            f"Symptoms: {symptoms}",
            f"Favourable conditions: {kb_record.get('favourable_conditions') or 'Not available.'}",
            f"Survival and spread: {kb_record.get('survival_and_spread') or 'Not available.'}",
            f"Management: {kb_record.get('management') or 'Not available.'}",
        ]
        return "\n".join(lines)
