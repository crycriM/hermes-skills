# Nginx Reverse Proxy for whisper-server

The nginx `/whisper/` location proxies to the post-processing proxy on port 9001 (not directly to whisper-server port 9000). See `references/whisper-proxy.md` for the proxy layer.

## Nginx location block

In `~/projects/pelemello/reverse-proxy/nginx.conf` (inside the port 8444 server block):

```nginx
    # ─── Whisper STT ─────────────────────────────────────────────────
    location /whisper/ {
        auth_basic "STT Service";
        auth_basic_user_file /etc/nginx/auth/stt.htpasswd;
        proxy_pass http://127.0.0.1:9001/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
```

Note: `proxy_pass` targets port `9001` (whisper-proxy), not `9000` (whisper-server raw).

## Services portal entry

Add to `/var/www/services/services.html` (inside the `.services` div, before the footer):

```html
    <a class="service" href="/whisper/">
      <span class="service-name">Whisper STT</span>
      <span class="service-path">/whisper/</span>
    </a>
```

Note: `/var/www/services/` may be owned by root. Fix before editing:
```bash
sudo chmod 775 /var/www/services/ && sudo chown cricri:cricri /var/www/services/
```

## Auth setup

```bash
sudo mkdir -p /etc/nginx/auth
sudo htpasswd -cb /etc/nginx/auth/stt.htpasswd stt_user "SttWhisper2026!"
# Add more users:
sudo htpasswd /etc/nginx/auth/stt.htpasswd <another_user>
```

## whisper-server service file

Path: `~/.config/systemd/user/whisper-server.service`

Key line — always bind to localhost:
```
ExecStart=/opt/whisper.cpp/build/bin/whisper-server -m /opt/whisper.cpp/models/ggml-small.bin --port 9000 --host 127.0.0.1 -t 4 -l en
```

After editing: `systemctl --user daemon-reload && systemctl --user restart whisper-server`

## Test

```bash
# Health check through proxy
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9001/health
# Expected: 200

# Via nginx (no auth — expect 401)
curl -sk -o /dev/null -w "%{http_code}" https://127.0.0.1:8444/whisper/
# Expected: 401

# Via nginx (with auth)
curl -sk -u "stt_user:SttWhisper2026!" -o /dev/null -w "%{http_code}" https://127.0.0.1:8444/whisper/
# Expected: 200

# Full STT test with audio file (through proxy)
curl -sk -u "stt_user:SttWhisper2026!" \
  -F "file=@test.wav;type=audio/wav" \
  -F "temperature=0.0" \
  -F "response_format=text" \
  https://127.0.0.1:8444/whisper/inference
```

## Remote access

Remote machines hit: `https://<host>:8444/whisper/inference`

Prerequisite: port 8444 open (check `sudo ufw status` — currently inactive).
