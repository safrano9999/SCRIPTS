#!/usr/bin/env python3
"""
nextcloud_mariadb_to_postgres.py
Migriert eine Nextcloud-Datenbank von MariaDB zu PostgreSQL.
Benötigt: pgloader (sudo apt install pgloader)
"""

import subprocess
import sys
import os
import tempfile
import getpass

# ANSI colors
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def hr():
    print(f"{CYAN}{'─' * 60}{RESET}")

def header(text):
    hr()
    print(f"{BOLD}{CYAN}{text}{RESET}")
    hr()

def ok(text):
    print(f"{GREEN}✓ {text}{RESET}")

def warn(text):
    print(f"{YELLOW}⚠ {text}{RESET}")

def err(text):
    print(f"{RED}✗ {text}{RESET}")

def ask(prompt, secret=False):
    if secret:
        return getpass.getpass(f"{BOLD}{prompt}{RESET}: ")
    val = input(f"{BOLD}{prompt}{RESET}: ").strip()
    return val

def ask_default(prompt, default):
    val = input(f"{BOLD}{prompt}{RESET} [{default}]: ").strip()
    return val if val else default

def check_pgloader():
    result = subprocess.run(["which", "pgloader"], capture_output=True)
    if result.returncode != 0:
        err("pgloader nicht gefunden!")
        print("Installieren mit:")
        print(f"  {YELLOW}sudo apt install pgloader{RESET}")
        sys.exit(1)
    ok("pgloader gefunden")

def check_psql():
    result = subprocess.run(["which", "psql"], capture_output=True)
    if result.returncode != 0:
        warn("psql nicht gefunden — Verbindungstest übersprungen")
        return False
    return True

