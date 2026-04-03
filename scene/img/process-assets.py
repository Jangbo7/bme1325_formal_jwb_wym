"""
医院游戏素材处理工程 - Python 版本
将大头照处理成游戏可用的圆形头像（多分辨率）
"""

import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw
import argparse

# 配置
SCRIPT_DIR = Path(__file__).parent
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.gif'}

HEADSHOT_CONFIG = {
    'sizes': [64, 128, 256],
    'suffixes': ['@1x', '@2x', '@4x'],
    'quality': 85
}


def create_circle_mask(size):
    """创建圆形遮罩"""
    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse([0, 0, size - 1, size - 1], fill=255)
    return mask


def process_headshot(input_path):
    """
    处理大头照 -> 圆形头像（多分辨率）
    
    Args:
        input_path: 输入图像路径
        
    Returns:
        bool: 处理是否成功
    """
    base_name = Path(input_path).stem
    
    print(f"\n🎨 处理头像: {base_name}")
    print("─" * 50)
    
    try:
        # 打开原始图像
        img = Image.open(input_path).convert('RGBA')
        width, height = img.size
        
        # 裁剪为正方形（保留中心，优先保留脸部）
        min_dim = min(width, height)
        left = (width - min_dim) // 2
        top = (height - min_dim) // 2
        right = left + min_dim
        bottom = top + min_dim
        
        square_img = img.crop((left, top, right, bottom))
        
        processed_count = 0
        
        for i, size in enumerate(HEADSHOT_CONFIG['sizes']):
            suffix = HEADSHOT_CONFIG['suffixes'][i]
            output_name = f"{base_name}-head{suffix}.png"
            output_path = SCRIPT_DIR / output_name
            
            try:
                # 调整大小
                resized = square_img.resize((size, size), Image.Resampling.LANCZOS)
                
                # 创建空白背景（透明）
                result = Image.new('RGBA', (size, size), (0, 0, 0, 0))
                
                # 应用圆形遮罩
                mask = create_circle_mask(size)
                result.paste(resized, (0, 0), mask)
                
                # 保存
                result.save(
                    output_path,
                    'PNG',
                    optimize=False,
                    quality=HEADSHOT_CONFIG['quality']
                )
                
                print(f"   ✓ {output_name} ({size}×{size}px)")
                processed_count += 1
                
            except Exception as e:
                print(f"   ✗ 生成 {suffix} 版本失败: {e}")
        
        if processed_count > 0:
            print(f"\n✅ 成功生成 {processed_count} 个头像版本")
            return True
        
        return False
        
    except Exception as e:
        print(f"❌ 处理失败: {e}")
        return False


def find_images(directory):
    """列出目录中的所有未处理的图像文件"""
    images = []
    
    for file in Path(directory).iterdir():
        if not file.is_file():
            continue
            
        ext = file.suffix.lower()
        name = file.name
        
        # 跳过已处理的文件、隐藏文件和系统文件
        if (ext in SUPPORTED_FORMATS and 
            not name.startswith('_') and 
            not name.startswith('.') and
            '-head@' not in name and
            '-character' not in name):
            images.append(file.name)
    
    return sorted(images)


def main():
    parser = argparse.ArgumentParser(
        description='医院游戏素材处理工程',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python process-assets.py              # 处理所有图像为头像
  python process-assets.py --type all   # 全量处理
        """
    )
    parser.add_argument(
        '--type',
        default='headshot',
        choices=['headshot', 'all'],
        help='处理类型（默认: headshot）'
    )
    
    args = parser.parse_args()
    
    print("\n" + "═" * 50)
    print("🎮 医院游戏素材处理工程 (Python 版)")
    print("═" * 50 + "\n")
    
    images = find_images(SCRIPT_DIR)
    
    if not images:
        print("⚠️  未找到图像文件\n")
        print("📋 步骤：")
        print("   1. 将你的大头照放在 img/ 目录中")
        print(f"   2. 支持格式: {', '.join(SUPPORTED_FORMATS)}")
        print("   3. 运行: python process-assets.py\n")
        print("📝 示例：")
        print("   · 将 photo.jpg 放在 img/ 目录")
        print("   · 运行 python process-assets.py")
        print("   · 得到 photo-head@1x.png 等文件\n")
        print("─" * 50 + "\n")
        return
    
    print(f"发现 {len(images)} 个图像文件:")
    for i, img in enumerate(images, 1):
        print(f"   {i}. {img}")
    print()
    
    success_count = 0
    error_count = 0
    
    for image in images:
        input_path = SCRIPT_DIR / image
        
        if args.type in ['headshot', 'all']:
            if process_headshot(input_path):
                success_count += 1
            else:
                error_count += 1
    
    print("\n" + "═" * 50)
    print("📊 处理完成")
    print("─" * 50)
    print(f"✅ 成功: {success_count} 个")
    if error_count > 0:
        print(f"❌ 失败: {error_count} 个")
    print(f"📍 输出位置: {SCRIPT_DIR}")
    print("\n💡 后续步骤:")
    print("   1. 检查生成的 -head@2x.png 文件")
    print("   2. 仔细阅读 img/README.md")
    print("   3. 按说明集成到游戏代码")
    print("\n" + "═" * 50 + "\n")


if __name__ == '__main__':
    main()
