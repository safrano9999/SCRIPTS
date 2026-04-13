# send_message.sh — Agent Instructions

## TL;DR — einfach so benutzen:

```bash
/home/openclaw/Skripte/send_message.sh --agent italy --message "Deine Nachricht hier"
```

Das war's. Der Script löst den Bot-Account automatisch auf und sendet über das OpenClaw Gateway zu Rafael.

---

## Verfügbare Agenten (`--agent`)

| Agent | Bot |
|-------|-----|
| `italy` | @triggershotbot |
| `germany` | @magabuttlerbot |
| `france` | @safran999bot |
| `uk` | @rafael_cos_bot |
| `serbia` | @healy9999bot |
| `russia` | @healer9999bot |
| `china` | @golemjudenbot |
| `america` | @farmerscowbot |

---

## Optionen

```
--agent <region>      Welcher Bot sendet (empfohlen)
--account <botname>   Direkter Bot-Name (nur wenn --agent nicht reicht)
--message / -m        Der Text der gesendet wird (Pflicht)
```

Kein `--agent` und kein `--account` → fällt auf `magabuttlerbot` zurück.

---

## Beispiele

```bash
# Italy schreibt Rafael
/home/openclaw/Skripte/send_message.sh --agent italy --message "Hi, was kann ich tun?"

# Mit Timestamp
/home/openclaw/Skripte/send_message.sh --agent germany --message "Es ist $(date '+%H:%M') Uhr."

# Direkter Bot-Override
/home/openclaw/Skripte/send_message.sh --account triggershotbot --message "Test"
```

---

## Cron-Job (einmalig oder wiederkehrend)

```bash
openclaw cron add \
  --name "Mein Job" \
  --cron "0 9 * * *" \
  --tz "Europe/Vienna" \
  --session isolated \
  --message "Use exec to run: /home/openclaw/Skripte/send_message.sh --agent italy --message \"Guten Morgen!\"" \
  --delete-after-run   # nur bei einmaligen Jobs
```

---

**Ziel:** Rafael's Chat-ID `5475045993` via Telegram. Immer.
