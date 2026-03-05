'''
通过对 eps 文件注入颜色替换指令，来实现更干净的背景去除。适用于那些无法直接渲染出透明背景的 eps 文件
'''

import numpy as np
import io
import re
from PIL import Image

def cmyk_ghostscript_rgb(cmyk_str):
    cmyk_str = cmyk_str.replace('k', 'setcmykcolor')
    test_eps = f"""%!PS-Adobe-3.0 EPSF-3.0
%%BoundingBox: 0 0 10 10
{cmyk_str}
newpath
0 0 moveto
10 0 lineto
10 10 lineto
0 10 lineto
closepath
fill
showpage
"""
    # 渲染测试 EPS
    test_io = io.BytesIO(test_eps.encode('latin-1'))
    with Image.open(test_io) as test_img:
        test_img.load(scale=1)
        test_arr = np.array(test_img.convert("RGB"))
        # 取中心像素的颜色（避免边缘抗锯齿）
        actual_rgb = test_arr[test_arr.shape[0]//2, test_arr.shape[1]//2]

    actual_rgb = tuple(actual_rgb)
    return actual_rgb


def find_unused_color_for_eps(eps_path):
    """
    分析 EPS 渲染图，寻找一个绝对不存在的颜色作为“安全背景色”
    返回: (rgb_str, cmyk_str, rgb_tuple, cmyk_reverse_rgb_tuple)
    """
    # 1. 快速低清渲染采样 (scale=1 即可，主要为了统计颜色)
    img = Image.open(eps_path)
    img.load(scale=1)
    W, H = img.size
    if max(H, W) > 256:
        scale = 256 / max(H, W)
        img = img.resize((int(W*scale), int(H*scale)), resample=Image.LANCZOS)

    sample_arr = np.array(img.convert("RGB"))
    # 2. 寻找不存在的颜色
    pixels = sample_arr.reshape(-1, 3)
    used_colors = set(map(tuple, pixels))
    used_colors = np.array(list(used_colors), dtype=np.uint8)
    
    candidates = np.random.randint(0, 256, size=(500, 3), dtype=np.uint8)
    diff = candidates[:, None, :] - used_colors[None, :, :]
    dist = np.sqrt(np.sum(diff**2, axis=2))
    min_dist = dist.min(axis=1)
    best_idx = np.argmax(min_dist)
    safe_rgb = candidates[best_idx]

    # 3. 构造指令字符串
    # RGB 格式: "r g b rg" (归一化到 0.0 - 1.0)
    rgb_str = f"{safe_rgb[0]/255:.2f} {safe_rgb[1]/255:.2f} {safe_rgb[2]/255:.2f} rg"

    # CMYK 格式转换 (近似转换，仅用于背景标记)
    r, g, b = [x/255 for x in safe_rgb]
    k = 1 - max(r, g, b)
    if k == 1:
        c, m, y = 0, 0, 0
    else:
        c = (1 - r - k) / (1 - k)
        m = (1 - g - k) / (1 - k)
        y = (1 - b - k) / (1 - k)
    cmyk_str = f"{c:.2f} {m:.2f} {y:.2f} {k:.2f} k"
    
    # 4. 计算 CMYK 反向转换的 RGB, 
    # CMYK 用 Ghostscript 渲染后实际的 RGB 颜色和初始的 RGB 大概率不一致 (RGB->CMYK->RGB 会有偏差),
    # 需要实际渲染一次来获取准确的 RGB 颜色用于后续的像素筛选.
    cmyk_reverse_rgb = cmyk_ghostscript_rgb(cmyk_str)
    return rgb_str, cmyk_str, safe_rgb, cmyk_reverse_rgb

def load_eps(eps_path, scale=4):
    """
    整合流程：寻找安全色 -> 修改源码 -> 渲染 -> NumPy 提取
    """
    # 获取原始源码
    with open(eps_path, 'r', encoding='latin-1') as f:
        content = f.read()

    # 1. 自动寻找安全背景色
    rgb_cmd, cmyk_cmd, safe_rgb_tuple, safe_rgb_tuple_reverse = find_unused_color_for_eps(eps_path)

    # 2. 替换第一个出现的背景定义
    prolog_divider = "%%EndProlog"
    if prolog_divider in content:
        header, body = content.split(prolog_divider, 1)
    else:
        header, body = "", content
    
    # 找到 eps 文件第一个出现的颜色，这个颜色98%的可能性是背景颜色
    first_color_pattern = r'([\d.]+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+[kK]|[\d.]+\s+[\d.]+\s+[\d.]+\s+(?:rg|setrgbcolor))'

    match = re.search(first_color_pattern, body)
    rgb_mode = False 
    if match:
        original_color = match.group(1) 
        if 'rg' in original_color or 'setrgbcolor' in original_color:
            # RGB 格式，替换成 RGB 安全色
            body = body.replace(original_color, rgb_cmd, 1)
            rgb_mode = True
        else:
            # CMYK 或灰度格式，替换成 CMYK 安全色
            body = body.replace(original_color, cmyk_cmd, 1)
    
    new_content = header + prolog_divider + "\n" + body 
    
    # 3. 渲染
    eps_io = io.BytesIO(new_content.encode('latin-1'))
    with Image.open(eps_io) as img:
        img.load(scale=scale)
        arr = np.array(img.convert("RGBA"))

    # 4. 将最可能是安全色的像素提取出来
    if rgb_mode:
        dist = ((arr[:,:,:3] - np.array(safe_rgb_tuple))**2).sum(axis=2)
    else:
        dist = ((arr[:,:,:3] - np.array(safe_rgb_tuple_reverse))**2).sum(axis=2)
    mask = dist < dist.min() + 5  # 容差5，防止压缩等因素导致的颜色偏移
    
    arr[mask, :] = 0  # 将背景像素置 0
    return Image.fromarray(arr)



if __name__ == "__main__":
    load_eps('test_files/sample_eps.eps').save('test.png')