# Qwen Chat Template: System Message Position Validation

## Symptom

Any API request to a model with this baked-in restriction returns a 400 error:

```json
{
  "error": {
    "code": 400,
    "message": "Unable to generate parser for this template. Automatic parser generation failed: 
    ------------
    While executing CallExpression at line 80, column 32 in source:
    ...first %}↵            {{- raise_exception('System message must be at the beginnin...
                                           ^
    Error: Jinja Exception: System message must be at the beginning."
  }
}
```

The error fires at generation time — the model loads fine, the template parses, but *applying* it to a specific messages array triggers the exception.

## Root cause

The GGUF's baked-in `tokenizer.chat_template` has this structure in its message loop:

```jinja
{%- for message in messages %}
    {%- if message.role == "system" %}
        {%- if not loop.first %}
            {{- raise_exception('System message must be at the beginning.') }}
        {%- endif %}
    ...
```

Any system message at any position other than messages[0] triggers a Jinja exception. This is intentional on the model creator's side — it enforces a strict conversation ordering assumption.

## Why it breaks clients

**Thin ACP clients (Kilo Code, Claude Code, Copilot)** send structured OpenAI-format messages to the router, but their internal conversation construction may place the system prompt after a user message. This is common when:

- The system prompt is injected mid-conversation by the ACP tool-use protocol
- A conversation has tool results that get interleaved with system instructions
- The client constructs messages in a different order than the template expects

The 27B variant of the same model family often lacks this validation — suggesting it's a per-quantizer choice, not a Qwen architecture requirement.

## How to fix

### 1. Extract the baked-in template

`gguf-dump` truncates long string values. Use raw file offset search:

```python
with open('/path/to/model.gguf', 'rb') as f:
    data = f.read()

# Find the raise_exception marker
idx = data.find(b"raise_exception('System message must be at the beginning.')")
# Find the template start — search backward for '{%-' which starts the Jinja template
template_start = data.rfind(b'{%-', 0, idx)
# Find the template end — search forward for the closing quote pattern
template_end = data.find(b"'\n", idx)
if template_end < 0:
    template_end = data.find(b"'\r", idx)

template = data[template_start:template_end].decode('utf-8')
```

### 2. Remove the raise_exception block

Replace the block:

```jinja
    {%- if message.role == "system" %}
        {%- if not loop.first %}
            {{- raise_exception('System message must be at the beginning.') }}
        {%- endif %}
    {%- elif message.role == "user" %}
```

With normal rendering:

```jinja
    {%- if message.role == "system" %}
        {{- '<|im_start|>' + message.role + '\n' + content + '<|im_end|>' + '\n' }}
    {%- elif message.role == "user" %}
```

### 3. Save as a custom template file

```bash
# Write to ~/llm-server/<model-name>-compat-template.jinja
```

### 4. Point the router preset at it

```ini
[qwen36-35b]
jinja = true
chat-template-file = /home/cricri/llm-server/qwen36-35b-compat-template.jinja
```

### 5. Restart both services

```bash
systemctl --user restart m5-router
systemctl --user restart model-manager
```

## Verification

Test the fix with a system-after-user message pattern (the Kilo scenario):

```bash
# Should succeed, not return 400
curl -s http://localhost:8079/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"MODEL_ID","messages":[{"role":"user","content":"Hello"},{"role":"system","content":"You are a helpful assistant."}],"max_tokens":10}'
```

## Detection: which variants have it

Check the GGUF metadata for the `raise_exception` string without loading the model:

```bash
gguf-dump /path/to/model.gguf 2>&1 | grep -o "raise_exception" | head -1
```

If it outputs "raise_exception", the model has aggressive template validation. If no match, it doesn't.
