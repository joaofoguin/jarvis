"""Gera relatórios em PDF a partir do texto que o JARVIS mostra no chat."""

import os
from datetime import datetime
from pathlib import Path


def reports_folder():
    # Mesma pasta do Claude Code; sem ela, a pasta Documentos do usuário.
    return Path(os.getenv("JARVIS_WORKSPACE") or Path.home() / "Documents")


def latin1(text):
    # As fontes padrão do PDF só têm caracteres latinos; emojis viram "?".
    return text.encode("latin-1", "replace").decode("latin-1")


def save_pdf(title, body, folder=None):
    from fpdf import FPDF

    folder = Path(folder or reports_folder())
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{title.lower().replace(' ', '_')}_{datetime.now():%Y%m%d_%H%M}.pdf"

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 10, latin1(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    pdf.multi_cell(0, 6, latin1(f"Gerado pelo JARVIS em {datetime.now():%d/%m/%Y %H:%M}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", size=11)

    for line in body.splitlines():
        pdf.multi_cell(0, 7, latin1(line) or " ", new_x="LMARGIN", new_y="NEXT")

    pdf.output(str(path))
    return path


def open_file(path):
    # Abre no leitor de PDF padrão; só existe no Windows.
    if hasattr(os, "startfile"):
        os.startfile(path)
