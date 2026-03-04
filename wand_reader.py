'''
wand 不支持透明背景, 一般不要用, 除非 fitz 打不开, 可以用它来碰碰运气, 然后用颜色过滤的方式处理一下透明背景. 

brew install imagemagick
pip install wand

如果已经 brew install 了 freetype, imagemagic, 但还是在 import wand 时报如下错误：

ImportError: MagickWand shared library not found.
You probably had not installed ImageMagick library.
Try to install:
  brew install freetype imagemagick

这是因为 wand 找不到 imagemagick 的安装位置了，需要在 terminal 运行：
export MAGICK_HOME=$(brew --prefix imagemagick)
然后再在当前 terminal 运行代码
'''

from wand.image import Image as WandImage 
from PIL import Image 
from io import BytesIO 


def load_wand(image_path)->Image.Image:
    with open(image_path, "rb") as f:
        with WandImage(file=f, resolution=300) as wand_img:
            if wand_img.colorspace == 'cmyk':
                wand_img.transform_colorspace('srgb')
                
            wand_img.strip()  # 去掉所有元数据，避免 Pillow 解析 zTXt 报错
            wand_img.format = "png"
            # wand_img.save(filename='temp.png')
            wand_img = Image.open(BytesIO(wand_img.make_blob()))

    return wand_img 


if __name__ == "__main__":
    import os 
    
    os.makedirs('outputs', exist_ok=True)
    img = load_wand('test_files/sample.ai')
    img.save('outputs/sample_ai_wand.png')
