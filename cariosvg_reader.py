import cairosvg
from PIL import Image 
from io import BytesIO 

# cairosvg 读取 svg 文件, 支持透明背景, 但只能处理 svg 文件, 不支持 pdf/ai.
def load_cairosvg(image_path)->Image.Image:
    png_data = cairosvg.svg2png(url=image_path, scale=2.0) # scale 可以调整输出分辨率，默认为1.0，过大可能会导致内存占用过高
    img = Image.open(BytesIO(png_data))
    return img  


# 下面是一些额外的工具函数，可以将 SVG 转换为 PDF 或 PNG 格式的文件
def svg2pdf(image_path, output_pdf_path):
    cairosvg.svg2pdf(url=image_path, write_to=output_pdf_path)
    
def svg2png(image_path, output_png_path):
    cairosvg.svg2png(url=image_path, write_to=output_png_path)