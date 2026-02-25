# Here are some useful scripts, mostly in Bash

## note – Terminal to Obsidian in One Command

> Looking for a solution to remember important commands or codeblocks?
> Just type `note "and a note"` and your last command will be saved immediately in a Markdown file named after its command.
> No need to search or ask twice — sustainable, saves time and energy.

### Requirements

- Bash
- Any Markdown viewer — Obsidian recommended but optional

### Installation

#### 1. Install the script

```bash
cp note ~/.local/bin/note
chmod +x ~/.local/bin/note
```

#### 2. Create note_config in the same directory

Create a file called `note_config` next to the script — add one line with the path to your folder:

```
PATH_YNOTE=/home/youruser/obsidian/linux
```

#### 3. Add to ~/.bashrc

```bash
echo "alias note='history -a; ~/.local/bin/note'" >> ~/.bashrc
source ~/.bashrc
```

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
