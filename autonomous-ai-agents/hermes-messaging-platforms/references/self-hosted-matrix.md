# Self-hosted Matrix for Hermes, tailnet-only

Goal: a chat channel between the user and Hermes with no third-party moderation layer in the
path. Shape: your own homeserver, bound to loopback, reachable only inside the tailnet, with
Tailscale terminating real TLS.

## 1. Homeserver (Tuwunel, Docker)

Tuwunel is the maintained Rust successor to conduwuit — light (~100 MB RSS), single container.

```yaml
services:
  tuwunel:
    image: ghcr.io/matrix-construct/tuwunel:latest
    container_name: tuwunel
    restart: unless-stopped
    mem_limit: 1g
    ports:
      - "127.0.0.1:8008:8008"   # loopback only — exposure is Tailscale's job, not a publish
    # Optional second binding when a client cannot do MagicDNS: publish on the tailnet address
    # only (NOT 0.0.0.0, which would put the homeserver on the LAN), so http-tolerant clients
    # can reach it at http://<tailnet ip>:8008 with no name resolution and no certificate:
    #   - "100.x.y.z:8008:8008"
    # Caveat: that bind needs the tailscale interface up at container start; it retries until it is.
    volumes:
      - ./data:/var/lib/tuwunel
      - ./tuwunel.toml:/etc/tuwunel.toml:ro
    environment:
      TUWUNEL_CONFIG: /etc/tuwunel.toml
```

`tuwunel.toml` — `server_name` MUST equal the URL clients log in with, or clients reject the
homeserver's responses:

```toml
[global]
server_name = "<host>.<tailnet>.ts.net"
database_path = "/var/lib/tuwunel"
address = "0.0.0.0"
port = 8008
allow_federation = false
allow_registration = true
registration_token = "<random>"

[global.well_known]
client = "https://<host>.<tailnet>.ts.net"
```

Get the tailnet hostname from `tailscale status --json` → `Self.DNSName` (trailing dot stripped).
Federation off is correct: the name is not publicly resolvable anyway, and a private server
should not try to federate.

## 2. TLS ingress with zero public exposure

`tailscale serve` publishes to the tailnet only and can terminate Let's Encrypt certs for the
ts.net name.

1. **Enable Serve + HTTPS certificates on the tailnet first** (admin console; the CLI prints the
   exact link when it refuses). Until then the CLI fails with `Serve is not enabled on your
   tailnet`, and `tailscale status --json` shows `CertDomains: None`.
2. `tailscale serve` needs root unless the user is the operator:
   `sudo tailscale set --operator=$USER` — one-off, and it makes every later serve change
   non-interactive.
3. `sudo tailscale serve --bg --https=443 http://127.0.0.1:8008`
4. Verify from the host, not from a browser elsewhere:
   `curl -sS https://<host>.<tailnet>.ts.net/_matrix/client/versions` and
   `tailscale serve status`. First run takes a few seconds while the cert is issued.

## 3. Accounts and room — client API only

**The image has no shell, so there is no `docker exec bash`.** Do everything over
`/_matrix/client/v3/...` (curl or Python).

- Registration: `POST /_matrix/client/v3/register` with `{}` returns a `session` and
  `[{stages:["m.login.registration_token"]}]`. (The GET form answers `M_UNRECOGNIZED`.) POST
  again with `auth={type:"m.login.registration_token", token:<registration_token>,
  session:<session>}` plus `username`/`password`. The response carries that account's
  `access_token`.
- **The first account registered becomes the server admin** — register the user's account before
  the bot's, or the bot ends up owning the server.
- Create the room unencrypted, as the user's account:
  `POST /_matrix/client/v3/createRoom` with `{name, preset:"private_chat", is_direct:true,
  invite:["@<bot>:<server>"], creation_content:{m.federate:false}}`. A 404 on
  `.../state/m.room.encryption` afterwards means it is unencrypted — which is the intent here.

## 4. Hermes side

`.env` keys: `MATRIX_HOMESERVER=https://<host>.<tailnet>.ts.net`, `MATRIX_USER_ID=@<bot>:<server>`,
`MATRIX_ACCESS_TOKEN`, `MATRIX_DEVICE_ID` (from registration), `MATRIX_ALLOWED_USERS=@<user>:<server>`,
`MATRIX_E2EE_MODE=off`. For a 1:1 chat also set `MATRIX_REQUIRE_MENTION=false` (no `@mention`
needed), `MATRIX_AUTO_THREAD=false` (keeps the timeline flat instead of one thread per reply), and
`MATRIX_HOME_ROOM=<room id>`.

Then, in this order: `hermes plugins enable matrix-platform` → install `mautrix` + `aiosqlite` +
`aiohttp-socks` into the Hermes venv → restart the gateway. See the parent skill for the full
sequence and the config.yaml trap.

Optional hardening: set only `MATRIX_ALLOWED_USERS` (not `MATRIX_ALLOWED_ROOMS`) so the user can
create their own rooms and DMs. The user allowlist is the real gate — `MATRIX_ALLOWED_ROOMS`
would lock the bot to one room.

## 5. Client (Element X on Android)

