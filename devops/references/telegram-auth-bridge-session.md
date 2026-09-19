# Telegram Group Auth Bridge Diagnostic Session (2026-06-13)

## Scenario
Bot responds in DMs but silent in a forum group (Chat ID -1003835592883, "Christian et PinceMi"). Privacy mode disabled, bot promoted to admin — still no response. User's messages appeared "unread" in Telegram UI.

## Root Cause
`group_allowed_chats` was only configured under `gateway.platforms.telegram.extra` in config.yaml, NOT at the top-level `telegram:` key. The auth bridge in `gateway/config.py` line 1065 reads `yaml_cfg.get("telegram")` (top-level) and converts it to the `TELEGRAM_GROUP_ALLOWED_CHATS` env var. The auth gate in `authz_mixin.py` line 122 checks this env var. Since the top-level lacked the key, the env var was never set, and the auth gate rejected all group messages.

## Key Evidence

### 1. Zero inbound group messages despite active gateway
```
$ grep "inbound message.*chat=-100" ~/.hermes/logs/gateway.log
# (empty — zero hits)
```
All inbound messages were from DM chat 1867239837. The group chat ID (-1003835592883) never appeared.

### 2. "Unauthorized user" appeared only for the NEW group
When a new non-forum group "PinceMi & PinceMoi" (-1004409226775) was created:
```
WARNING gateway.run: Unauthorized user: -1004409226775 (PinceMoi) on telegram
```
This confirmed the auth gate was working — it KEPT messages from the new group, proving the message pipeline was functional, just gated by auth.

### 3. Env var absent in running process
```
$ cat /proc/<PID>/environ | tr '\0' '\n' | grep TELEGRAM_GROUP
# (empty)
```
`TELEGRAM_GROUP_ALLOWED_CHATS` was never set, despite being in `gateway.platforms.telegram.extra`.

### 4. Config bridge key path
`gateway/config.py` line 1065: `telegram_cfg = yaml_cfg.get("telegram", {})` — reads TOP-LEVEL, not nested.
Line 1134: `group_allowed_chats = telegram_cfg.get("group_allowed_chats")` — reads from the top-level dict.
Line 1138: `os.environ["TELEGRAM_GROUP_ALLOWED_CHATS"] = str(group_allowed_chats)` — sets the env var.

### 5. Bot permissions verified OK
```json
{
  "can_read_all_group_messages": true,
  "status": "administrator",
  "can_manage_topics": true
}
```
Privacy disabled, admin confirmed, topic management granted. The bot COULD read if auth allowed it.

### 6. Forum group confirmed
```json
{
  "is_forum": true,
  "type": "supergroup"
}
```
Group has Topics enabled. This was initially suspected as the cause but wasn't — the auth gate issue affected the new non-forum group identically.

## Diagnostic Commands Used

```bash
# Check process environment for auth env var
cat /proc/$(systemctl --user show hermes-gateway -p MainPID --value)/environ | tr '\0' '\n' | grep TELEGRAM

# Parse running config
cd ~/.hermes/hermes-agent && . venv/bin/activate && python3 -c "
import yaml, json
with open('/home/cricri/.hermes/config.yaml') as f:
    cfg = yaml.safe_load(f)
tl = cfg.get('telegram', {})
gw = cfg.get('gateway', {}).get('platforms', {}).get('telegram', {})
print('Top-level telegram:', json.dumps(tl, indent=2))
print('Gateway platforms telegram:', json.dumps(gw, indent=2))
"

# Verify Telegram bot state directly
source ~/.hermes/.env
BOT="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}"
curl -s "$BOT/getMe" | python3 -m json.tool
curl -s "$BOT/getChat?chat_id=-1003835592883" | python3 -m json.tool
curl -s "$BOT/getChatMember?chat_id=-1003835592883&user_id=8373809487" | python3 -m json.tool
```

## Resolution
Add `group_allowed_chats` to the **top-level** `telegram:` section in config.yaml:
```yaml
telegram:
  reactions: false
  channel_prompts: {}
  allowed_chats: ''
  require_mention: true
  group_allowed_chats:
    - "-1003835592883"
    - "-1004409226775"
```
Then restart gateway. The auth bridge now picks up the key → sets env var → auth gate passes → response gate handles mention/reply logic.
