from PIL import Image 
import numpy as np 
from skimage import morphology 
import cv2 


def remove_dark_bg_hsv(img:Image.Image, expand_pixels=1)->Image.Image:
    rgba_data = np.array(img.convert("RGBA"))
    hsv_data = np.array(img.convert("HSV"))
    
    v = hsv_data[:, :, 2]
    bg_mask = v < 50

    if expand_pixels > 0:
        bg_mask = morphology.binary_dilation(bg_mask, morphology.disk(expand_pixels))

    rgba_data[bg_mask] = 0
    return Image.fromarray(rgba_data, "RGBA")


def remove_white_bg_hsv(img:Image.Image, sensitivity=30, expand_pixels=1):    
    rgba_data = np.array(img.convert("RGBA"))
    hsv_data = np.array(img.convert("HSV"))
    
    s = hsv_data[:, :, 1]
    v = hsv_data[:, :, 2]

    white_mask = (s < sensitivity) & (v > (255 - sensitivity))
    
    if expand_pixels > 0:
        white_mask = morphology.binary_dilation(white_mask, morphology.disk(expand_pixels))

    rgba_data[white_mask] = 0
    return Image.fromarray(rgba_data, "RGBA")


def remove_4corner_bg(img:Image.Image, sensitivity=30, expand_pixels=1, edge_bg=True)->Image.Image:
    img = np.array(img.convert('RGB')) 
    h, w = img.shape[:2] 
    corners = img[[0, 0, h-1, h-1], [0, w-1, 0, w-1]]
    bg_color = np.median(corners, axis=0)
    dist = np.sqrt(np.sum((img - bg_color) ** 2, axis=2))
    bg_mask = dist < sensitivity
                                                                                                                                                                                                        
    # 加 1px 白色边框确保背景连通，只做一次 floodFill
    if edge_bg:
        bg_mask_u8 = bg_mask.astype(np.uint8) * 255
        h, w = bg_mask_u8.shape
        padded = np.full((h + 2, w + 2), 255, dtype=np.uint8)  # 全白边框
        padded[1:-1, 1:-1] = bg_mask_u8
        flood_mask = np.zeros((h + 4, w + 4), dtype=np.uint8)
        cv2.floodFill(padded, flood_mask, (0, 0), 128)
        bg_mask = padded[1:-1, 1:-1] == 128
        
    if expand_pixels > 0:
        bg_mask = morphology.binary_dilation(bg_mask, morphology.disk(expand_pixels))
    img[bg_mask] = 0
    fg_mask = (~bg_mask).astype(np.uint8) * 255
    img = np.concatenate([img, fg_mask[...,None]], axis=2)
    return Image.fromarray(img)


def remove_white_bg_hsv_refined(input_path, sensitivity=5, expand_pixels=1):
    # 防止颜色过滤过滤到前景中和背景颜色相近的区域, 用 floodFill 找到颜色 mask 中与边缘联通的区域（边缘往往是背景), 只把这部分设置为透明. 
    img = Image.open(input_path)
    W, H = img.size
    
    if max(W, H) > 1024:
        scale = 1024 / max(W, H)
        img = img.resize((int(W*scale), int(H*scale)), resample=Image.LANCZOS)

    if min(W, H) < 512:
        scale = int(512 / min(W, H)) + 1 
        img.load(scale=scale)
    
    rgba_data = np.array(img.convert("RGBA"))
    hsv_data = np.array(img.convert("HSV"))

    s = hsv_data[:, :, 1]
    v = hsv_data[:, :, 2]

    white_mask = (s < sensitivity) & (v > (255 - sensitivity))

    # 加 1px 白色边框确保背景连通，只做一次 floodFill
    white_u8 = white_mask.astype(np.uint8) * 255
    h, w = white_u8.shape
    padded = np.full((h + 2, w + 2), 255, dtype=np.uint8)  # 全白边框
    padded[1:-1, 1:-1] = white_u8
    flood_mask = np.zeros((h + 4, w + 4), dtype=np.uint8)
    cv2.floodFill(padded, flood_mask, (0, 0), 128)
    bg_mask = padded[1:-1, 1:-1] == 128

    if expand_pixels > 0:
        bg_mask = morphology.binary_dilation(bg_mask, morphology.disk(expand_pixels))

    rgba_data[bg_mask] = 0

    return Image.fromarray(rgba_data, "RGBA")
