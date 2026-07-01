#!/usr/bin/env python3
"""Build and deliver the ephemeral safcontainer welcome documentation."""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
)


README_DIR = Path(os.environ.get("SAFRANO9999_README_DIR", "/README"))
META_DIR = Path("/usr/local/share/fedora44-ai/readme")
PAPER_SOURCE = Path(
    "/opt/safrano9999/SCRIPTS/safrano9999/image/readme/paper.pdf"
)
OUTPUT = README_DIR / "welcome.pdf"
SOURCES = (
    ("Environment", META_DIR / "env.example"),
    ("Configuration", META_DIR / "config.conf_example"),
    ("Container", META_DIR / "container.example"),
    ("Build", META_DIR / "fedora.build.conf_example"),
)
ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")


def canonical_key(key: str) -> str:
    return "_".join(part for part in key.split("_") if not part.isdigit())


def read_specs() -> tuple[dict[str, tuple[str, bool]], list[str]]:
    specs: dict[str, tuple[str, bool]] = {}
    order: list[str] = []
    for section, path in SOURCES:
        secret = False
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line == "#secret":
                secret = True
                continue
            match = ASSIGNMENT.match(line)
            if match:
                key = match.group(1)
                if key not in specs:
                    order.append(key)
                    specs[key] = (section, secret)
                secret = False
            elif not line:
                secret = False
    return specs, order


def resolved_entries() -> dict[str, list[tuple[str, str, bool]]]:
    specs, order = read_specs()
    by_canonical = {canonical_key(key): value for key, value in specs.items()}
    keys = list(order)
    for key in sorted(os.environ):
        if key not in specs and canonical_key(key) in by_canonical:
            keys.append(key)
            specs[key] = by_canonical[canonical_key(key)]

    for key, value in os.environ.items():
        if canonical_key(key) != "OPENAI_V1_API_KEY_ALIAS":
            continue
        alias = value.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", alias) and alias not in specs:
            keys.append(alias)
            specs[alias] = ("Environment", True)

    result = {section: [] for section, _ in SOURCES}
    for key in keys:
        section, secret = specs[key]
        value = os.environ.get(key, "")
        shown = "exists" if secret and value else "unset" if secret else value or "blank"
        result[section].append((key, shown, secret))
    return result


def styles() -> dict[str, ParagraphStyle]:
    accent = HexColor("#9f1d2d")
    ink = HexColor("#20242a")
    muted = HexColor("#68717d")
    return {
        "accent": accent,
        "header": ParagraphStyle(
            "header", fontName="Helvetica-Bold", fontSize=30,
            textColor=accent, alignment=TA_CENTER, leading=36, spaceAfter=4,
        ),
        "subheader": ParagraphStyle(
            "subheader", fontName="Helvetica", fontSize=10,
            textColor=muted, alignment=TA_CENTER, leading=14, spaceAfter=14,
        ),
        "section": ParagraphStyle(
            "section", fontName="Helvetica-Bold", fontSize=13,
            textColor=white, backColor=accent, borderPad=6,
            leading=17, spaceBefore=14, spaceAfter=9,
        ),
        "body": ParagraphStyle(
            "body", fontName="Helvetica", fontSize=9.5,
            textColor=ink, leading=14, spaceAfter=6,
        ),
        "entry": ParagraphStyle(
            "entry", fontName="Helvetica", fontSize=8.5,
            textColor=ink, leading=12, spaceAfter=4,
        ),
        "code": ParagraphStyle(
            "code", fontName="Courier", fontSize=7.5,
            textColor=ink, backColor=HexColor("#f1f3f5"),
            borderPad=7, leading=10,
        ),
        "footer": ParagraphStyle(
            "footer", fontName="Helvetica", fontSize=8,
            textColor=muted, alignment=TA_CENTER,
        ),
    }


def add_section(story: list, title: str, text: str, pdf_styles: dict) -> None:
    story.append(Paragraph(f"  {html.escape(title)}  ", pdf_styles["section"]))
    story.append(Paragraph(text, pdf_styles["body"]))


