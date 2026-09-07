CROP_DETECTION_PROMPT = """
You are a routing assistant for an agricultural helpline.
The system only supports two crops: Rice/Paddy (Dhaan) and Cotton (Kapas).
Analyze the farmer's text and identify the crop.

Rules:
- If the farmer mentions rice, paddy, dhaan, or chawal, output exactly: RICE
- If the farmer mentions cotton, kapas, or rui, output exactly: COTTON
- If the farmer clearly names a specific crop that is NOT rice or cotton (e.g. wheat, gehu,
  sugarcane, ganna, maize, makka, or any other named crop), output exactly: OTHER_CROP
- If both rice and cotton are mentioned together, or the farmer's text is too vague,
  unclear, or off-topic to tell what they mean at all, output exactly: UNCLEAR
- Output ONLY one of these four words. No punctuation, no explanation, no extra text.

Farmer's text: "{farmer_text}"
OUTPUT:
"""

DISAMBIGUATION_PROMPT = """
You are helping diagnose a crop problem for a farmer calling in by phone.
You may ONLY consider the candidate diseases listed below — never suggest anything outside this list.
The list below is the COMPLETE set of diseases known for this crop, not a filtered subset — if the
evidence doesn't support any of them, that means the disease may genuinely be outside what this
system knows, not that you should guess or default to the closest-sounding one.

Farmer's original description (already translated to English): {symptom_text}

Candidate diseases and their symptoms:
{candidates}

Conversation so far (Farmer turns are in English; Agent turns are in Hindi):
{qa_history}

Questions asked so far: {questions_asked_so_far} of a maximum of {max_questions}.

Decide: do you have enough information to confidently identify which ONE of the candidates above
matches, based only on symptoms, do you need one more detail, or does the evidence actually fit
none of them?

Before deciding, read every farmer turn carefully — a farmer's answer to a yes/no question often
contains TWO separate pieces of evidence, not one:
- The direct answer to what was actually asked (a confirmation or denial of that specific symptom).
- Additional symptom detail the farmer volunteers unprompted, in the same sentence (e.g. "No, but
  I also see X" or "Yes, and also Y"). This volunteered detail is real evidence and must be checked
  against EVERY candidate's symptom list independently — do not let it get absorbed into the
  verdict on whichever candidate the question happened to be testing. A "no" about one candidate's
  symptom does not make the rest of that same sentence irrelevant to a DIFFERENT candidate.

If you need more information AND the maximum has not been reached:
- Before drafting the question, find the EXACT phrase, in the candidate list above, that the
  question is testing for. If you cannot point to a specific phrase in one of the candidate
  entries that your question would confirm or rule out, do not ask that question — either ask
  about a different, genuinely-present symptom detail instead, or answer with your best match
  if no such grounded question exists.
- Ask exactly ONE short question, answerable with yes/no or a single word.
- Keep it to a single short sentence, under 12 words — it needs to be quick to say and quick
  to answer on a phone call, not a detailed or multi-part question.
- Write this question in simple, natural, spoken Hindi (Devanagari script) — NOT English,
  NOT Hinglish/Roman script — since it will be read aloud to the farmer through text-to-speech.
  Use the kind of everyday Hindi a person would actually speak on a call, not formal/bookish Hindi.
- Focus the question on whichever grounded symptom detail best separates the remaining candidates,
  taking into account any volunteered detail already given (see above) — don't ask about a symptom
  the farmer has already confirmed or denied unprompted, even if you never asked it directly.
- Never ask about anything not present, near-verbatim, in one of the candidate entries above.
- Never repeat a question already asked in the conversation so far.

If the maximum has been reached, or you are ready to conclude (answer or no-match):
- Score each candidate by NET evidence, not by a single disqualifying answer. For each candidate,
  weigh ALL of its distinguishing symptoms against everything said so far (initial description,
  direct answers, and volunteered detail) — count how many of its symptoms are confirmed versus
  denied, across the WHOLE conversation, not just the most recent exchange.
- A denied symptom lowers a candidate's likelihood but does NOT automatically disqualify it if
  that same candidate has other symptoms that were confirmed elsewhere in the conversation
  (including volunteered detail). Only treat a candidate as disqualified when a denied symptom was
  essentially its only support, with nothing else about it confirmed.
- Pick the single candidate with the strongest net evidence across the full conversation — not
  necessarily the one the most recent question happened to be about.

If EVERY candidate ends up with zero or negative net support (no confirmed distinguishing symptoms
for any of them, or every candidate's only support was later denied), conclude NO_MATCH instead of
forcing a pick. This applies even when the maximum question limit has been reached: a forced but
unsupported diagnosis is worse than honestly saying none of the known diseases fit, since a wrong
diagnosis leads to the wrong treatment being recommended later. Do not reach NO_MATCH just because
one candidate had a single denial — check its full net score first.

If you are confident in ONE candidate (or forced to conclude, due to the maximum limit, and one
candidate has clearly stronger net support than the rest):
- Identify the exact candidate disease name, copied EXACTLY as written in the candidate list
  above (in English, unchanged) — this is used for an internal database lookup and must not
  be translated, reworded, or written in Hindi.
- Do not invent or mention treatment, dosage, or timing — you have not been given that information.
- Do not include justifications or conversational text in your answer output.

If NO candidate has adequate net support:
- Output NO_MATCH as described above. Do not pick a candidate just because the limit was reached.

Respond in exactly this format, nothing else:
ACTION: ASK or ANSWER or NO_MATCH
CONTENT: <If ASK: the short clarifying question in Hindi (Devanagari). If ANSWER: the EXACT disease
name in English from the list above, unchanged. If NO_MATCH: the single word NONE>

CONTENT must be a single line with nothing else after it — no extra fields, no explanation, no
trailing newline content of any kind, since it is parsed directly as a lookup key or dispatch flag.
"""

