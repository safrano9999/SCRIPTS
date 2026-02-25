#!/bin/bash

PATH_YNOTE="$HOME/obsidian/linux"
HISTFILE_PATH="${HISTFILE:-$HOME/.bash_history}"

# --block Modus
if [[ "$1" == "--block" ]]; then
    EXE_NAME="$2"
    COMMENT="$3"
    [ -z "$EXE_NAME" ] && { echo "❌ Verwendung: note --block <dateiname> [kommentar]"; exit 1; }
    echo "📋 Inhalt einfügen, dann Ctrl+D zum Abschliessen:"
    CONTENT=$(cat)
    [ -z "$CONTENT" ] && { echo "❌ Nichts eingegeben."; exit 1; }
    mkdir -p "$PATH_YNOTE"
    printf -- '---\n**%s** %s\n```\n%s\n```\n' "${COMMENT:-ohne Kommentar}" "$(date '+%Y-%m-%d %H:%M')" "$CONTENT" >> "$PATH_YNOTE/$EXE_NAME.md"
    echo "✅ Gespeichert in $EXE_NAME.md"
    exit 0
fi

USER_OFFSET=0
if [[ $1 =~ ^\+([0-9]+)$ ]]; then
    USER_OFFSET=${BASH_REMATCH[1]}
    shift
fi

LINES=$((USER_OFFSET + 1))

LAST_CMD=$(tail -n 20 "$HISTFILE_PATH" \
    | grep -vE "^\s*(note|history -a)" \
    | tail -n "$LINES" \
    | sed 's/[[:space:]]*$//')

[ -z "$LAST_CMD" ] && { echo "❌ Fehler: Befehl nicht gefunden."; exit 1; }

if [[ $USER_OFFSET -gt 0 ]]; then
    EXE_NAME="block"
elif [[ "$LAST_CMD" == *"|"* ]]; then
    EXE_NAME="pipes"
else
    EXE_NAME=$(echo "$LAST_CMD" | awk '{if($1=="sudo") print $2; else print $1}' | xargs basename)
fi

mkdir -p "$PATH_YNOTE"
COMMENT="$*"

printf -- '---\n**%s** %s\n```bash\n%s\n```\n' "${COMMENT:-ohne Kommentar}" "$(date '+%Y-%m-%d %H:%M')" "$LAST_CMD" >> "$PATH_YNOTE/$EXE_NAME.md"

echo "✅ Gespeichert: in $EXE_NAME.md"
