Using your own reasoning below, return STRICT JSON only: a list of objects,
one per field in {fields}, each shaped exactly as
{"field": "<name>", "value": "<verbatim value or null>", "quote": "<the exact
verbatim substring of the protocol text that supports value, or empty string
if value is null>"}.

Rules:
- "quote" MUST be an exact, character-for-character substring of the protocol
  text (copy-paste, not a paraphrase) — it will be verified by exact match.
- For "inclusionCriteria"/"exclusionCriteria", "value" and "quote" may be the
  full verbatim block of criteria text (not paraphrased or restructured).
- If a field is not present, set "value" to null and "quote" to "".
- Return every field in {fields} exactly once. No prose outside the JSON.

YOUR REASONING:
{reasoning}

PROTOCOL TEXT:
{document_text}
