import re

from llm.prompts import CROP_DETECTION_PROMPT, DISAMBIGUATION_PROMPT, MANAGEMENT_PROMPT, FOLLOWUP_QA_PROMPT, INTENT_CLASSIFICATION_PROMPT
from llm.client import get_fast_llm_completion, get_reasoning_completion
from llm.translation import translate_to_english
# CHANGED: get_candidates -> get_all_candidates
from rag.retriever import get_all_candidates, get_disease_record

MAX_DISAMBIGUATION_QUESTIONS = 2
MAX_FOLLOWUPS = 2

GENERIC_ERROR_REPLY = "Maaf kijiyega, thodi dikkat aa gayi. Kripya dobara boliye."
# CHANGED: added, was missing
NO_MATCH_REPLY = "Maaf kijiyega, lakshan ke aadhar par main sahi bimari nahi pehchaan paa raha hoon. Kripya krishi visheshagya se sampark karein."


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

    # CHANGED: re-indented into the class (was at column 0)
    async def _handle_crop_detection(self, text_en: str) -> str:
        """Phase 0: Figure out the crop from what the farmer says (may take multiple turns)."""

        self.pending_symptom_turns.append(text_en)

        prompt = CROP_DETECTION_PROMPT.format(farmer_text=text_en)
        llm_decision = await get_fast_llm_completion(prompt, temperature=0.0)
        decision = llm_decision.strip().upper()

        if "OTHER_CROP" in decision:
            self.phase = "completed"
            return "Maaf kijiyega, humari helpline abhi sirf Dhaan (Rice) aur Kapas (Cotton) ki bimariyon ke baare mein jaankari de sakti hai. Call karne ke liye dhanyawad, namaste."

        elif "RICE" in decision:
            self.crop = "rice"

        elif "COTTON" in decision:
            self.crop = "cotton"

        elif "UNCLEAR" in decision or not self.crop:
            return "Maaf kijiyega, main theek se samajh nahi paaya. Kya aap bata sakte hain ki yeh samasya dhaan (rice) ki hai ya kapas (cotton) ki?"

        self.symptoms_text = " ".join(self.pending_symptom_turns)
        self.phase = "symptom_diagnosis"

        # CHANGED: fetch every disease record for this crop, not a vector top-k.
        candidate_records = get_all_candidates(self.crop)

        if not candidate_records:
            # Defensive: crop detected but somehow no KB entries for it — don't proceed
            # into a disambiguation prompt with an empty candidate list.
            self.phase = "completed"
            print(
                f"[DialogueManager] No candidate records found for crop={self.crop!r}")
            return "Maaf kijiyega, abhi mere paas is fasal ki bimariyon ki jaankari uplabdh nahi hai. Kripya krishi visheshagya se sampark karein."

        self.candidate_names = [r.get("disease_name", "")
                                for r in candidate_records]
        self.candidates_text = self._format_candidates_text(candidate_records)

        return await self._trigger_llm_turn()

    async def _handle_disambiguation(self, text_en: str) -> str:
        """Phase 1: Handles the farmer's answers to our clarifying questions (in English)."""
        self.qa_history.append(f"Farmer: {text_en}")
        # CHANGED: questions_asked increment removed from here — now owned solely by
        # _trigger_llm_turn's ASK branch, to avoid double-counting per round-trip.
        return await self._trigger_llm_turn()

    async def _trigger_llm_turn(self) -> str:
        """The Reasoning Engine for Phase 1. Decides whether to ASK, ANSWER, or NO_MATCH."""

        # CHANGED: no more early-exit hardcoded fallback here — the LLM is always
        # consulted, including on the final turn. DISAMBIGUATION_PROMPT itself
        # handles how to conclude once questions_asked_so_far == max_questions.

        formatted_history = "\n".join(self.qa_history)
        prompt = DISAMBIGUATION_PROMPT.format(
            symptom_text=self.symptoms_text,
            candidates=self.candidates_text,
            qa_history=formatted_history,
            questions_asked_so_far=self.questions_asked,
            max_questions=MAX_DISAMBIGUATION_QUESTIONS
        )

        llm_output = await get_reasoning_completion(prompt)
        action, content = self._parse_action_content(llm_output)

        if action is None:
            print(
                f"[DialogueManager] Could not parse reasoning output: {llm_output!r}")
            return "Maaf kijiye, main theek se samajh nahi paaya. Kya aap lakshan dobara bata sakte hain?"

        # Safety net: the model shouldn't ask past the limit, but if it does, don't
        # let the call loop forever — force a conclusion instead of trusting it blindly.
        if action == "ASK" and self.questions_asked >= MAX_DISAMBIGUATION_QUESTIONS:
            print(
                f"[DialogueManager] Model asked past question limit, overriding. Raw: {llm_output!r}")
            self.phase = "completed"
            return NO_MATCH_REPLY

        if action == "ASK":
            self.qa_history.append(f"Agent: {content}")
            self.questions_asked += 1  # CHANGED: sole place questions_asked is incremented now
            return content

        elif action == "ANSWER":
            # Safety net: only trust the disease name if it's actually one we offered.
            if content not in self.candidate_names:
                print(
                    f"[DialogueManager] ANSWER did not match a candidate name: {content!r}")
                self.phase = "completed"
                return NO_MATCH_REPLY
            self.identified_disease = content
            return await self._generate_management_plan()

        elif action == "NO_MATCH":
            self.phase = "completed"
            return NO_MATCH_REPLY

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
        # CHANGED: was an inline f-string, now uses the imported template
        intent_prompt = INTENT_CLASSIFICATION_PROMPT.format(
            farmer_reply=text_en)
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

    @staticmethod
    def _format_candidates_text(candidate_records: list[dict]) -> str:
        """
        Builds the {candidates} block for DISAMBIGUATION_PROMPT: one numbered line per
        disease, full symptoms_bullets folded in after the colon. Keeps the same
        'N. DiseaseName: ...' shape the rest of the system expects.
        """
        lines = []
        for i, record in enumerate(candidate_records, start=1):
            name = record.get("disease_name", "Unknown")
            bullets = record.get("symptoms_bullets", [])
            symptoms = " ".join(bullets) if bullets else "Not available."
            lines.append(f"{i}. {name}: {symptoms}")
        return "\n".join(lines)

    # CHANGED: get_all_candidates REMOVED from this class entirely — it belongs in
    # rag/retriever.py as a module-level function (see below), not as a method here.
    # It was pasted in with no `self`/`@staticmethod` and referenced RAW_DISEASE_DB,
    # a name that doesn't exist in this file.
