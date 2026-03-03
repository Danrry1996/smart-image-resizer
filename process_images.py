import os
import shutil
from PIL import Image
import math

# 配置
INPUT_DIR = os.getcwd()
OUTPUT_DIR = os.path.join(INPUT_DIR, 'processed_images')
MAX_SIZE_MB = 5 * 1024 * 1024  # 5MB

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def save_image(img, path, quality=95):
    """保存图片并确保文件大小小于5MB"""
    # 转换为RGB模式，防止保存JPEG出错
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    # 初始保存
    img.save(path, 'JPEG', quality=quality)
    
    # 检查大小
    while os.path.getsize(path) > MAX_SIZE_MB and quality > 10:
        quality -= 5
        img.save(path, 'JPEG', quality=quality)
    
    if os.path.getsize(path) > MAX_SIZE_MB:
        print(f"Warning: Could not compress {path} to under 5MB. Current size: {os.path.getsize(path)/1024/1024:.2f}MB")

def process_main_image(img_path, output_path):
    try:
        with Image.open(img_path) as img:
            # 处理透明背景（如果有）
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                alpha = img.convert('RGBA').split()[-1]
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=alpha)
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            w, h = img.size
            
            # 目标尺寸：800x800 至 1800x1800
            # 策略：取最长边，限制在 800-1800 之间
            max_dim = max(w, h)
            target_size = max(800, min(1800, max_dim))
            
            # 创建白色背景的正方形画布
            new_img = Image.new('RGB', (target_size, target_size), (255, 255, 255))
            
            # 计算缩放比例
            ratio = min(target_size / w, target_size / h)
            new_w = int(w * ratio)
            new_h = int(h * ratio)
            
            # 缩放原图
            resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            # 居中粘贴
            paste_x = (target_size - new_w) // 2
            paste_y = (target_size - new_h) // 2
            new_img.paste(resized_img, (paste_x, paste_y))
            
            save_image(new_img, output_path)
            print(f"Processed Main Image: {output_path} ({target_size}x{target_size})")
            
    except Exception as e:
        print(f"Error processing main image {img_path}: {e}")

def process_detail_image(img_path, output_path_base):
    try:
        with Image.open(img_path) as img:
            # 处理透明背景（如果有）
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                alpha = img.convert('RGBA').split()[-1]
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=alpha)
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            w, h = img.size
            
            # 宽度限制：800 - 1800
            target_w = w
            if w < 800:
                target_w = 800
            elif w > 1800:
                target_w = 1800
            
            # 如果宽度需要调整
            if target_w != w:
                ratio = target_w / w
                target_h = int(h * ratio)
                img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            
            # 高度限制：10000
            # 如果高度超过 10000，切片
            current_h = img.height
            if current_h > 10000:
                num_slices = math.ceil(current_h / 10000)
                slice_height = math.ceil(current_h / num_slices) # 尽量均匀切分，避免最后一张太短
                
                # 如果切分后单张高度超过10000（理论上不会发生，除非原始非常大），可以强制最大10000
                if slice_height > 10000:
                    slice_height = 10000
                    num_slices = math.ceil(current_h / slice_height)

                base_name, ext = os.path.splitext(output_path_base)
                
                for i in range(num_slices):
                    top = i * slice_height
                    bottom = min((i + 1) * slice_height, current_h)
                    
                    crop_img = img.crop((0, top, img.width, bottom))
                    slice_path = f"{base_name}_{i}{ext}"
                    save_image(crop_img, slice_path)
                    print(f"Processed Detail Slice: {slice_path}")
            else:
                # 不需要切片，直接保存
                save_image(img, output_path_base)
                print(f"Processed Detail Image: {output_path_base}")
                
    except Exception as e:
        print(f"Error processing detail image {img_path}: {e}")

def main():
    # if os.path.exists(OUTPUT_DIR):
    #    shutil.rmtree(OUTPUT_DIR)
    ensure_dir(OUTPUT_DIR)
    
    total_files = 0
    processed_files = 0

    for root, dirs, files in os.walk(INPUT_DIR):
        # 跳过输出目录
        if 'processed_images' in root:
            continue
            
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                total_files += 1
                input_path = os.path.join(root, file)
                
                # 构建输出路径
                rel_path = os.path.relpath(root, INPUT_DIR)
                output_dir = os.path.join(OUTPUT_DIR, rel_path)
                ensure_dir(output_dir)
                output_path = os.path.join(output_dir, file)
                
                # 判断类型
                if '主图' in root:
                    if os.path.exists(output_path):
                        # print(f"Skipping existing: {output_path}")
                        continue
                    process_main_image(input_path, output_path)
                    processed_files += 1
                elif '商详图' in root:
                    # 商详图可能有切片，需要特殊处理跳过逻辑
                    # 简单起见，商详图如果不切片，输出文件名和原名一致
                    # 如果切片，会有 _0, _1 后缀
                    # 这里先检查基础路径是否存在，如果存在则跳过（针对未切片情况）
                    # 对于切片情况比较复杂，稳妥起见，商详图重新处理一下也无妨，或者检查第一个切片是否存在
                    base_name, ext = os.path.splitext(output_path)
                    if os.path.exists(output_path) or os.path.exists(f"{base_name}_0{ext}"):
                         # print(f"Skipping existing: {output_path}")
                         continue

                    process_detail_image(input_path, output_path)
                    processed_files += 1
                else:
                    print(f"Skipping unknown type: {input_path}")
    
    print(f"\nProcessing complete. Processed {processed_files}/{total_files} images.")

if __name__ == "__main__":
    main()
