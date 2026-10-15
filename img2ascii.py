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

FLOOR = 90
BRIGHTNESS = 1.4

def img_to_ascii(path, width=35):
    img = Image.open(path).convert("RGB")
    img = ImageOps.autocontrast(img, cutoff=2)

    px_w = width * 2
    px_h = int(px_w * img.height / img.width)
    px_h = max(4, px_h - px_h % 4)
    img = img.resize((px_w, px_h))

    colour = img.load()
    grey = ImageEnhance.Brightness(img.convert("L")).enhance(BRIGHTNESS)
    bits = grey.convert("1").load()

    out = Text()
    for cy in range(0, px_h, 4):
        for cx in range(0, px_w, 2):
            mask = 0
            rs = gs = bs = 0
            for dy in range(4):
                for dx in range(2):
                    r, g, b = colour[cx + dx, cy + dy]
                    rs += r; gs += g; bs += b
                    if bits[cx + dx, cy + dy]:
                        mask |= DOTS[dy][dx]
            r = FLOOR + (rs // 8) * (255 - FLOOR) // 255
            g = FLOOR + (gs // 8) * (255 - FLOOR) // 255
            b = FLOOR + (bs // 8) * (255 - FLOOR) // 255
            out.append(chr(0x2800 + mask), style=f"#{r:02x}{g:02x}{b:02x}")
        out.append("\n")
    return out
if __name__ == "__main__":
    console = Console()

    music = Path(__file__).parent / "music"

    for cover in sorted(music.rglob("cover.jpg")):
        console.print(f"[bold]{cover.parent.name}[/bold]")
        console.print(img_to_ascii(cover))