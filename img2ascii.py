from PIL import Image, ImageOps
from rich.console import Console
from rich.text import Text
from PIL import Image, ImageOps, ImageEnhance
from rich.text import Text
from pathlib import Path

RAMP = "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. "

DOTS = [[0x01, 0x08],
        [0x02, 0x10],
        [0x04, 0x20],
        [0x40, 0x80]]

FLOOR = 65
BRIGHTNESS = 0.9

def img_to_ascii(path, width=70):
    img = Image.open(path).convert("RGB")
    img = ImageOps.autocontrast(img, cutoff=2)

    # terminal cells are about twice as tall as wide
    height = max(1, int(width * img.height / img.width / 2))
    img = img.resize((width, height))

    colour = img.load()
    grey = ImageEnhance.Brightness(img.convert("L")).enhance(BRIGHTNESS)
    lum = grey.load()

    last = len(RAMP) - 1
    out = Text()
    for y in range(height):
        for x in range(width):
            ch = RAMP[(255 - lum[x, y]) * last // 255]
            r, g, b = colour[x, y]
            r = FLOOR + r * (255 - FLOOR) // 255
            g = FLOOR + g * (255 - FLOOR) // 255
            b = FLOOR + b * (255 - FLOOR) // 255
            out.append(ch, style=f"#{r:02x}{g:02x}{b:02x}")
        out.append("\n")
    return out


if __name__ == "__main__":
    console = Console()

    music = Path(__file__).parent / "music"

    for cover in sorted(music.rglob("cover.jpg")):
        console.print(f"[bold]{cover.parent.name}[/bold]")
        console.print(img_to_ascii(cover))