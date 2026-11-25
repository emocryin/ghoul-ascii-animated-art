# ghoul-ascii

A looping TrueColor ASCII animation inspired by *Tokyo Ghoul*, written in pure Python 3 with zero external dependencies.

![Python](https://img.shields.io/badge/python-3.8%2B-red?style=flat-square)
![Dependencies](https://img.shields.io/badge/dependencies-none-black?style=flat-square)
![Terminal](https://img.shields.io/badge/terminal-Kitty%20%7C%20TrueColor-crimson?style=flat-square)



## Features

- **Rainy Tokyo backdrop** — city skyline with lit windows, neon signs, overhead power lines, a streetlamp casting a light cone, red spider lilies (*higanbana*), and a moon that turns crimson on impact.
- **Detailed ghoul** — layered flowing coat, black mask with a metallic glint, windswept white hair, glowing kakugan with a cross-flare and drifting red smoke, plus 4 rinkaku kagune tentacles crackling with RC lightning.
- **Randomized victim every loop (9s)** — 5 outfit palettes, 4 hairstyles, and a random umbrella that gets knocked spinning onto the asphalt on impact.
- **Effects & physics** — slanted rain splashing on wet asphalt, drifting spider lily petals, impact flash, shockwave ring, camera shake, gravity-driven blood splatter, and an expanding pool of blood.
- **Resize-safe & flicker-free** — reads live terminal dimensions and font aspect ratio, disables line wrapping, and uses DEC 2026 synchronized output for smooth rendering in Kitty.

## Requirements

- Linux / macOS (uses POSIX `termios` / `fcntl` for terminal sizing)
- Python 3.8+ (standard library only)
- A TrueColor terminal emulator ([Kitty](https://sw.kovidgoyal.net/kitty/) recommended)

## Usage

```bash
git clone [https://github.com/YOUR_USERNAME/ghoul-ascii.git](https://github.com/YOUR_USERNAME/ghoul-ascii.git)
cd ghoul-ascii
chmod +x ghoul.py
```

Run in Kitty with a small font size for high-density detail:

```bash
kitty --title "Ghoul" -o background=#000000 -o font_size=7 -o window_padding_width=0 ./ghoul.py
```

Press `Ctrl+C` to exit.

### Themes

Pass a kagune color theme as an argument:

| Theme | Style | Command |
|---|---|---|
| `crimson` *(default)* | Classic red rinkaku | `./ghoul.py crimson` |
| `centipede` | Deep purple kakuja | `./ghoul.py centipede` |
| `owl` | Fiery crimson-orange | `./ghoul.py owl` |

### Fish Shell Function (Optional)

Launch from anywhere with `ghoul` or `ghoul centipede`:

```fish
function ghoul
    set theme crimson
    if test (count $argv) -gt 0
        set theme $argv[1]
    end
    kitty --title "Ghoul" -o background=#000000 -o font_size=7 -o window_padding_width=0 ~/ghoul.py $theme &
end
funcsave ghoul
```
