# vector-image-load-guide

<p align="right"><a href="./README_zh.md">🇨🇳 中文</a></p>

A toolkit for reading and processing vector images, born from hands-on experience batch-processing logo vector assets from various sources.

Covers common vector formats including SVG, PDF, AI, EPS, and CDR. Each format is paired with the most suitable reading approach, along with practical post-processing tools like background removal and color block segmentation.

## Format Support & Recommended Approaches

| Format | Recommended Approach | File | Notes |
|--------|---------------------|------|-------|
| SVG | cairosvg | `cariosvg_reader.py` | Native transparent background support, simple and efficient |
| PDF / AI / SVG | PyMuPDF (fitz) | `fitz_reader.py` | Transparent background support, auto-crops foreground area, good rendering quality |
| CDR | Inkscape CLI | `cdr_reader.py` | CDR is a proprietary format, requires Inkscape for conversion; supports auto-splitting individual logos from multi-logo CDR files |
| EPS | Pillow + PostScript injection | `eps_reader.py` | EPS doesn't support transparent backgrounds; achieves transparency by injecting a safe background color then removing it |
| AI / Other | ImageMagick (wand) | `wand_reader.py` | Fallback option, no transparent background support, useful when fitz can't open the file |

> Inkscape CLI can also read AI, SVG, and PDF, but it's slower due to external process calls. Prefer fitz or cairosvg when possible.

## Highlights

- **CDR multi-logo auto-splitting** (`cdr_reader.py` → `load_cdr`): Parses the object tree via Inkscape `--query-all`, determines whether child elements are independent logos or composite elements based on overlap detection, then recursively splits and exports each one
- **EPS transparent background workaround** (`eps_reader.py`): Automatically finds a "safe color" not present in the image, replaces the background color definition in the EPS source code, renders it, then removes the background using color distance — bypassing EPS's lack of alpha channel support
- **fitz adaptive foreground scaling** (`fitz_reader.py` → `load_fitz`): First renders at low resolution to find the foreground bounding box, then calculates zoom based on actual foreground size, preventing small logos on large canvases from being rendered at insufficient resolution

## Post-processing Tools (`seg_utils/`)

| File | Functionality |
|------|--------------|
| `color_filter.py` | Background removal toolkit: HSV-based black/white background removal, four-corner color sampling removal (floodFill prevents accidentally removing same-colored foreground regions) |
| `process_color_block.py` | Color block mosaic segmentation: handles cases where multiple logos are placed on colored blocks in a single image, auto-splits using color histogram + connected components |

## Installation

```bash
# Python packages
pip install PyMuPDF cairosvg Wand Pillow numpy opencv-python scikit-image

# System dependencies
brew install inkscape        # Required for CDR reading, or download from official website
brew install imagemagick      # Required for wand_reader
```

> If wand reports `MagickWand shared library not found`, run this in your terminal first:
> ```bash
> export MAGICK_HOME=$(brew --prefix imagemagick)
> ```
