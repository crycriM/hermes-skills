# Qwen3.8-27B no-think suppression caveat

A reasoning model like Qwen3.8-27B emits a ` thinking\n...\n response\n...` block even with
`reasoning = off` + `chat-template-kwargs={"enable_thinking":false}`, tested with BOTH the model's
native embedded template and `chat_template_sharp.jinja`. DFlash2/MTP spec decode stays active
(draft_n/draft_n_accepted > 0) but the model still shortcuts through a brief reasoning block before
answering. This is model behavior, not a config bug — a non-reasoning or smaller model is the only
true think-free path.

`chat_template_sharp.jinja` specifically cannot produce a clean no-think prompt: its
generation-prompt block (lines ~367-373) emits the ` thinking` token in BOTH branches (thinking on →
` thinking\n`; thinking off → ` thinking\n\n response\n\n`). Every completion opens with ` thinking`.
For a genuine dual-entry fast path alongside a sharp-template thinking entry, give the nothink entry
its own template (drop `chat-template-file` so it uses the model's native embedded template).
