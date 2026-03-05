'''
cdr 文件是闭源文件格式，无法直接解析其内部结构来提取矢量图像内容。
因此，最可靠的方式是借助第三方软件（如 Inkscape）将 cdr 文件转换为支持透明通道的位图格式（如 PNG），
并在转换过程中自动裁剪掉多余的背景区域。这样可以确保提取出的图像仅包含前景内容，背景部分则被设置为透明。

Inkscape 是一个很强大的工具, 除了 cdr 还支持如下几种矢量图读取: ai, svg, pdf, cdr
'''
import shutil
import subprocess 
from io import BytesIO 
from PIL import Image
import numpy as np

def load_cdr_basic(input_cdr)->Image.Image:
    '''
    需要提前安装开源软件 inkscape  
    构建 Inkscape 命令行指令
    --export-type=png: 指定输出格式
    --export-area-drawing: 【核心】仅导出有内容的区域，自动切除页面多余边框
    --export-background-opacity=0: 确保背景完全透明 (4通道)
    --export-filename: 指定输出路径
    '''
    #inkscape_path = "/Applications/Inkscape.app/Contents/MacOS/inkscape"
    inkscape_path = shutil.which("inkscape")  # 自动查找 inkscape 可执行文件路径
    
    cmd = [
        inkscape_path,
        input_cdr,
        "--export-type=png",
        "--export-area-drawing", 
        "--export-background-opacity=0",
        #"--export-filename=" + output_png # 输出为文件
        "--export-filename=-" # 输出到标准输出
    ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True)
        if result.returncode == 0:
            img = Image.open(BytesIO(result.stdout))
            return img.copy() # 当 result.stdout 销毁时可能导致 img 无法访问，所以复制一份返回   
        else:
            return input_cdr
    except subprocess.CalledProcessError as e:
        return input_cdr 
    
    
