'''
通过对 eps 文件注入颜色替换指令，来实现更干净的背景去除。适用于那些无法直接渲染出透明背景的 eps 文件
v2: 优先通过解析 CorelDRAW Object 结构精确定位背景色，fallback 到第一个颜色指令
'''

import numpy as np
import io
import re
from PIL import Image
import struct


def read_eps_content(eps_path):
    """读取 EPS 内容，自动处理 DOS EPS Binary 格式"""
    with open(eps_path, 'rb') as f:
        header = f.read(4)
        if header == b'\xc5\xd0\xd3\xc6':
            ps_offset, ps_length = struct.unpack('<II', f.read(8))
            f.seek(ps_offset)
            data = f.read(ps_length).decode('latin-1')
        else:
            f.seek(0)
            data = f.read().decode('latin-1')
    # 统一换行符：\r\n -> \n, 单独的 \r -> \n
    return data.replace('\r\n', '\n').replace('\r', '\n')


def cmyk_ghostscript_rgb(cmyk_str):
    """通过 Ghostscript 渲染获取 CMYK 转 RGB 的实际颜色，cmyk_str 为纯数值如 '0.94 0.48 0.00 0.16'"""
    test_eps = f"""%!PS-Adobe-3.0 EPSF-3.0
%%BoundingBox: 0 0 10 10
{cmyk_str} setcmykcolor
newpath
0 0 moveto
10 0 lineto
10 10 lineto
0 10 lineto
closepath
fill
showpage
"""
    test_io = io.BytesIO(test_eps.encode('latin-1'))
    with Image.open(test_io) as test_img:
        test_img.load(scale=1)
        test_arr = np.array(test_img.convert("RGB"))
        actual_rgb = test_arr[test_arr.shape[0]//2, test_arr.shape[1]//2]
    return tuple(actual_rgb)


def find_unused_color_for_eps(eps_content):
    """
    分析 EPS 渲染图，寻找一个绝对不存在的颜色作为"安全背景色"
    返回: (rgb_values, cmyk_values, safe_rgb_tuple, cmyk_reverse_rgb_tuple)
    rgb_values/cmyk_values 不含操作符，只有数值部分
    """
    eps_data = eps_content.encode('latin-1')
    img = Image.open(io.BytesIO(eps_data))
    img.load(scale=1)
    W, H = img.size
    if max(H, W) > 256:
        scale = 256 / max(H, W)
        img = img.resize((int(W*scale), int(H*scale)), resample=Image.LANCZOS)

    sample_arr = np.array(img.convert("RGB"))
    pixels = sample_arr.reshape(-1, 3)
    used_colors = np.array(list(set(map(tuple, pixels))), dtype=np.uint8)

    candidates = np.random.randint(0, 256, size=(500, 3), dtype=np.uint8)
    diff = candidates[:, None, :] - used_colors[None, :, :]
    dist = np.sqrt(np.sum(diff**2, axis=2))
    min_dist = dist.min(axis=1)
    safe_rgb = candidates[np.argmax(min_dist)]

    rgb_values = f"{safe_rgb[0]/255:.2f} {safe_rgb[1]/255:.2f} {safe_rgb[2]/255:.2f}"

    r, g, b = [x/255 for x in safe_rgb]
    k = 1 - max(r, g, b)
    if k == 1:
        c, m, y = 0, 0, 0
    else:
        c = (1 - r - k) / (1 - k)
        m = (1 - g - k) / (1 - k)
        y = (1 - b - k) / (1 - k)
    cmyk_values = f"{c:.2f} {m:.2f} {y:.2f} {k:.2f}"

    cmyk_reverse_rgb = cmyk_ghostscript_rgb(cmyk_values)
    return rgb_values, cmyk_values, safe_rgb, cmyk_reverse_rgb


COLOR_PATTERN = r'([\d.]+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+(?:[kK]|cmyk|setcmykcolor)|[\d.]+\s+[\d.]+\s+[\d.]+\s+(?:rg|RG|setrgbcolor))'


def _is_rgb_op(op):
    return op in ('rg', 'RG', 'setrgbcolor')


def _build_replacement(color_str, rgb_values, cmyk_values):
    """
    根据原始颜色指令的操作符，构造替换字符串
    返回: (new_cmd, is_rgb_mode)
    """
    parts = color_str.strip().split()
    op = parts[-1]
    if _is_rgb_op(op):
        return f"{rgb_values} {op}", True
    else:
        return f"{cmyk_values} {op}", False


def _inject_bg_rect(eps_content, bb_x1, bb_y1, bb_x2, bb_y2, rgb_values, cmyk_values):
    """
    在绘图内容起始处注入一个覆盖整个 BoundingBox 的安全色矩形。
    适用于没有显式背景填充块的 EPS（背景为 Ghostscript 默认白色）。
    返回: (new_content, is_rgb_mode)
    """
    # 确定注入位置：优先在结构标记之后，fallback 到 %%Page: 或 %%EndComments 之后
    for marker in ('%%EndPageSetup', '%%EndSetup', '%%EndProlog', '%%Page:', '%%EndComments'):
        idx = eps_content.find(marker)
        if idx >= 0:
            inject_pos = eps_content.index('\n', idx) + 1
            break
    else:
        return eps_content, False

    # 检测文件使用的颜色空间，优先匹配已有指令的类型
    drawing = eps_content[inject_pos:]
    if re.search(r'\bsetrgbcolor\b|\brg\b|\bRG\b', drawing):
        color_cmd = f"{rgb_values} setrgbcolor"
        is_rgb = True
    else:
        color_cmd = f"{cmyk_values} setcmykcolor"
        is_rgb = False

    bg_rect = (
        f"gsave\n"
        f"{color_cmd}\n"
        f"newpath\n"
        f"{bb_x1:.4f} {bb_y1:.4f} moveto\n"
        f"{bb_x2:.4f} {bb_y1:.4f} lineto\n"
        f"{bb_x2:.4f} {bb_y2:.4f} lineto\n"
        f"{bb_x1:.4f} {bb_y2:.4f} lineto\n"
        f"closepath fill\n"
        f"grestore\n"
    )

    new_content = eps_content[:inject_pos] + bg_rect + eps_content[inject_pos:]
    return new_content, is_rgb


def replace_bg_color_of_eps(eps_content, rgb_values, cmyk_values):
    """
    在 EPS 源码中找到背景色并替换为安全色
    优先通过 CorelDRAW Object 结构精确定位，fallback 到第一个颜色指令
    返回: (new_content, is_rgb_mode)
    """
    # 解析 BoundingBox
    bb = re.search(r'%%BoundingBox:\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)', eps_content)
    if not bb:
        return eps_content, False

    bb_x1, bb_y1, bb_x2, bb_y2 = [float(x) for x in bb.groups()]
    bb_area = (bb_x2 - bb_x1) * (bb_y2 - bb_y1)

    # 尝试通过 Object 结构定位背景
    bg_color_match = None
    if bb_area > 0 and '@rax %Note: Object' in eps_content:
        obj_pattern = r'@rax %Note: Object\s*\n([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+@E(.*?)\nF\s*\n'
        objects = list(re.finditer(obj_pattern, eps_content, re.DOTALL))

        candidates = []
        for obj in objects:
            ox1, oy1, ox2, oy2 = [float(x) for x in obj.groups()[:4]]
            obj_area = (ox2 - ox1) * (oy2 - oy1)
            if obj_area == 0:
                continue
            # 计算 IoU
            inter_x = max(0, min(bb_x2, ox2) - max(bb_x1, ox1))
            inter_y = max(0, min(bb_y2, oy2) - max(bb_y1, oy1))
            inter_area = inter_x * inter_y
            union_area = bb_area + obj_area - inter_area
            iou = inter_area / union_area if union_area > 0 else 0
            if iou < 0.8:
                continue

            # 计算 /$fm 到块结尾的行数
            block_body = obj.group(5)
            fm_idx = block_body.find('/$fm')
            if fm_idx >= 0:
                line_count = len(block_body[fm_idx:].strip().split('\n'))
            else:
                line_count = len(block_body.strip().split('\n'))
            if line_count < 4 or line_count > 30:
                continue

            # 提取颜色指令（在整个 Object 块中搜索）
            cm = re.search(COLOR_PATTERN, block_body)
            if cm:
                # 记录颜色在 eps_content 中的绝对位置
                abs_start = obj.start(5) + cm.start()
                abs_end = obj.start(5) + cm.end()
                candidates.append((line_count, cm.group(1), abs_start, abs_end))

        if candidates:
            if len(candidates) == 1:
                bg_color_match = candidates[0]
            else:
                candidates.sort(key=lambda x: x[0])
                bg_color_match = candidates[0]

    # 如果通过 Object 找到了背景色，直接替换
    if bg_color_match:
        _, color_str, abs_start, abs_end = bg_color_match
        new_cmd, is_rgb = _build_replacement(color_str, rgb_values, cmyk_values)
        new_content = eps_content[:abs_start] + new_cmd + eps_content[abs_end:]
        return new_content, is_rgb

    # 通过行扫描查找填充块，避免 DOTALL 正则在大文件上的灾难性回溯
    # 策略：找到所有 fill 行，向前回溯提取颜色和路径
    fill_re = re.compile(r'^\s*(?:fill|eofill)\s*$|^f$', re.MULTILINE)
    color_re = re.compile(COLOR_PATTERN)
    coord_re = re.compile(r'([\d.]+)\s+([\d.]+)\s+(?:moveto|lineto|curveto|mo|li|cv|m|L|c)\b')
    curve_re = re.compile(r'\b(?:curveto|cv)\b|[\d.]+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+c\b')

    # 确定搜索起点（跳过 prolog/setup 定义）
    search_start = 0
    for marker in ('%%EndPageSetup', '%%EndSetup', '%%EndProlog'):
        idx = eps_content.find(marker)
        if idx >= 0:
            search_start = eps_content.index('\n', idx) + 1
            break

    best_color_str = None
    best_color_start = 0
    best_color_end = 0
    best_area = 0

    for fill_m in fill_re.finditer(eps_content, search_start):
        # 从 fill 位置向前回溯最多 50 行，查找颜色和路径
        block_end = fill_m.start()
        block_start = max(search_start, eps_content.rfind('\n', 0, max(0, block_end - 3000)) + 1)
        block = eps_content[block_start:block_end]
        lines = block.split('\n')
        # 最多看最后 50 行，并修正 block_start 偏移
        if len(lines) > 50:
            skipped_text = '\n'.join(lines[:-50]) + '\n'
            block_start += len(skipped_text)
            lines = lines[-50:]

        # 在这个块中找颜色指令和路径坐标
        block_text = '\n'.join(lines)
        cm = color_re.search(block_text)
        if not cm:
            continue

        # 跳过含曲线的路径（非矩形）
        if curve_re.search(block_text):
            continue

        coords = coord_re.findall(block_text)
        if len(coords) < 3:
            continue

        xs = [float(c[0]) for c in coords]
        ys = [float(c[1]) for c in coords]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        if area > best_area:
            best_area = area
            best_color_str = cm.group(1)
            # 计算颜色在 eps_content 中的绝对位置
            best_color_start = block_start + block_text.index(cm.group(0)) + cm.start(1) - cm.start(0)
            best_color_end = best_color_start + len(cm.group(1))

    if best_color_str and bb_area > 0 and best_area / bb_area >= 0.5:
        new_cmd, is_rgb = _build_replacement(best_color_str, rgb_values, cmyk_values)
        new_content = eps_content[:best_color_start] + new_cmd + eps_content[best_color_end:]
        return new_content, is_rgb

    # Fallback: 没有找到显式背景填充块，注入一个安全色背景矩形
    # 适用于背景为隐式白色（Ghostscript 默认页面色）的文件
    return _inject_bg_rect(eps_content, bb_x1, bb_y1, bb_x2, bb_y2,
                           rgb_values, cmyk_values)


def load_eps(eps_path):
    """加载 EPS 并去除背景，返回 RGBA 的 PIL Image"""
    eps_content = read_eps_content(eps_path)

    # 找安全色
    rgb_values, cmyk_values, safe_rgb_tuple, safe_rgb_tuple_reverse = find_unused_color_for_eps(eps_content)

    # 替换背景色
    new_content, is_rgb = replace_bg_color_of_eps(eps_content, rgb_values, cmyk_values)

    # 渲染
    eps_io = io.BytesIO(new_content.encode('latin-1'))
    with Image.open(eps_io) as img:
        max_dim = max(img.size)
        scale = (512 // max_dim + 1) if max_dim < 512 else 1
        img.load(scale=scale)
        arr = np.array(img.convert("RGBA"))

    # 根据安全色提取背景 mask
    if is_rgb:
        target = np.array(safe_rgb_tuple)
    else:
        target = np.array(safe_rgb_tuple_reverse)

    dist = ((arr[:, :, :3].astype(float) - target.astype(float)) ** 2).sum(axis=2)
    mask = dist < dist.min() + 5
    arr[mask, :] = 0

    # 对 BoundingBox 不从 (0,0) 开始的文件，GS 会在 BB 外渲染白色填充
    # 从四角 flood-fill 清除残留的白色边缘
    still_opaque = arr[:, :, 3] > 0
    white_like = np.all(arr[:, :, :3] > 240, axis=2)
    edge_white = still_opaque & white_like
    if edge_white.any():
        from scipy.ndimage import label
        labeled, _ = label(edge_white)
        # 只清除与图像边缘相连的白色连通区域
        edge_labels = set()
        edge_labels.update(labeled[0, :][labeled[0, :] > 0])
        edge_labels.update(labeled[-1, :][labeled[-1, :] > 0])
        edge_labels.update(labeled[:, 0][labeled[:, 0] > 0])
        edge_labels.update(labeled[:, -1][labeled[:, -1] > 0])
        for lbl in edge_labels:
            arr[labeled == lbl, :] = 0

    return Image.fromarray(arr)


if __name__ == "__main__":
    lst = [
    'vector_logo/全球加工制造业矢量LOGO/_572.eps',
    'vector_logo/全球广告设计公司矢量标志/_0168.eps', 
    'vector_logo/全球加工制造业矢量LOGO/_003.eps',
    'vector_logo/全球加工制造业矢量LOGO/_461.eps', 
    'vector_logo/全球加工制造业矢量LOGO/_730.eps',
    'vector_logo/全球加工制造业矢量LOGO/_227.eps',
    'vector_logo/全球加工制造业矢量LOGO/_192.eps',
    ]
    # for idx in range(len(lst)):
    #     try:
    #         img = load_eps(lst[idx])
    #         img.save(f'test_{idx}.png')
    #     except Exception as e:
    #         print(f"Error processing {lst[idx]}: {e}")
    
    load_eps('vector_logo/全球加工制造业矢量LOGO/_319.eps').save('test_094.png')
    