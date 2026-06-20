import sharp from 'sharp';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const inputDir = __dirname;
const outputDir = __dirname;

// 配置
const config = {
  headshot: {
    sizes: [64, 128, 256],
    suffixes: ['@1x', '@2x', '@4x'],
    quality: 85,
    format: 'png'
  }
};

/**
 * 创建圆形 SVG 遮罩
 */
function createCircleMask(size) {
  return `
    <svg width="${size}" height="${size}" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <mask id="circle">
          <rect width="${size}" height="${size}" fill="white"/>
          <circle cx="${size/2}" cy="${size/2}" r="${size/2 - 1}" fill="black"/>
        </mask>
      </defs>
      <circle cx="${size/2}" cy="${size/2}" r="${size/2 - 1}" fill="white" mask="url(#circle)"/>
    </svg>
  `;
}

/**
 * 生成游戏可用的头像（多分辨率）
 */
async function generateHeadshotVariants(inputPath) {
  const baseName = path.basename(inputPath, path.extname(inputPath));
  const sizes = config.headshot.sizes;
  const suffixes = config.headshot.suffixes;

  try {
    console.log(`\n🎨 处理头像: ${baseName}`);
    console.log(`${'─'.repeat(50)}`);

    // 首先获取图像元数据并做初步处理
    const metadata = await sharp(inputPath).metadata();
    const minDim = Math.min(metadata.width || 0, metadata.height || 0);

    if (minDim === 0) {
      console.error(`❌ 无法读取图像尺寸`);
      return false;
    }

    // 裁剪为正方形（优先裁剪中心，保留脸部）
    const crop = Math.floor((Math.max(metadata.width || 0, metadata.height || 0) - minDim) / 2);
    const squareImage = await sharp(inputPath)
      .extract({ 
        left: crop, 
        top: crop, 
        width: minDim, 
        height: minDim 
      })
      .toBuffer();

    let processed = 0;

    for (let i = 0; i < sizes.length; i++) {
      const size = sizes[i];
      const suffix = suffixes[i];
      const outputPath = path.join(outputDir, `${baseName}-head${suffix}.png`);

      try {
        // 调整大小并应用圆形遮罩
        await sharp(squareImage)
          .resize(size, size, { fit: 'cover', position: 'center' })
          .composite([
            {
              input: Buffer.from(createCircleMask(size)),
              blend: 'dest-in'
            }
          ])
          .png({ quality: config.headshot.quality })
          .toFile(outputPath);

        console.log(`   ✓ ${baseName}-head${suffix}.png (${size}×${size}px)`);
        processed++;
      } catch (error) {
        console.error(`   ✗ 生成 ${suffix} 版本失败: ${error.message}`);
      }
    }

    if (processed > 0) {
      console.log(`\n✅ 成功生成 ${processed} 个头像版本`);
      return true;
    }
    return false;

  } catch (error) {
    console.error(`❌ 工 处理失败: ${error.message}`);
    return false;
  }
}

/**
 * 列出输入目录中的所有图像
 */
function findImages(dir) {
  const supportedFormats = ['.jpg', '.jpeg', '.png', '.webp', '.bmp'];

  try {
    const files = fs.readdirSync(dir);
    return files.filter(file => {
      const ext = path.extname(file).toLowerCase();
      const name = path.basename(file);
      return (
        supportedFormats.includes(ext) &&
        !name.startsWith('_') &&
        !name.startsWith('.') &&
        !name.includes('-head@') &&
        !name.includes('-character')
      );
    });
  } catch (error) {
    return [];
  }
}

/**
 * 主处理函数
 */
async function main() {
  const args = process.argv.slice(2);
  const typeArg = args.find(a => a.startsWith('--type'))?.split('=')[1] || 'headshot';

  console.log(`\n${'═'.repeat(50)}`);
  console.log(`🎮 医院游戏素材处理工程`);
  console.log(`═'.repeat(50)}\n`);

  const images = findImages(inputDir);

  if (images.length === 0) {
    console.log(`⚠️  未找到图像文件\n`);
    console.log(`📋 步骤：`);
    console.log(`   1. 将你的大头照放在 img/ 目录中`);
    console.log(`   2. 支持格式: JPG, PNG, WebP, BMP`);
    console.log(`   3. 运行: npm run process\n`);
    console.log(`📝 示例：`);
    console.log(`   · 将 photo.jpg 放在 img/ 目录`);
    console.log(`   · 运行 npm run process`);
    console.log(`   · 得到 photo-head@1x.png 等文件\n`);
    console.log(`${'─'.repeat(50)}\n`);
    return;
  }

  console.log(`发现 ${images.length} 个图像文件:`);
  images.forEach((img, i) => console.log(`   ${i + 1}. ${img}`));
  console.log();

  let successCount = 0;
  let errorCount = 0;

  for (const image of images) {
    const inputPath = path.join(inputDir, image);

    if (typeArg === 'headshot' || typeArg === 'all') {
      const success = await generateHeadshotVariants(inputPath);
      if (success) successCount++;
      else errorCount++;
    }
  }

  console.log(`\n${'═'.repeat(50)}`);
  console.log(`📊 处理完成`);
  console.log(`${'─'.repeat(50)}`);
  console.log(`✅ 成功: ${successCount} 个`);
  console.log(`❌ 失败: ${errorCount} 个`);
  console.log(`📍 输出位置: ${outputDir}`);
  console.log(`\n💡 后续步骤:`);
  console.log(`   1. 检查生成的 -head@2x.png 文件`);
  console.log(`   2. 仔细阅读 img/README.md`);
  console.log(`   3. 按说明集成到游戏代码\n`);
  console.log(`${'═'.repeat(50)}\n`);
}

main().catch(err => {
  console.error(`\n❌ 致命错误: ${err.message}\n`);
  process.exit(1);
});