def build_pdf() -> Path:
    README_DIR.mkdir(parents=True, exist_ok=True)
    paper_target = README_DIR / "paper.pdf"
    if PAPER_SOURCE.is_file() and (
        not paper_target.exists() or not os.path.samefile(PAPER_SOURCE, paper_target)
    ):
        shutil.copy2(PAPER_SOURCE, paper_target)

    pdf_styles = styles()
    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=A4, leftMargin=1.55 * cm, rightMargin=1.55 * cm,
        topMargin=1.45 * cm, bottomMargin=1.45 * cm,
        title="Welcome to fedora44-ai", author="safrano9999",
    )
    story: list = [
        Paragraph("WELCOME", pdf_styles["header"]),
        Paragraph(
            "fedora44-ai runtime map and agent starting point",
            pdf_styles["subheader"],
        ),
        HRFlowable(width="100%", thickness=3, color=pdf_styles["accent"], spaceAfter=14),
    ]

    add_section(
        story,
        "Start here",
        "Read <b>/README/paper.pdf</b> first. It explains the SOT hierarchy: "
        "shared behavior originates in SCRIPTS, application repositories own "
        "their domain code, and container repositories consume generated files "
        "and hardlinks rather than becoming a second source of truth.",
        pdf_styles,
    )
    add_section(
        story,
        "Runtime documentation",
        "This file is rebuilt inside the ephemeral /README directory. Values "
        "marked <b>#secret</b> in an example are never printed; only their "
        "presence is reported. Configuration, container and build values remain "
        "visible so an agent can inspect the running system.",
        pdf_styles,
    )
    add_section(
        story,
        "Flatnotes",
        "Flatnotes serves the Markdown workspace from <b>FLATNOTES_PATH</b>. "
        "In this instance it can point to the persistent Hermes Obsidian directory "
        "while the Flatnotes service itself remains image-managed.",
        pdf_styles,
    )

    entries = resolved_entries()
    for section, _ in SOURCES:
        story.append(PageBreak())
        story.append(Paragraph(f"  {section} variables  ", pdf_styles["section"]))
        for key, value, secret in entries[section]:
            suffix = " <font color='#68717d'>(secret)</font>" if secret else ""
            story.append(
                Paragraph(
                    f"<b>{html.escape(key)}</b>{suffix}<br/>"
                    f"{html.escape(value)}",
                    pdf_styles["entry"],
                )
            )

    story.append(PageBreak())
    story.append(Paragraph("  Python requirements  ", pdf_styles["section"]))
    requirements = Path("/requirements.txt")
    if requirements.is_file():
        for line in requirements.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                story.append(Paragraph(html.escape(line), pdf_styles["entry"]))
    else:
        story.append(Paragraph("/requirements.txt is not present.", pdf_styles["body"]))

    story.append(PageBreak())
    add_section(
        story,
        "First agent project: a chess service",
        "Use an available published port, keep source in its owning repository, "
        "and bind the FastAPI listener to 0.0.0.0 inside the container. A minimal "
        "starting point is:",
        pdf_styles,
    )
    story.append(
        Preformatted(
            "from fastapi import FastAPI\n"
            "\n"
            "app = FastAPI(title=\"Chess\")\n"
            "\n"
            "@app.get(\"/\")\n"
            "def board():\n"
            "    return {\"status\": \"ready\"}\n"
            "\n"
            "uvicorn chess:app --host 0.0.0.0 --port 13333",
            pdf_styles["code"],
        )
    )
    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            "After the listener is running, execute the CITADEL scan. CITADEL "
            "discovers the port and can map it through localhost, Tailscale or "
            "Cloudflare according to the enabled modules and stored route policy. "
            "Do not hardcode provider-specific routing into the application.",
            pdf_styles["body"],
        )
    )
    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=1, color=pdf_styles["accent"]))
    story.append(
        Paragraph(
            f"Generated {datetime.now().astimezone().isoformat(timespec='seconds')}",
            pdf_styles["footer"],
        )
    )
    doc.build(story)
    print(f"Welcome PDF written: {OUTPUT}")
    return OUTPUT


def deliver(pdf: Path) -> None:
    target = os.environ.get("OPENCLAW_TELEGRAM_CHAT_ID", "").split(",", 1)[0].strip()
    if not target:
        print("Welcome PDF delivery skipped: OPENCLAW_TELEGRAM_CHAT_ID is empty")
        return
    subprocess.run(
        [
            "openclaw", "message", "send", "--channel", "telegram",
            "--target", target, "--message", "fedora44-ai welcome documentation",
            "--media", str(pdf), "--force-document", "--json",
        ],
        check=True,
    )


def fullrun() -> None:
    if os.environ.get("SAFRANO9999_FULLRUN_ON_START", "1").lower() not in {
        "1", "true", "yes", "on",
    }:
        return
    script = Path(os.environ.get("SAFRANO9999_FULLRUN_SCRIPT", "/usr/local/bin/safrano9999-fullrun"))
    if script.is_file():
        subprocess.run([str(script)], check=True)


def main() -> int:
    status = 0
    try:
        deliver(build_pdf())
    except Exception as exc:
        status = 1
        print(f"Welcome documentation failed: {exc}", file=sys.stderr)
    fullrun()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
