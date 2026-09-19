#!/usr/bin/env python3
"""
Sound event detection template — doorbell ring monitor.
Captures audio from ALSA device, computes RMS energy per chunk,
triggers Telegram alert on sustained loud sound using a sliding window.

Customize: thresholds, chunk duration, ALSA card number, alert message.
"""

import subprocess
import struct
import time
import math
import os
import sys
import signal
import logging
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import json

# --- Configuration ---
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION_SEC = 0.5
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION_SEC)
ALERT_THRESHOLD = 5000       # RMS floor (ambient ~1200-2000)
TRIGGER_LOUD = 2             # loud chunks needed within window
TRIGGER_WINDOW = 4           # sliding window size (4 × 0.5s = 2s)
COOLDOWN_SEC = 30            # min seconds between alerts
ALSA_CONFIG = "/tmp/alsa_direct.conf"

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "1867239837")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("ring_monitor")


def ensure_alsa_config():
    if not os.path.exists(ALSA_CONFIG):
        with open(ALSA_CONFIG, "w") as f:
            # Adjust card number for your device
            f.write("pcm.!default {\n    type hw\n    card 2\n    device 0\n}\n")


def send_telegram(text):
    if not BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN not set")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urlencode({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
    try:
        with urlopen(Request(url, data=data), timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                log.info("Telegram alert sent")
                return True
            log.error(f"Telegram error: {result}")
            return False
    except Exception as e:
        log.error(f"Telegram failed: {e}")
        return False


def compute_rms(audio_bytes):
    n = len(audio_bytes) // 2
    if n == 0:
        return 0
    samples = struct.unpack(f"<{n}h", audio_bytes[: n * 2])
    return math.sqrt(sum(s * s for s in samples) / n)


def start_arecord():
    env = os.environ.copy()
    env["ALSA_CONFIG_PATH"] = ALSA_CONFIG
    proc = subprocess.Popen(
        ["arecord", "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", str(CHANNELS), "-D", "default", "-t", "raw"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    log.info(f"arecord started (pid {proc.pid})")
    return proc


def main():
    ensure_alsa_config()
    running = True

    def handle_signal(sig, frame):
        nonlocal running
        log.info("Stopping...")
        running = False
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Calibrate ambient noise (3s)
    log.info("Calibrating ambient noise (3s)...")
    proc = start_arecord()
    calib = []
    for _ in range(int(3.0 / CHUNK_DURATION_SEC)):
        raw = proc.stdout.read(CHUNK_SAMPLES * 2)
        if len(raw) < CHUNK_SAMPLES * 2:
            proc.terminate()
            sys.exit(1)
        calib.append(compute_rms(raw))
    proc.terminate()
    proc.wait()

    ambient = sum(calib) / len(calib)
    threshold = max(ambient * 3, ALERT_THRESHOLD)
    log.info(f"Ambient RMS: {ambient:.0f}, threshold: {threshold:.0f}")

    # Main loop with sliding window
    proc = start_arecord()
    recent_chunks = []  # bools: True=loud
    last_alert = 0
    log.info("Monitoring started...")

    while running:
        raw = proc.stdout.read(CHUNK_SAMPLES * 2)
        if not raw or len(raw) < CHUNK_SAMPLES * 2:
            log.warning("Audio read failed, restarting arecord...")
            proc.terminate()
            proc.wait()
            time.sleep(1)
            proc = start_arecord()
            continue

        rms = compute_rms(raw)
        ts = datetime.now().strftime("%H:%M:%S")

        is_loud = rms > threshold
        recent_chunks.append(is_loud)
        if len(recent_chunks) > TRIGGER_WINDOW:
            recent_chunks.pop(0)

        loud_count = sum(recent_chunks)

        if is_loud:
            bar = "#" * min(int(rms / 1000), 40)
            log.info(f"[{ts}] LOUD  RMS={rms:7.0f} |{bar} (window: {loud_count}/{TRIGGER_WINDOW})")
        elif loud_count > 0:
            log.debug(f"[{ts}] quiet RMS={rms:7.0f} (window: {loud_count}/{TRIGGER_WINDOW})")

        if loud_count >= TRIGGER_LOUD:
            now = time.time()
            if now - last_alert >= COOLDOWN_SEC:
                log.warning(f"*** ALERT at {ts} RMS={rms:.0f} window={loud_count}/{TRIGGER_WINDOW} ***")
                send_telegram(
                    f"🔔 <b>Sound Alert!</b>\n"
                    f"Time: {datetime.now().strftime('%H:%M:%S')}\n"
                    f"Level: {rms:.0f} (threshold: {threshold:.0f})"
                )
                last_alert = now
                recent_chunks.clear()
            else:
                log.info(f"In cooldown ({COOLDOWN_SEC}s)")
                recent_chunks.clear()

    proc.terminate()
    proc.wait()
    log.info("Stopped.")


if __name__ == "__main__":
    main()