'''
一部分 logo 图像素材是由不同方形色块拼起来的，每个色块中对应一个 logo
本代码通过颜色直方图，提取靠前的色块颜色，然后计算每个颜色的 mask，再根据 mask 
的连通域，分割出不同的 logo 区域（有可能不相邻的两个 logo 具有同样的背景颜色）。

'''
import cv2
import numpy as np
from PIL import Image
from collections import Counter
from skimage.morphology import remove_small_objects

def is_inside(box1, box2):
    """判断 box1 是否在 box2 内部 (x, y, w, h)"""
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2
    return x1 >= x2 and y1 >= y2 and (x1 + w1) <= (x2 + w2) and (y1 + h1) <= (y2 + h2)

def filter_nested_bboxes(all_bboxes):
    """过滤掉嵌套在其它 BBox 内部的小 Box"""
    all_bboxes.sort(key=lambda x: x[0][2] * x[0][3], reverse=True)
    
    keep = []
    for i, (box_i, color_i) in enumerate(all_bboxes):
        is_nested = False
        for j, (box_j, color_j) in enumerate(keep):
            if is_inside(box_i, box_j):
                is_nested = True
                break
        if not is_nested:
            keep.append((box_i, color_i))
    return keep

def extract_logos_refined(pth):
    pil_img = Image.open(pth) 
    w, h = pil_img.size 
    if max(w, h) < 5000: 
        scale = 5000//max(w, h) + 1 
        pil_img.load(scale=scale)
    if max(w, h) > 5000:
        scale = 5000 / max(w, h)
        pil_img = pil_img.resize((int(w*scale), int(h*scale)), resample=Image.LANCZOS) 
        
    img_rgba = np.array(pil_img.convert("RGBA"))
    img_bgr = cv2.cvtColor(img_rgba, cv2.COLOR_RGBA2BGR)
    img_h, img_w = img_bgr.shape[:2]
    total_area = img_h * img_w
    area_threshold = total_area / 64 
    
    pixels = img_bgr.reshape(-1, 3)
    pixel_counts = Counter(map(tuple, pixels))
    sorted_colors = pixel_counts.most_common()
    
    raw_bboxes = []
    
    for color, count in sorted_colors:
        if count < area_threshold:
            break
        
        lower = np.array([max(0, c - 3) for c in color])
        upper = np.array([min(255, c + 3) for c in color])
        mask = cv2.inRange(img_bgr, lower, upper)
        mask = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
        
        # 内缩 10 个像素，防止某色块边缘颜色因未知原因变成全图的边缘
        mask[0:10, :] = 0
        mask[-10:, :] = 0
        mask[:, 0:10] = 0
        mask[:, -10:] = 0
        
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
        
        for i in range(1, num_labels):
            x, y, w, h, area = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP], \
                                stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT], \
                                stats[i, cv2.CC_STAT_AREA]
            
            if area > area_threshold / 2:
                raw_bboxes.append(((x, y, w, h), color))
                
    filtered_bboxes = filter_nested_bboxes(raw_bboxes)
                
    # 4. 提取与去底
    results = []
    margin = 2 # 绕着边缘 crop 一圈，防止因为 bbox 坐标取整，切到相邻色块的边缘
    for (x, y, w, h), color in filtered_bboxes:
        roi_bgr = img_bgr[y:y+h, x:x+w]
        if h > 2 * margin and w > 2 * margin:
            roi_bgr = roi_bgr[margin:-margin, margin:-margin]
            
        lower = np.array([max(0, c - 3) for c in color])
        upper = np.array([min(255, c + 3) for c in color])
        mask = cv2.inRange(roi_bgr, lower, upper)
        
        roi_rgb = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2RGB)
        alpha = 255 - mask
        alpha = remove_small_objects(alpha.astype(bool), min_size=100, connectivity=8).astype(np.uint8) * 255
        roi_rgba = np.dstack((roi_rgb, alpha))
        final_pil = Image.fromarray(roi_rgba)
        w, h = final_pil.size
        tight_bbox = final_pil.getbbox()
        pad = min(h, w) // 20 
        x0, y0, x1, y1 = tight_bbox 
        tight_bbox = (max(0, x0-pad), max(0, y0-pad), min(w, x1+pad), min(h, y1+pad))
        if tight_bbox:
            final_pil = final_pil.crop(tight_bbox)
        
        w, h = final_pil.size 
        if max(w, h) > 512:
            scale = 512 / max(w, h)
            final_pil = final_pil.resize((int(w*scale), int(h*scale)), resample=Image.LANCZOS)
            
        results.append(final_pil)
        
    return results

# for idx, box in enumerate(raw_bboxes):
#     x, y, w, h = box[0]
#     patch = mask[y:y+h, x:x+w]
#     cv2.imwrite(f'patch_{idx}.png', patch)


if __name__ == "__main__":
    import glob 
    import tqdm 
    import os 
    
    os.makedirs('FotoliaColorBlock', exist_ok=True)
    # pth = '/Users/yxn/Documents/LOGO标志/LOGO1500031/Fotolia_59983755_Subscription_V/content.eps'
    # pth = '/Users/yxn/Documents/LOGO标志/LOGO1500031/Fotolia_74456131_Subscription_V/content.eps'
    
    # logos = extract_logos_refined(pth)
    lst = glob.glob('/Users/yxn/Documents/LOGO标志/LOGO1500031/*/*.eps')
            
    idx = 0
    for pth in tqdm.tqdm(lst):
        logos = extract_logos_refined(pth)
        num = pth.split('/')[-2].split('_')[1] 
        for logo in logos:
            logo.save(f"FotoliaColorBlock/Fotolia_{num}_{idx:04d}.png")
            idx += 1
         