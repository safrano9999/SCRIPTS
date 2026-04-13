# Here are some useful scripts, mostly in Bash

## note – Terminal to MD-File in One Command

> Looking for a solution to remember important commands you type in the console or codeblocks?
> Just type `note "and a note"` and your last command will be saved immediately in a Markdown file named after its command.
> No need to search or ask twice — sustainable, saves time and energy.

### Requirements

- Bash
- Any Markdown viewer — Obsidian recommended but optional

### Installation

#### 1. Clone the repo

```bash
git clone https://github.com/yourusername/SCRIPTS.git ~/Skripte
```

#### 2. Symlink the script into your PATH

```bash
ln -s ~/Skripte/note ~/.local/bin/note
```

No copying needed — changes in the repo are live immediately.

#### 2. Create note_config in the same directory

Create a file called `note_config` next to the script — add one line with the path to your folder (may vary to your setup):

```
PATH_YNOTE=/home/youruser/obsidian/linux
```

#### 4. Add to ~/.bashrc

```bash
echo "alias note='history -a; ~/.local/bin/note'" >> ~/.bashrc
echo 'export PATH="$HOME/.local/bin:$HOME/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"' >> ~/.bashrc
```

Then reload: `source ~/.bashrc`

### Usage

```bash
# Save last command
echo "hello"
note "my comment"
# → echo.md

# Save pipe command
cat file.txt | grep "pattern"
note "search for pattern"
# → pipes.md

# Save last 2 commands
ls -la
grep "test" file.txt
note +1 "my workflow"
# → block.md

# Save last 3 commands
note +2 "comment"
# → block.md

# Paste multiline block (e.g. SQL)
note --block mysql "all users"
# → paste content, Ctrl+D to finish
# → mysql.md
```

### File structure in Obsidian

| File | Content |
|------|---------|
| `command.md` | Single command, named after the program |
| `pipes.md` | Commands with pipes |
| `block.md` | Multiple commands (`+N`) |
| `mysql.md` | Example `--block` input |

### Note format

~~~
---
**my comment** 2026-02-25 14:30
```bash
echo "hello"
```
~~~

# I_dont_care_about_versioning.sh 🚀

Simples Bash-Script zum schnellen Pushen auf GitHub – ohne Schnickschnack.

## Usage

```bash
./push.sh <githubuser> [--auth] [--init] [--reset] [-m "msg"]
```

## Flags

| Flag | Was es macht |
|------|-------------|
| `--auth` | 🔐 GitHub Login via `gh auth login` |
| `--init` | 🛠️ Repo lokal initialisieren & Remote setzen |
| `--reset` | 💥 Komplette History löschen & neu hochladen |
| `-m "msg"` | 💬 Eigene Commit Message (sonst: aktuelles Datum) |

## Beispiele

```bash
# Neues Projekt einrichten
./push.sh meinuser --auth --init --reset -m "initial commit"

# History komplett wegwerfen
./push.sh meinuser --reset -m "clean start"

# Normaler Push
./push.sh meinuser -m "fix bug"

# Push ohne Message → nimmt Timestamp
./push.sh meinuser
```

## ⚠️ Hinweise

- Der **Ordnername** muss mit dem **GitHub Repo-Namen** übereinstimmen
- Bei `--reset` wird die gesamte Git-History unwiderruflich gelöscht
- Bei geschützten Branches (`main`) → Branch Protection in den GitHub Repo-Settings deaktivieren