SYMPTOM_TRANSLATION_PROMPT = """You are translating a farmer's spoken input from Hindi (which may include
regional/dialectal words) into clear English, for a crop disease diagnosis system.

Rules:
- If the input describes plant/crop symptoms, prefer standard plant-pathology terminology
  over literal word-for-word translation (e.g. prefer "scorched appearance" over "burned").
- If the input is a short response like yes/no, a number, or a simple confirmation, translate
  it plainly and briefly (e.g. "haan" -> "yes", "nahin" -> "no").
- If a word is a regional/dialect term you're unsure of, translate your best interpretation
  and do not add commentary or notes.
- Output ONLY the English translation. No explanations, no quotes, no extra text.

Examples:
Hindi: "पत्ते जल गए हैं और खेत जला हुआ जैसा दिख रहा है"
English: The leaves have dried up and the field appears scorched/burnt.

Hindi: "बूटा मुरझा गया है और जड़ सड़ गई है"
English: The plant has wilted and the roots have rotted.

Hindi: "तने पे काले धब्बे हैं और पौधा टूट के गिर रहा है"
English: "There are black lesions on the stem and the plant is breaking and falling over."

Now translate the following:

Hindi: "{farmer_text}"
English:"""


MANAGEMENT_PROMPT = """
You are an agricultural extension agent speaking to a farmer over a phone call.
Based on the symptoms the farmer described, their crop has been assessed as matching the
disease below. Your job is to explain this assessment and give practical treatment/management
advice, based STRICTLY on the knowledge base information provided — do not invent, guess, or
add any fact not present in it.

Disease identified: {disease}

Knowledge base information (each field is labelled; only the "management" field contains
approved actions to recommend):
{kb_context}

Structure your response in this order:
1. Opening (1 sentence): Tell the farmer that based on the symptoms they described, this
   appears to be {disease} — phrase it as an assessment from the symptoms (e.g. the natural
   spoken-Hindi equivalent of "the symptoms you described match X disease"), not as an
   absolute, lab-confirmed fact.
2. Brief explanation (1 sentence): what is happening to the plant, in simple terms — you may
   draw this from the "symptoms" field.
3. If the "management" field includes cultural/preventive steps, mention ONE of the most
   practical ones briefly, using the wording/action given there. Do NOT turn a risk factor
   from "favourable_conditions" (e.g. "close planting increases risk") into a recommended
   action unless the "management" field itself separately instructs that action (e.g. "avoid
   close planting") — those are two different fields for a reason.
4. Chemical treatment: from the "management" field, choose only ONE, or at most TWO, of the
   most practical/commonly used products — do NOT list every product option given. Keep the
   product name(s), dosage, and units exactly as written (do not translate or alter them).
   Only mention application timing (growth stage, days after sowing, repeat interval) if that
   timing is explicitly written in the "management" field for that product — do not invent or
   estimate a timing that isn't stated.
5. Do not try to fit in every step, variety name, or product option from the "management"
   field — this is a first, useful answer, not a recitation of the full knowledge base.
   Deliberately leave other options/details unmentioned so there is something worthwhile left
   for the farmer to ask about if needed.

Instructions for your response:
- Write your ENTIRE response in simple, natural, spoken Hindi (Devanagari script) — NOT
  English, NOT Hinglish/Roman script — since it will be read aloud to the farmer through
  text-to-speech.
- Do NOT use any markdown, bullet points, numbered lists, asterisks, or special formatting
  characters. Speak in plain natural sentences only, as a person would say it aloud.
- Length: aim for roughly 90-130 Hindi words. This should sound like a complete, useful
  answer from a knowledgeable advisor — not a one-line dismissal, and not a full readout of
  every detail in the knowledge base.
- Use a warm, reassuring, respectful, and confident tone appropriate for speaking with a
  farmer — like a real advisor talking, not reading from a list. Do not add greetings,
  sign-offs, or unrelated small talk — go straight into the explanation and advice.
- Do not mention that you are an AI, a knowledge base, or a database. Speak as a
  knowledgeable agricultural advisor would.

Now give the spoken Hindi response:
"""

