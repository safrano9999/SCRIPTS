#!/usr/bin/env python3
"""Build and deliver the ephemeral safcontainer welcome documentation."""

from __future__ import annotations

import html
import os
import re
import shutil
import socket
from datetime import datetime
from pathlib import Path

from python_header import env

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
LOCAL_REFERENCE = Path(__file__).resolve().with_name("ref.conf")
REF_SOURCE = LOCAL_REFERENCE if LOCAL_REFERENCE.is_file() else Path("/opt/safrano9999/WELCOME/ref.conf")
PAPER_SOURCE = Path(
    "/opt/safrano9999/SCRIPTS/safrano9999/image/readme/paper.pdf"
)
OUTPUT = README_DIR / "welcome.pdf"
SECTIONS = ("Environment", "Configuration", "Container", "Build")
REFERENCE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def canonical_key(key: str) -> str:
    return "_".join(part for part in key.split("_") if not part.isdigit())


def read_specs() -> tuple[dict[str, str], list[str]]:
    specs: dict[str, str] = {}
    order: list[str] = []
    section = ""
    if not REF_SOURCE.is_file():
        return specs, order
    for raw in REF_SOURCE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section in SECTIONS and REFERENCE.fullmatch(line) and line not in specs:
            order.append(line)
            specs[line] = section
    return specs, order


def resolved_entries() -> dict[str, list[tuple[str, str]]]:
    specs, _ = read_specs()
    by_canonical = {canonical_key(key): value for key, value in specs.items()}
    result = {section: [] for section in SECTIONS}
    for key in sorted(os.environ):
        section = specs.get(key) or by_canonical.get(canonical_key(key))
        if not section:
            continue
        value = env.get(key, "")
        result[section].append((key, value or "blank"))
    return result


def runtime_name() -> str:
    return env.get("CONTAINER_NAME", "").strip() or socket.gethostname()


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
    name = runtime_name()
    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=A4, leftMargin=1.55 * cm, rightMargin=1.55 * cm,
        topMargin=1.45 * cm, bottomMargin=1.45 * cm,
        title=f"Welcome to {name}", author="safrano9999",
    )
    story: list = [
        Paragraph(f"WELCOME TO {html.escape(name)}", pdf_styles["header"]),
        Paragraph(
            "by safrano9999 - runtime map and agent starting point",
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
        "This file is rebuilt inside the ephemeral /README directory. Variables "
        "marked <b>#secret</b> never enter ref.conf and therefore cannot appear "
        "here. Non-secret runtime values remain visible for inspection.",
        pdf_styles,
    )
    add_section(
        story,
        "Vditor Notes",
        "Vditor Notes serves the Markdown workspace from <b>VDITOR_NOTES_PATH</b>. "
        "It provides recursive file management and a Vditor editor while the "
        "workspace can remain in the persistent Hermes Obsidian directory.",
        pdf_styles,
    )

    entries = resolved_entries()
    for section in SECTIONS:
        story.append(PageBreak())
        story.append(Paragraph(f"  {section} variables  ", pdf_styles["section"]))
        for key, value in entries[section]:
            story.append(
                Paragraph(
                    f"<b>{html.escape(key)}</b><br/>"
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


if __name__ == "__main__":
    build_pdf()
