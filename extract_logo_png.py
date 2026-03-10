import glob
import tqdm
import os
import numpy as np
from multiprocessing import Pool, TimeoutError as MPTimeoutError
from cdr_reader import load_cdr, load_cdr_basic
from eps_reader import load_eps
from seg_utils.color_filter import remove_4corner_bg

TIMEOUT = 10  # 单个文件超时秒数
NUM_WORKERS = os.cpu_count() or 4

def _process_one(args):
    """worker 函数，在子进程中执行 load_eps 并保存"""
    pth, sv_path = args
    img = load_eps(pth)
    if img is not None:
        img.save(sv_path)
    return pth, True


if __name__ == "__main__":
    total_lst = sorted(glob.glob("vector_logo/*/*.eps"))
    output_dir = "outputs_eps"
    os.makedirs(output_dir, exist_ok=True)

    # 过滤已处理的文件
    tasks = []
    for pth in total_lst:
        base_name = '_'.join(pth.split("/")[1:])
        base_name = base_name.rsplit(".", 1)[0]
        sv_path = f"{output_dir}/{base_name}.png"
        if not os.path.exists(sv_path):
            tasks.append((pth, sv_path))

    broken_files = []
    pool = Pool(processes=NUM_WORKERS)
    pending = []

    # 逐个提交异步任务
    for task in tasks:
        pending.append((task[0], pool.apply_async(_process_one, (task,))))

    for pth, async_result in tqdm.tqdm(pending, total=len(pending)):
        try:
            async_result.get(timeout=TIMEOUT)
        except MPTimeoutError:
            print(f"Timeout (>{TIMEOUT}s): {pth}")
            broken_files.append(pth)
        except Exception as e:
            print(f"Error: {pth}: {e}")
            broken_files.append(pth)

    pool.terminate()
    pool.join()

    with open("broken_eps_files.txt", "w") as f:
        for pth in broken_files:
            f.write(pth + "\n")