# Delivery targets and send verification

Depth for the delivery half of cron work: addressing a target correctly, and
proving a send landed. Read alongside `scripts/probe_cron_delivery.py`, which
resolves a JOB's target the way the tick does; this file is for the manual send.

## `hermes send` target grammar

```
platform                      home channel for that platform
platform:chat_id              a specific chat
platform:chat_id:thread_id    a topic/thread inside that chat
platform:#channel-name        name-addressed (Slack/Discord)
```

- `hermes send --to <platform> --list` prints what the gateway knows: home
  channels, DMs, and topic lanes as `platform:chat_id:thread_id`. It is the
  starting point for any target question — never hand-guess an id.
- `--file <path>` reads the body from disk (the point of the command: sending a
  job's deliverable without re-running the job). `--subject` prepends a header
  line. `--json` returns the platform's own response including `message_id`.
- Attachment instead of text: put `MEDIA:<path>` in the message text.

## Long bodies

The command splits the body to the platform's limit and sends sequentially, so
one brief can arrive as several messages. The returned `message_id` is the LAST
chunk's: it is the cursor for verification, not the first message.

## Verify the send by reading it back

The exit code proves the first request was accepted, not that the body rendered.
Read the landing zone.

Discord — list the newest messages in the channel (token from the profile `.env`;
never echo it):

```bash
TOKEN=$(grep -E '^DISCORD_BOT_TOKEN=' "$HERMES_HOME/.env" | cut -d= -f2- | tr -d '"'"'"')
curl -s -H "Authorization: Bot $TOKEN" \
  "https://discord.com/api/v10/channels/<channel_id>/messages?limit=6" \
  > /tmp/msgs.json   # then parse and print id, author, timestamp, len(content)
```

Check: every chunk present, in order, and the LAST chunk ends where the file
ends — the tail of the body, not the beginning. Authorship should be the bot.

Telegram — `sendMessage` returns the message object; a forum send that lands in
General instead of the intended topic is a missing `message_thread_id`, visible in
the response the gateway logs.

## Topics on Telegram forums

The Bot API cannot list topics. A name is knowable only from traffic the bot has
seen in that topic, so:

- ask the user to post one word in the topic and read `message_thread_id` from the
  next inbound log line; or
- take the topic link (`t.me/c/<internal>/<id>`) — the trailing number IS the
  thread id.

When a job must post to a topic the bot has never used, the same restriction
applies: it can send there by id, it just cannot find the id itself.