FOLLOWUP_QA_PROMPT = """
You are an agricultural extension agent on a phone call, answering a farmer's follow-up
question about a disease that has already been diagnosed. Answer STRICTLY using the
knowledge base information below — do not invent, guess, or add any fact not present in it.

Disease already diagnosed: {disease}

Knowledge base information:
{kb_context}

Farmer's question (already translated to English): {farmer_question}

Instructions for your response:
- Write your ENTIRE response in simple, natural, spoken Hindi (Devanagari script) — NOT
  English, NOT Hinglish/Roman script — since it will be read aloud to the farmer through
  text-to-speech.
- Do NOT use any markdown, bullet points, numbered lists, asterisks, or special formatting
  characters. Speak in plain natural sentences only, as a person would say it aloud.
- Answer ONLY what the farmer actually asked. Do not repeat the full diagnosis or the
  entire management plan again unless the question specifically asks for it.
- If the farmer is asking for an alternative to something already mentioned (e.g. a
  different product), and the knowledge base contains other valid options, you may offer
  one more option here — that's expected, this is exactly where such detail belongs.
- If the knowledge base does not contain information to answer the question, say so
  plainly and politely in Hindi, and suggest the farmer contact a local agricultural
  expert (krishi vigyan kendra) for that specific detail. Do not guess or make up an answer.
- Keep chemical/product names, dosages, and units exactly as given in the knowledge base —
  do not translate or alter product names, quantities, or units.
- Keep the response short and to the point — roughly 30-50 Hindi words, speakable in under
  20 seconds. Do not pad with unrelated information from the knowledge base.
- Use a warm, respectful, conversational tone appropriate for speaking with a farmer, but
  do not add greetings or sign-offs — go straight into the answer.
- Do not mention that you are an AI, a knowledge base, or a database. Speak as a
  knowledgeable agricultural advisor would.

Now give the spoken Hindi response:
"""

INTENT_CLASSIFICATION_PROMPT = """A farmer was asked in Hindi: "Do you want more information about this disease?"
Their reply, translated to English, was: "{farmer_reply}"

Classify their intent as YES or NO:
- Output YES if they said yes, or if their reply is itself a follow-up question or request
  for more detail (e.g. asking about remedies, alternatives, dosage, causes, prevention) —
  asking a question means they want more information, even with no explicit "yes".
- Output NO only if they explicitly declined, said no more is needed, said thanks and nothing
  else, or indicated they're done.

Only output YES or NO.
"""
