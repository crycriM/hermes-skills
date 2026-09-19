# Telegram Bot API Diagnostics

Raw diagnostic commands and response patterns. Uses `source ~/.hermes/.env` to load `TELEGRAM_BOT_TOKEN`.

## Bot Identity & Privacy Status

```bash
source ~/.hermes/.env
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe" | python3 -m json.tool
```

**Response shape:**
```json
{
    "ok": true,
    "result": {
        "id": 8373809487,
        "is_bot": true,
        "first_name": "PinceMi",
        "username": "pincemi_bot",
        "can_join_groups": true,
        "can_read_all_group_messages": true,
        "supports_inline_queries": false,
        "has_topics_enabled": false
    }
}
```

**Key fields:**
- `can_read_all_group_messages: true` → Privacy Mode DISABLED in BotFather. Bot can see all group messages.
- `can_read_all_group_messages: false` → Privacy Mode ENABLED. Bot only sees messages starting with `/` or mentioning `@botusername`. Fix: BotFather → `/setprivacy` → Disabled.
- `has_topics_enabled: false` → Bot itself doesn't have topics management feature. Doesn't affect message receiving if `can_read_all_group_messages: true`.

## Group Metadata

```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChat?chat_id=-1003835592883" | python3 -m json.tool
```

**Response shape:**
```json
{
    "ok": true,
    "result": {
        "id": -1003835592883,
        "title": "Christian et PinceMi",
        "is_forum": true,
        "type": "supergroup",
        "has_visible_history": true,
        "permissions": { ... }
    }
}
```

**Key fields:**
- `is_forum: true` → Group has Topics enabled. Messages flow through individual topics.
- `type: "supergroup"` → Normal modern Telegram group.
- `join_to_send_messages: true` → Bot needs to be added to the group by an admin.

## Bot Member Status

```bash
BOT_ID=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['id'])")
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMember?chat_id=-1003835592883&user_id=${BOT_ID}" | python3 -m json.tool
```

**Response shapes:**
- `"status": "member"` → Bot is in the group but not admin. May not receive forum topic messages.
- `"status": "administrator"` → Bot is admin. Will receive ALL messages including from topics.
- `"status": "left"` → Bot was removed from the group. Re-add it.

## Pending Updates

```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates?timeout=5" | python3 -m json.tool
```

**Response shapes:**
```json
{"ok": true, "result": []}  // No pending updates (normal)
```
```json
{"ok": false, "error_code": 409, "description": "Conflict: terminated by other getUpdates request; make sure that only one bot instance is running"}
```
The 409 means another process (the gateway) is actively polling. This is expected when the gateway is running.

## Webhook Status

```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | python3 -m json.tool
```

**Response shapes:**
```json
{"ok": true, "result": {"url": "", ...}}  // Polling mode
```
```json
{"ok": true, "result": {"url": "https://...", ...}}  // Webhook mode
```

If a stale webhook URL is set while using polling mode, the bot may not receive updates. Use `deleteWebhook` to clear it:
```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook" | python3 -m json.tool
```

## Polling Conflict Detection

```bash
journalctl --user -u hermes-gateway --since "5 min ago" --no-pager | grep "polling conflict"
```

Conflicts occur when the gateway restarts and the old polling session is still held open by Telegram's servers. The built-in recovery retries up to 5 times with 20s backoff. Messages sent during the conflict window are lost — Telegram does not replay acknowledged updates.

## Troubleshooting Flow

1. `getMe` → check `can_read_all_group_messages`
2. `getChat` → check `is_forum`, `type`
3. `getChatMember` → check `status` (member vs administrator)
4. `getWebhookInfo` → verify no stale webhook URL
5. gateway log → grep for group chat ID in inbound messages
6. If no inbound messages and config is correct → BotFather privacy or admin status
