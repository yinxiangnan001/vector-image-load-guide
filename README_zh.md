# vector-image-load-guide

<p align="right"><a href="./README.md">🇬🇧 English</a></p>

矢量图读取与处理工具箱，源于批量处理各种来源的 logo 矢量素材的实战经验。

覆盖 SVG、PDF、AI、EPS、CDR 等常见矢量格式，针对每种格式选择了最合适的读取方案，并提供了去背景、色块分割等实用的后处理工具。

## 格式支持与推荐方案

| 格式 | 推荐方案 | 文件 | 说明 |
|------|---------|------|------|
| SVG | cairosvg | `cariosvg_reader.py` | 原生支持透明背景，简单高效 |
| PDF / AI / SVG | PyMuPDF (fitz) | `fitz_reader.py` | 支持透明背景，自动裁剪前景区域，渲染质量好 |
| CDR | Inkscape CLI | `cdr_reader.py` | CDR 是闭源格式，只能借助 Inkscape 转换；支持从多 logo 的 CDR 中自动拆分独立 logo |
| EPS | Pillow + PostScript 注入 | `eps_reader.py` | EPS 不支持透明背景，通过注入安全背景色再抠除的方式实现透明化 |
| AI / 其他 | ImageMagick (wand) | `wand_reader.py` | 备选方案，不支持透明背景，适合 fitz 打不开时兜底 |

> Inkscape CLI 也能读取 AI、SVG、PDF，但因为是外部进程调用，速度较慢，建议优先用 fitz 或 cairosvg。

## 亮点

- **CDR 多 logo 自动拆分**（`cdr_reader.py` → `load_cdr`）：通过 Inkscape `--query-all` 解析对象树，根据子元素是否重叠判断是独立 logo 还是组合元素，递归拆分并逐个导出
- **EPS 透明背景方案**（`eps_reader.py`）：自动寻找图中不存在的"安全色"，替换 EPS 源码中的背景色定义，渲染后用颜色距离抠除背景，绕过 EPS 不支持透明通道的限制
- **fitz 前景自适应缩放**（`fitz_reader.py` → `load_fitz`）：先低分辨率渲染找前景包围盒，再按前景实际尺寸计算 zoom，避免小 logo 在大画布上渲染后分辨率不足

## 后处理工具 (`seg_utils/`)

| 文件 | 功能 |
|------|------|
| `color_filter.py` | 去背景工具集：HSV 去黑/白背景、四角取色去背景（floodFill 防止误伤前景同色区域） |
| `process_color_block.py` | 色块拼图分割：处理多个 logo 拼在同一张彩色色块图上的情况，按颜色直方图 + 连通域自动拆分 |

## 依赖安装

```bash
# Python 库
pip install PyMuPDF cairosvg Wand Pillow numpy opencv-python scikit-image

# 系统依赖
brew install inkscape        # CDR 读取必需，也可从官网下载安装
brew install imagemagick      # wand_reader 必需
```

> wand 如果报 `MagickWand shared library not found`，需要在终端先执行：
> ```bash
> export MAGICK_HOME=$(brew --prefix imagemagick)
> ```
