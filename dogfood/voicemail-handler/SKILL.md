---
name: voicemail-handler
description: Handle voice message transcriptions. Save long ones to ~/voicemails/, respond normally to short ones.
triggers:
  - voice message
  - voice transcription
  - "Here's what they said"
---

# Voicemail Handler

When you receive a message containing a voice transcription (injected as `[The user sent a voice message~ Here's what they said: "..." ]`), follow these rules:

## Decision: Save or Reply

### Short voice messages (under ~100 words of transcript)
- Respond normally to whatever was said
- Do NOT save to file
- No mention of saving or transcription

### Long voice messages (~100+ words of transcript)
1. Save the transcript to a markdown file in `~/voicemails/`
2. Filename format: `YYYY-MM-DD_HHMM.md` (use current date/time)
   - Optionally append a short slug: `YYYY-MM-DD_HHMM-project-update.md`
3. File content should be a clean markdown doc:
   ```markdown
   # Voice Message — YYYY-MM-DD HH:MM

   [transcript text here, cleaned up]
   ```
4. Reply to the user with:
   - A brief summary of what the voice message was about (2-3 sentences max)
   - Confirmation: "Saved to voicemails/YYYY-MM-DD_HHMM.md"
   - Ask for clarification if anything in the transcription is unclear or ambiguous
5. Do NOT quote the full transcript back at the user

## Edge Cases

- If `~/voicemails/` doesn't exist, create it
- If transcription looks garbled/nonsense, mention it and ask the user to repeat
- If the user explicitly says "don't save my voice messages", acknowledge and skip saving for that session