def test_mariadb(host, port, user, password, db):
    print("Teste MariaDB-Verbindung...")
    cmd = [
        "mysql",
        f"-h{host}", f"-P{port}", f"-u{user}", f"-p{password}",
        db, "-e", "SELECT 1;"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err(f"MariaDB-Verbindung fehlgeschlagen:\n{result.stderr.strip()}")
        return False
    ok("MariaDB-Verbindung OK")
    return True

def test_postgres(host, port, user, password, db):
    print("Teste PostgreSQL-Verbindung...")
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    cmd = ["psql", f"-h{host}", f"-p{port}", f"-U{user}", f"-d{db}", "-c", "SELECT 1;"]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        err(f"PostgreSQL-Verbindung fehlgeschlagen:\n{result.stderr.strip()}")
        return False
    ok("PostgreSQL-Verbindung OK")
    return True

def create_pgloader_config(maria, pg):
    config = f"""LOAD DATABASE
     FROM mysql://{maria['user']}:{maria['password']}@{maria['host']}:{maria['port']}/{maria['db']}
     INTO postgresql://{pg['user']}:{pg['password']}@{pg['host']}:{pg['port']}/{pg['db']}

WITH include drop, create tables, create indexes, reset sequences,
     workers = 4, concurrency = 1,
     multiple readers per thread, rows per range = 50000

SET PostgreSQL PARAMETERS
     maintenance_work_mem to '256MB',
     work_mem to '64MB'

CAST type bigint when (= precision 20) to bigserial drop typemod,
     type int when (= precision 11) to serial drop typemod,
     type int when (= precision 10) to integer drop typemod,
     type tinyint to boolean using tinyint-to-boolean,
     type datetime to timestamptz drop typemod

MATERIALIZE VIEWS ALL

EXCLUDING TABLE NAMES MATCHING ~/^oc_filecache_extended$/

BEFORE LOAD DO
$$ CREATE EXTENSION IF NOT EXISTS unaccent; $$;
"""
    return config

def run_pgloader(config_path):
    print(f"\n{YELLOW}Starte pgloader Migration...{RESET}")
    print("Das kann je nach Datenbankgröße einige Minuten dauern.\n")
    result = subprocess.run(
        ["pgloader", "--verbose", config_path],
        text=True
    )
    return result.returncode == 0

def print_nextcloud_config(pg):
    header("Nextcloud config.php anpassen")
    print("Im Nextcloud-Container folgende Werte in config/config.php setzen:\n")
    print(f"""  {YELLOW}'dbtype'     => 'pgsql',{RESET}
  {YELLOW}'dbname'     => '{pg['db']}',{RESET}
  {YELLOW}'dbhost'     => '{pg['host']}:{pg['port']}',{RESET}
  {YELLOW}'dbuser'     => '{pg['user']}',{RESET}
  {YELLOW}'dbpassword' => '{pg['password']}',{RESET}""")
    print(f"""
Danach in den Container:
  {CYAN}podman exec -it <nextcloud-container> bash{RESET}
  {CYAN}php occ maintenance:mode --on{RESET}
  {CYAN}# config.php anpassen{RESET}
  {CYAN}php occ maintenance:mode --off{RESET}
  {CYAN}php occ db:add-missing-indices{RESET}
  {CYAN}php occ db:add-missing-columns{RESET}
  {CYAN}php occ db:add-missing-primary-keys{RESET}
""")

def main():
    header("Nextcloud: MariaDB → PostgreSQL Migration")

    # Voraussetzungen prüfen
    check_pgloader()
    has_psql = check_psql()
    print()

    # MariaDB Creds
    header("MariaDB Quelldatenbank")
    maria = {}
    maria['host']     = ask_default("Host", "127.0.0.1")
    maria['port']     = ask_default("Port", "3306")
    maria['db']       = ask_default("Datenbank", "nextcloud")
    maria['user']     = ask_default("Benutzer", "nextcloud")
    maria['password'] = ask("Passwort", secret=True)
    print()

    # Verbindungstest MariaDB
    if not test_mariadb(maria['host'], maria['port'], maria['user'], maria['password'], maria['db']):
        cont = ask("Trotzdem fortfahren? (j/n)", secret=False)
        if cont.lower() != 'j':
            sys.exit(1)

    print()

    # PostgreSQL Creds
    header("PostgreSQL Zieldatenbank")
    pg = {}
    pg['host']     = ask_default("Host", "127.0.0.1")
    pg['port']     = ask_default("Port", "5432")
    pg['db']       = ask_default("Datenbank", "nextcloud")
    pg['user']     = ask_default("Benutzer", "nextcloud")
    pg['password'] = ask("Passwort", secret=True)
    print()

    # Verbindungstest PostgreSQL
    if has_psql:
        if not test_postgres(pg['host'], pg['port'], pg['user'], pg['password'], pg['db']):
            cont = ask("Trotzdem fortfahren? (j/n)", secret=False)
            if cont.lower() != 'j':
                sys.exit(1)

    print()

    # Zusammenfassung
    header("Zusammenfassung")
    print(f"  MariaDB:    {maria['user']}@{maria['host']}:{maria['port']}/{maria['db']}")
    print(f"  PostgreSQL: {pg['user']}@{pg['host']}:{pg['port']}/{pg['db']}")
    print()
    warn("ACHTUNG: Ziel-DB wird geleert und neu befüllt!")
    confirm = ask("Migration starten? (ja/nein)", secret=False)
    if confirm.lower() not in ("ja", "j"):
        print("Abgebrochen.")
        sys.exit(0)

    # pgloader config schreiben
    config = create_pgloader_config(maria, pg)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.load', delete=False) as f:
        f.write(config)
        config_path = f.name

    ok(f"pgloader-Config geschrieben: {config_path}")
    print()

    # Migration
    success = run_pgloader(config_path)
    os.unlink(config_path)

    print()
    if success:
        ok("Migration abgeschlossen!")
        print_nextcloud_config(pg)
    else:
        err("Migration fehlgeschlagen. Siehe Ausgabe oben.")
        print(f"\nTipp: Config manuell prüfen mit {YELLOW}pgloader --verbose <config.load>{RESET}")
        sys.exit(1)

if __name__ == "__main__":
    main()
