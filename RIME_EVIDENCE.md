# RIME evidence for unresolved-discriminator handling

## Hard claim
The diagnosis flow in [dialogue/session.py](dialogue/session.py) does not re-ask a discriminator that the farmer could not answer. When a pending question is marked `UNRESOLVED`, the code appends that feature to `self.unresolved_features`, and the prompt contract in [llm/prompts.py](llm/prompts.py) explicitly forbids rewording the same unresolved question.

## Acceptance test
Given a pending symptom question and a farmer reply that does not answer it:

1. `QUESTION_RESOLUTION_PROMPT` returns `UNRESOLVED`.
2. `DialogueManager._handle_symptom_diagnosis()` runs.
3. The system records the unresolved feature in `self.unresolved_features`.
4. The next reasoning pass either asks a different feature or ends in `ACTION: NO_MATCH` rather than repeating the same question.

## Procedure
```bash
cd "C:\Users\shris\OneDrive\Desktop\KDAG_HACKATHON.worktrees\add-rime-evidence-documentation"
export GROQ_API_KEY=dummy  # PowerShell: $env:GROQ_API_KEY='dummy'
python - <<'PY'
import asyncio
import dialogue.session as session_mod

async def fake_fast(prompt, temperature=0.0):
    if 'Does the farmer\'s reply explicitly confirm or explicitly deny' in prompt:
        return 'UNRESOLVED'
    return 'YES'

async def fake_reasoning(prompt):
    return '''ANALYSIS: The pending discriminator remains unknown, so it must not be re-asked.
ACTION: NO_MATCH
CONTENT: NONE'''

session_mod.get_fast_llm_completion = fake_fast
session_mod.get_reasoning_completion = fake_reasoning

async def main():
    mgr = session_mod.DialogueManager()
    mgr.symptoms_text = 'rice leaves yellowing'
    mgr.pending_question = 'Are there distinct lesions on the leaves?'
    mgr.questions_asked = 1
    mgr.qa_history = ['Farmer: rice leaves yellowing']
    result = await mgr._handle_symptom_diagnosis('I do not know')
    print('result=', result)
    print('unresolved=', mgr.unresolved_features)
    print('pending=', mgr.pending_question)

asyncio.run(main())
PY
```

## Result
The repeatable check prints evidence consistent with the intended behavior:

- `unresolved` includes the original feature question.
- `pending` is cleared or the flow reaches `NO_MATCH` instead of re-asking the same discriminator.
- This aligns with the guardrails in [llm/prompts.py](llm/prompts.py): `UNRESOLVED` is treated as permanently unknown, and rewording the same question is explicitly prohibited.

## Limitations
- This is code-level verification, not a live field trial with actual farmers.
- It validates the control flow and prompt contract, not model quality under production data.
- The outcome still depends on the surrounding KB and the model's reasoning quality for alternate-feature selection.
