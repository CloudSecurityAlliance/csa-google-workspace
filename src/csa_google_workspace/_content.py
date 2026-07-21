"""Plain-text extraction helpers for Docs/Slides API responses. Text runs only."""


def _para_text(paragraph: dict) -> str:
    return "".join(e.get("textRun", {}).get("content", "")
                   for e in paragraph.get("elements", []))


def _element_text(el: dict) -> str:
    if "paragraph" in el:
        return _para_text(el["paragraph"])
    if "table" in el:
        parts = []
        for row in el["table"].get("tableRows", []):
            for cell in row.get("tableCells", []):
                parts.extend(_element_text(c) for c in cell.get("content", []))
        return "".join(parts)
    return ""


def doc_text(document: dict) -> str:
    return "".join(_element_text(el) for el in document.get("body", {}).get("content", []))


def doc_paragraphs(document: dict) -> list[str]:
    out = []
    for el in document.get("body", {}).get("content", []):
        if "paragraph" in el:
            out.append(_para_text(el["paragraph"]).rstrip("\n"))
    return out