Log in with `https://<host>.<tailnet>.ts.net`; the phone must be on the tailnet.
**Element X requires HTTPS** — a plain `http://` tailnet IP is refused at login. Element X,
Element Classic, FluffyChat, and SchildiChat all work; the bot joins rooms on invite, and the
adapter needs no client-side plugin.

Android voice notes and images work because Matrix carries media natively and Hermes transcribes
voice messages on every platform — no extra wiring beyond a sane `MATRIX_MAX_MEDIA_BYTES`.

## 6. When a client cannot connect: it is the tailnet layer, not the server

Once the adapter is verified and the homeserver answers on the host, a client that "can't connect"
is a name-resolution problem on that client. **A working curl on the host proves nothing about the
phone**: systemd-resolved keeps the per-link LAN DNS, tailscaled answers MagicDNS names locally
from its netmap, and traffic to the node's own tailnet IP never leaves the host. Reproduce from the
failing device.

1. **Is the client on the tailnet?** `tailscale ping <peer>` — a `pong` (often `via DERP(...)`)
   means the tunnel is up. Ping is handled by tailscaled and bypasses ACLs, so it succeeds even when
   ACLs block real traffic; a pong is not proof the path works.
2. **Did any packet arrive?** While the user retries, watch
   `journalctl -u tailscaled -f | grep -E '<client tailnet ip>|handshake'`. No lines = the device
   never resolved the name. `http: TLS handshake error from <ip>: no SNI ServerName` = the device
   dialed the IP, which `tailscale serve` cannot serve (it routes by SNI).
3. **The `ts.net` zone trap.** The coordinator pushes clients a split-DNS route for the entire
   `ts.net.` zone pointing at Tailscale's *public* nameservers (e.g. 199.247.155.53,
   2620:111:8007::53). A node name has a public record **only while Funnel is enabled**; otherwise
   those servers answer NXDOMAIN *with the authoritative flag*. So a lookup that leaks to that route
   gives the client `ERR_NAME_NOT_RESOLVED` / `DNS_PROBE_FINISHED_NXDOMAIN` while the host resolves
   the same name fine. Inspect what clients are told with `tailscale dns status` (MagicDNS state,
   resolvers, split routes, `Proxied`) and `tailscale debug netmap` → `DNS`.
4. **Never reach for tailnet "Override local DNS" to fix one client.** It does not help a client
   that never applies VPN DNS, and it breaks bare LAN names for *every* device: a host that resolved
   `m5:8081` through the router's DNS plus the `lan` search domain (resolvectl: link DNS 10.0.10.1,
   DNS domain `lan`) now sends `m5.lan` to Tailscale, which forwards it to 1.1.1.1 → NXDOMAIN. If
   override must stay on, restore LAN names with a split-DNS route on the same console page
   (nameserver = the router's IP, restricted to domain `lan`). Revert it when it bought nothing.
5. **Android/EMUI:** the VPN can be up — pong answers, a DERP or direct path exists — while Android
   still does not use its DNS. Check the app's "Use Tailscale DNS settings", Android Private DNS =
   Off/Automatic, and battery/auto-start permissions; clearing the app's data or reinstalling
   resets a wedged VPN DNS registration.
6. **Escapes that remove DNS from the equation.** `tailscale funnel --bg --https=443
   http://127.0.0.1:8008` puts a public record in the very zone the client queries, with the cert
   already valid and MagicDNS irrelevant — at the cost of internet exposure, so set
   `allow_registration = false` first and revert with `tailscale funnel --https=443 off`. The
   zero-exposure alternative is an http-tolerant client (Element classic, FluffyChat, SchildiChat)
   against the homeserver also bound on the tailnet IP; Element X refuses plain http outright.
   Applied outcome of this route: `docker compose up -d` with the extra
   `- "<tailnet ip>:8008:8008"` port, client URL `http://<tailnet ip>:8008`. Verify the intended
   split survives the change — tailnet http 200, **LAN address still refused**, `tailscale serve`
   https unchanged — and expect one transient `Matrix: sync error: 502` in the adapter log from the
   container recreate, which the sync loop retries through (confirm by re-reading the log and by the
   gateway holding an ESTABLISHED socket to the serve port).

**Do not blame the bot's credentials.** Moving `MATRIX_*` between Hermes profiles changes which
profile owns `@<bot>`; a user client authenticating as `@<user>` with its own token is unaffected by
it. Prove the client path from the room rather than from logs:
`GET /rooms/{id}/messages?dir=b&limit=25` — a message from the user's account *after* the questioned
change is direct evidence the client worked then. Tuwunel logs only notable events (registration,
login, room create) and nothing for `/sync`, so an idle log proves nothing either way.

## Why unencrypted is the right default here

Tailscale already carries the traffic inside WireGuard, encrypted end to end between the two
devices. Matrix E2EE on top buys nothing and costs the device-verification dance plus
"unable to decrypt" failures between a rust-sdk client (Element X) and a Python bot (mautrix).
Keep `MATRIX_E2EE_MODE=off`.

**The caveat that bites:** rooms *you* create in Element X default to encrypted. Toggle
encryption off when creating a room, or the bot cannot read it. The room created via the API in
step 3 is already unencrypted, so point the user at that one.

E2EE upgrade path if it is ever wanted: `sudo apt install libolm-dev`, install
`mautrix[encryption]`, set `MATRIX_E2EE_MODE=required`, re-verify devices.