def load_cdr(input_cdr, min_size_ratio=0.05, debug=False):
    """
    有的 CDR 文件中包含多个 logo, 此函数可以从 CDR 文件中提取独立的 logo.
    策略：如果一个 root 对象的子元素互不重叠, 则子元素是独立 logo, 需要拆分;
    如果 root 对象的子元素有重叠，则它们是同一个 logo 的组成部分, 保留 root 对象整体导出.

    Args:
        input_cdr: CDR 文件路径
        min_size_ratio: 最小尺寸比例 (0~1)，宽或高小于 图像短边 * ratio 的对象会被过滤掉
        debug: 是否输出调试信息
    """
    inkscape_path = "/Applications/Inkscape.app/Contents/MacOS/inkscape"

    # --- 第一步：查询所有对象的 ID 和边界框 ---
    query_cmd = [inkscape_path, "--query-all", input_cdr]

    try:
        query_result = subprocess.run(query_cmd, check=True, capture_output=True, text=True)
        lines = query_result.stdout.strip().split('\n')

        # 解析所有对象的边界框: {id: (x, y, w, h)}
        candidates = {}
        max_w, max_h = 0, 0
        for line in lines:
            parts = line.split(',')
            if len(parts) < 5:
                continue
            obj_id = parts[0]
            if obj_id.startswith(('svg', 'defs', 'namedview', 'metadata')):
                continue
            x, y, w, h = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
            candidates[obj_id] = (x, y, w, h)
            if w > max_w:
                max_w = w
            if h > max_h:
                max_h = h

        # 用所有对象的最大宽高推算画布范围
        min_size = min(max_w, max_h) * min_size_ratio

        if debug:
            print(f"[split_cdr] 最大尺寸: {max_w:.0f}x{max_h:.0f}, min_size={min_size:.1f} (ratio={min_size_ratio})")
            print(f"[split_cdr] 总对象数: {len(candidates)}")

        # --- 第二步：按尺寸过滤 ---
        # 不会删掉大尺寸元素中包含的小尺寸子元素, 大大缩减了处理的 object 数量, 从上千缩小到几十
        candidates = {oid: bbox for oid, bbox in candidates.items()
                      if bbox[2] >= min_size and bbox[3] >= min_size}

        if debug:
            print(f"[split_cdr] 尺寸过滤后: {len(candidates)}")

        # --- 第三步：构建父子关系树 ---
        def contains(outer, inner):
            ox, oy, ow, oh = outer
            ix, iy, iw, ih = inner
            tol = 1.0
            return (ix >= ox - tol and iy >= oy - tol and
                    ix + iw <= ox + ow + tol and iy + ih <= oy + oh + tol)

        ids = list(candidates.keys())
        # 为每个对象找到最小的直接父对象
        parent_of = {}
        for i, id_a in enumerate(ids):
            best_parent = None
            best_parent_area = float('inf')
            for j, id_b in enumerate(ids):
                if i == j:
                    continue
                bbox_a, bbox_b = candidates[id_a], candidates[id_b]
                area_a, area_b = bbox_a[2] * bbox_a[3], bbox_b[2] * bbox_b[3]
                if contains(bbox_b, bbox_a) and area_b > area_a:
                    if area_b < best_parent_area:
                        best_parent = id_b
                        best_parent_area = area_b
            if best_parent:
                parent_of[id_a] = best_parent

        # 构建 children 映射
        children_of = {oid: [] for oid in ids}
        for child_id, par_id in parent_of.items():
            children_of[par_id].append(child_id)

        # 找到顶层节点（没有父对象的）
        roots = [oid for oid in ids if oid not in parent_of]

        # 去重：bbox 相同的元素，保留有 children 的，去掉没有 children 的（细边框）
        bbox_groups = {}
        for oid in roots:
            key = candidates[oid]
            bbox_groups.setdefault(key, []).append(oid)
        dedup_removed = set()
        for bbox_key, group in bbox_groups.items():
            if len(group) <= 1:
                continue
            no_children = [oid for oid in group if not children_of[oid]]
            if no_children:
                dedup_removed.update(no_children)
                if debug:
                    print(f"[split_cdr] 去重: bbox={bbox_key}, 移除无子元素的 {[oid for oid in no_children]}")
        roots = [oid for oid in roots if oid not in dedup_removed]

        # --- 第四步：拆分容器组 ---
        def children_no_overlap(obj_id):
            """判断 obj_id 的直接子元素是否互不重叠"""
            kids = children_of[obj_id]
            if len(kids) <= 1:
                return False
            for a in range(len(kids)):
                for b in range(a + 1, len(kids)):
                    ba = candidates[kids[a]]
                    bb = candidates[kids[b]]
                    # 计算交集
                    ix = max(ba[0], bb[0])
                    iy = max(ba[1], bb[1])
                    ir = min(ba[0] + ba[2], bb[0] + bb[2])
                    ib = min(ba[1] + ba[3], bb[1] + bb[3])
                    if ix < ir and iy < ib:
                        return False  # 有重叠
            return True

        def collect_logos(root_id):
            """如果 root 对象的子元素互不重叠则拆分，否则作为独立 logo 保留"""
            if children_of[root_id] and children_no_overlap(root_id):
                if debug:
                    print(f"[split_cdr] 容器组: {root_id}, 子元素互不重叠, 拆分为 {len(children_of[root_id])} 个子对象")
                result = children_of[root_id]
                return result
            else:
                return [root_id]

        top_level_ids = []
        for root_id in roots:
            top_level_ids.extend(collect_logos(root_id))

        if debug:
            print(f"[split_cdr] 最终保留: {len(top_level_ids)} 个独立 logo")

        # --- 第五步：导出 ---
        logo_dict = {}
        for idx, obj_id in enumerate(top_level_ids):
            if debug:
                print(f"[split_cdr] 导出 {idx+1}/{len(top_level_ids)}: {obj_id}")
            export_cmd = [
                inkscape_path,
                input_cdr,
                "--export-type=png",
                f"--export-id={obj_id}",
                "--export-id-only",
                "--export-background-opacity=0",
                "--export-filename=-"
            ]

            export_result = subprocess.run(export_cmd, check=True, capture_output=True)

            if export_result.stdout:
                img = Image.open(BytesIO(export_result.stdout))
                arr = np.array(img.convert("RGBA"))
                # 前景像素占比 < 10% 视为空白图，跳过
                fg_ratio = (arr[:, :, 3] > 0).sum() / (arr.shape[0] * arr.shape[1])
                if fg_ratio < 0.01:
                    print(f"[split_cdr] 跳过空白: {obj_id} (前景占比 {fg_ratio:.1%})")
                    continue
                logo_dict[obj_id] = img.copy()

        return logo_dict

    except subprocess.CalledProcessError as e:
        print(f"执行失败: {e.stderr}")
        return
    
    
if __name__ == "__main__":
    import os 
    
    os.makedirs('outputs', exist_ok=True)
    img = load_cdr('test_files/sample_cdr_multiple.cdr', debug=True)
    for idx, (obj_id, logo) in enumerate(img.items()):
        logo.save(f'outputs/sample_cdr_{idx+1}_{obj_id}.png')
        
    # img_single = load_cdr_basic('test_files/sample_cdr_multiple.cdr')
    # img_single.save('outputs/sample_cdr_single.png')