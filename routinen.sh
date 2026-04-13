#!/bin/bash
# ─────────────────────────────────────────────────────────
# routinen.sh  –  Tagesroutinen mit gum table
# ─────────────────────────────────────────────────────────

source "$(dirname "$0")/.env"
DB_USER="botuser"
DB_PASS=$bot_pw
DB_HOST="127.0.0.1"
DB_NAME="telegram_bot"

function run_sql() {
    mariadb -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" -D "$DB_NAME" -N -e "$1"
}

function show_table() {
    TERM_W=$(tput cols 2>/dev/null || echo 120)

    W_ID=4
    W_S=3
    W_NOTIZ=60
    OVERHEAD=17
    W_THEMA=$(( TERM_W - W_ID - W_S - W_NOTIZ - OVERHEAD ))
    (( W_THEMA < 10 )) && W_THEMA=10

    QUERY="
    SELECT
        ri.id,
        CASE WHEN rl.checked_at IS NOT NULL THEN '✔' ELSE ' ' END,
        IFNULL(ri.label, ''),
        LEFT(IFNULL(rl.note, ''), 256)
    FROM routine_items ri
    LEFT JOIN routine_log rl
        ON ri.id = rl.item_id AND rl.session_date = CURDATE()
    ORDER BY ri.id ASC;"

    csv_field() {
        local val="${1//$'\n'/ }"
        val="${val//$'\r'/ }"
        printf '"%s"' "${val//\"/\"\"}"
    }

    {
        # Erste Zeile = Header (gum table liest das automatisch)
        printf 'ID,S,Thema,Notiz\n'
        run_sql "$QUERY" | while IFS=$'\t' read -r id status label note; do
            printf '%s,%s,%s,%s\n' \
                "$(csv_field "$id")" \
                "$(csv_field "$status")" \
                "$(csv_field "$label")" \
                "$(csv_field "$note")"
        done
    } | gum table \
        --border rounded \
        --border.foreground 240 \
        --header.foreground 212 \
        --widths "${W_ID},${W_S},${W_THEMA},${W_NOTIZ}" \
        --print
}

# ── Main ─────────────────────────────────────────────────

if [ -z "$1" ]; then
    show_table | lolcat
    exit 0
fi

ITEM_ID=$1
ACTION=$2
NOTE=$3

EXISTS=$(run_sql "SELECT count(*) FROM routine_log WHERE item_id=$ITEM_ID AND session_date=CURDATE()")
if [ "$EXISTS" -eq "0" ]; then
    run_sql "INSERT INTO routine_log (item_id, session_date) VALUES ($ITEM_ID, CURDATE())"
fi

case "$ACTION" in
    "+") run_sql "UPDATE routine_log SET checked_at=NOW()  WHERE item_id=$ITEM_ID AND session_date=CURDATE()" ;;
    "-") run_sql "UPDATE routine_log SET checked_at=NULL   WHERE item_id=$ITEM_ID AND session_date=CURDATE()" ;;
esac

if [ -n "$NOTE" ]; then
    SAFE=$(echo "$NOTE" | sed "s/'/''/g")
    run_sql "UPDATE routine_log SET note='$SAFE' WHERE item_id=$ITEM_ID AND session_date=CURDATE()"
fi

show_table | lolcat
