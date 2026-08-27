#!/usr/bin/env python3
"""
Genera una portada (1200x630, estética "ventana de terminal") para cada
post de content/{posts,ciberseguridad,cloud}/ que NO tenga ya un
`cover:` en su front matter (si lo tiene, se respeta y no se toca nada).

Pensado para ejecutarse en CI antes de `hugo build` (ver
.github/workflows/hugo.yml), así que no hace falta ejecutarlo a mano salvo
para previsualizar en local con `hugo server`.

Salida: assets/images/covers/<content-base-name>.<lang>.png
Esa ruta la leen (vía resources.Get, sin tocar el front matter de cada post):
  - layouts/_partials/cover.html                              → portada visual
  - layouts/_partials/templates/_funcs/get-page-images.html   → og:image / twitter:image / JSON-LD
"""
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIRS = ["posts", "ciberseguridad", "cloud"]
OUT_DIR = ROOT / "assets" / "images" / "covers"
FONTS_DIR = Path(__file__).resolve().parent / "fonts"

W, H = 1200, 630
BG = (15, 17, 16)
WINDOW_BAR = (22, 25, 23)
BORDER = (38, 43, 40)
ACCENT = (107, 168, 138)
PRIMARY = (196, 202, 197)
SECONDARY = (128, 136, 130)

MONO_BOLD = str(FONTS_DIR / "DejaVuSansMono-Bold.ttf")
MONO = str(FONTS_DIR / "DejaVuSansMono.ttf")

FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_front_matter(text: str) -> dict:
    m = FRONT_MATTER_RE.match(text)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm


def has_manual_cover(text: str) -> bool:
    m = FRONT_MATTER_RE.match(text)
    if not m:
        return False
    return re.search(r"^\s*cover\s*:", m.group(1), re.MULTILINE) is not None


def content_base_and_lang(path: Path):
    """Replica cómo calcula Hugo File.ContentBaseName + Lang para este repo
    (es = idioma por defecto, sin sufijo; en = sufijo .en antes de .md)."""
    name = path.name
    if not name.endswith(".md"):
        return None, None
    stem = name[:-3]
    if stem.endswith(".en"):
        return stem[:-3], "en"
    return stem, "es"


def wrap_title(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = (current + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def fit_title(draw, text, max_width, max_lines=3, start_size=64, min_size=36):
    size = start_size
    while size >= min_size:
        font = ImageFont.truetype(MONO_BOLD, size)
        lines = wrap_title(draw, text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines
        size -= 4
    font = ImageFont.truetype(MONO_BOLD, min_size)
    return font, wrap_title(draw, text, font, max_width)[:max_lines]


def render_cover(title: str, section: str, slug: str, out_path: Path):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    margin = 60
    win_top, win_bottom = 90, H - 70
    d.rounded_rectangle([margin, win_top, W - margin, win_bottom], radius=14,
                         outline=BORDER, width=2, fill=(18, 21, 19))

    bar_h = 40
    d.rounded_rectangle([margin, win_top, W - margin, win_top + bar_h], radius=14, fill=WINDOW_BAR)
    d.rectangle([margin, win_top + bar_h - 14, W - margin, win_top + bar_h], fill=WINDOW_BAR)
    dot_y = win_top + bar_h / 2
    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = margin + 26 + i * 24
        d.ellipse([cx - 6, dot_y - 6, cx + 6, dot_y + 6], fill=color)

    pad_x = margin + 46
    content_top = win_top + bar_h + 40
    max_text_width = (W - margin) - pad_x - 40

    # Etiqueta de sección
    label_font = ImageFont.truetype(MONO_BOLD, 24)
    label_text = f"#{section}"
    lw = d.textlength(label_text, font=label_font)
    pill_pad_x, pill_h = 16, 40
    d.rounded_rectangle(
        [pad_x, content_top, pad_x + lw + pill_pad_x * 2, content_top + pill_h],
        radius=pill_h / 2, outline=ACCENT, width=2,
    )
    d.text((pad_x + pill_pad_x, content_top + 7), label_text, font=label_font, fill=ACCENT)

    # Título, ajustado en tamaño para que quepa en máximo 3 líneas
    title_top = content_top + pill_h + 34
    font_title, lines = fit_title(d, title, max_text_width, max_lines=3)
    line_height = font_title.size + 14
    y = title_top
    for line in lines:
        d.text((pad_x, y), line, font=font_title, fill=PRIMARY)
        y += line_height

    # Línea de prompt con el nombre real del archivo del post
    prompt_font = ImageFont.truetype(MONO, 26)
    prompt_y = win_bottom - 60
    prompt = f"manuel@pcapcafe:~$ cat {slug}.md"
    if d.textlength(prompt, font=prompt_font) > max_text_width:
        prompt = f"manuel@pcapcafe:~$ cat {slug[:24]}\u2026.md"
    d.text((pad_x, prompt_y), prompt, font=prompt_font, fill=SECONDARY)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    print(f"  + {out_path.relative_to(ROOT)}")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    generated, skipped_manual = 0, 0

    for section in CONTENT_DIRS:
        section_dir = ROOT / "content" / section
        if not section_dir.exists():
            continue
        for path in sorted(section_dir.glob("*.md")):
            if path.name.startswith("_index."):
                continue

            text = path.read_text(encoding="utf-8")
            if has_manual_cover(text):
                skipped_manual += 1
                continue

            fm = parse_front_matter(text)
            title = fm.get("title", path.stem)
            base, lang = content_base_and_lang(path)
            if base is None:
                continue

            out_path = OUT_DIR / f"{base}.{lang}.png"
            render_cover(title, section, base, out_path)
            generated += 1

    print(f"\n{generated} portada(s) generada(s), {skipped_manual} post(s) con cover manual (sin tocar).")


if __name__ == "__main__":
    main()
