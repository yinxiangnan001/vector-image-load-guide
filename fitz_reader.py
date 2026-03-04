'''
.pdf .ai .svg 首选 fitz (PyMuPDF), 它支持透明背景, 将矢量图渲染为位图, 适合处理矢量图文件. 
其他库如 pdf2image 可能不支持透明背景, 或者渲染质量较差. 

安装方式: pip install PyMuPDF

'''

import fitz 
from PIL import Image 
import numpy as np 


def load_fitz_basic(input_path, min_size=1024):
    # 基础用法
    doc = fitz.open(input_path)
    page = doc[0]
    rect = page.rect
    max_dim = max(rect.width, rect.height)
    zoom = max(min_size / max_dim, 1.0)
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=True)
    img = Image.frombytes("RGBA", [pix.width, pix.height], pix.samples)
    return img


def load_fitz(input_path, min_size=512):
    # 只提取前景, 且以合适的 zoom 渲染
    doc = fitz.open(input_path)
    page = doc[0]

    # 先用 zoom=1 低分辨率渲染，找前景包围盒
    pix_low = page.get_pixmap(alpha=True)
    alpha = np.frombuffer(pix_low.samples, dtype=np.uint8).reshape(pix_low.height, pix_low.width, 4)[:, :, 3]
    ys, xs = np.where(alpha > 0)
    if len(xs) == 0:
        # 没有前景，直接返回空图
        return Image.frombytes("RGBA", [pix_low.width, pix_low.height], pix_low.samples)

    fg_w = xs.max() - xs.min()
    fg_h = ys.max() - ys.min()
    fg_max_dim = max(fg_w, fg_h)

    # 根据前景尺寸计算 zoom，使前景区域放大到 min_size
    zoom = max(min_size / fg_max_dim, 1.0)
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=True)
    img = Image.frombytes("RGBA", [pix.width, pix.height], pix.samples)
    img = img.crop(img.getbbox())
    return img


if __name__ == "__main__":
    import os 
    
    os.makedirs('outputs', exist_ok=True)
    img = load_fitz('test_files/sample.ai')
    img.save('outputs/sample_ai.png')
