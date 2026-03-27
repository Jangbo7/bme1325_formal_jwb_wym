# 游戏素材处理工程

这个目录专门用于预处理游戏素材（大头照等）并生成适合游戏使用的格式。

## 快速开始（3步）

### 1️⃣ 放置素材
将你的大头照放在 `img/` 目录中。

**支持格式**：JPG, JPEG, PNG, WebP, BMP, GIF, TIFF

### 2️⃣ 运行处理（Python）
在 PowerShell 中运行：
```powershell
cd img
python process-assets.py
```

你也可以在 `img` 目录右键选择 `"在终端中打开"` 或在 VS Code 中打开集成终端。

### 3️⃣ 获取输出
处理完成后，在 `img/` 目录会生成以下文件：

```
photo-head@1x.png     (64×64)   - 小地图
photo-head@2x.png     (128×128) - 游戏标准（推荐）
photo-head@4x.png     (256×256) - 高清版
```

## 输出文件说明

### 头像系列的三个版本

| 文件 | 尺寸 | 用途 |
|------|------|------|
| `*-head@1x.png` | 64×64 | 小地图、远景 |
| `*-head@2x.png` | 128×128 | **游戏主显示（推荐）** |
| `*-head@4x.png` | 256×256 | 高清缩放 |

### 处理特性
✅ **自动圆形化** - 符合游戏头部几何  
✅ **多分辨率** - 支持不同显示需求  
✅ **透明背景** - PNG 格式可无缝合成  
✅ **面部优化** - 自动检测并保留面部区域  

## 在游戏中使用

### 🎯 推荐方案：修改 render.js

找到 `drawPlayer` 函数（约第 164 行），进行以下修改：

**顶部添加全局加载：**
```javascript
// 在 render.js 最顶部添加（在导入后）
window.playerHeadImage = new Image();
window.playerHeadImage.onload = () => {
  console.log('✓ 玩家头像已加载');
};
window.playerHeadImage.onerror = () => {
  console.warn('⚠ 玩家头像加载失败，使用默认样式');
};
window.playerHeadImage.src = './img/photo-head@2x.png';  // 改成你的文件名
```

**修改 drawPlayer 函数中的头部绘制部分：**

原代码（约第 189-192 行）：
```javascript
  ctx.fillStyle = palette.playerHead;
  ctx.beginPath();
  ctx.arc(top.x, top.y - 4, 8, 0, Math.PI * 2);
  ctx.fill();
```

替换为：
```javascript
  // 使用图像头像，降级使用颜色填充
  if (window.playerHeadImage?.complete) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(top.x, top.y - 4, 8, 0, Math.PI * 2);
    ctx.clip();
    ctx.drawImage(window.playerHeadImage, top.x - 8, top.y - 12, 16, 16);
    ctx.restore();
  } else {
    // 图像未加载时使用默认颜色
    ctx.fillStyle = palette.playerHead;
    ctx.beginPath();
    ctx.arc(top.x, top.y - 4, 8, 0, Math.PI * 2);
    ctx.fill();
  }
```

### 📝 完整的 drawPlayer 函数示例

```javascript
export function drawPlayer(ctx, player, camera, canvas) {
  const base = project(player.x, player.y, 0, camera, canvas);
  const top = project(player.x, player.y, 32, camera, canvas);

  // 阴影
  ctx.fillStyle = palette.shadow;
  ctx.beginPath();
  ctx.ellipse(base.x, base.y + 10, 18, 9, 0, 0, Math.PI * 2);
  ctx.fill();

  // 腿部
  ctx.strokeStyle = palette.playerLeg;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(base.x - 5, base.y + 2);
  ctx.lineTo(base.x - 7, base.y + 18);
  ctx.moveTo(base.x + 5, base.y + 2);
  ctx.lineTo(base.x + 7, base.y + 18);
  ctx.stroke();

  // 身体
  ctx.strokeStyle = palette.playerBody;
  ctx.lineWidth = 9;
  ctx.beginPath();
  ctx.moveTo(base.x, base.y - 2);
  ctx.lineTo(top.x, top.y + 6);
  ctx.stroke();

  // 头部（用图像替换）
  if (window.playerHeadImage?.complete) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(top.x, top.y - 4, 8, 0, Math.PI * 2);
    ctx.clip();
    ctx.drawImage(window.playerHeadImage, top.x - 8, top.y - 12, 16, 16);
    ctx.restore();
  } else {
    ctx.fillStyle = palette.playerHead;
    ctx.beginPath();
    ctx.arc(top.x, top.y - 4, 8, 0, Math.PI * 2);
    ctx.fill();
  }
}
```

### 或者：在 index.html 中预加载

在 `<head>` 中添加：
```html
<script>
  const playerHeadImage = new Image();
  playerHeadImage.crossOrigin = 'anonymous';
  playerHeadImage.src = './img/photo-head@2x.png';
  window.playerHeadImage = playerHeadImage;
</script>
```

## 故障排除

### ❓ 生成的头像看起来很模糊？

**原因**：游戏中缩放到 16×16 显示时自然会模糊。

**解决方案**：
- 确保是使用 `@2x` 或 `@4x` 版本
- 在 Canvas 绘制时尝试启用抗锯齿：
  ```javascript
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ```

### ❓ 头像没有显示，还是用的原始颜色？

**原因**：可能是文件路径错误或 CORS 问题。

**调试步骤**：
```javascript
// 在浏览器控制台检查
console.log(window.playerHeadImage)
console.log(window.playerHeadImage?.src)
console.log(window.playerHeadImage?.complete)
```

### ❓ 图像的颜色和游戏风格不搭？

**原因**：霓虹紫色调需要色彩调和。

**解决方案**：在加载后应用滤镜
```javascript
ctx.filter = 'saturate(1.2) hue-rotate(15deg)';
ctx.drawImage(...);
ctx.filter = 'none';
```

或编辑原始照片，调整色温。

## 进阶定制

### 修改头像大小

编辑 `process-assets.js` 中的 `size` 数组：
```javascript
const sizes = [32, 64, 128, 256];      // 添加或修改尺寸
const suffixes = ['@0.5x', '@1x', '@2x', '@4x'];  // 对应后缀
```

### 支持多个角色头像

放置多个素材，例如：
```
img/
├── player-headshot.jpg
├── doctor-photo.jpg
└── nurse-photo.jpg
```

运行处理后得到：
```
img/
├── player-headshot-head@2x.png
├── doctor-photo-head@2x.png
└── nurse-photo-head@2x.png
```

在游戏中分别加载：
```javascript
window.playerHeadImage.src = './img/player-headshot-head@2x.png';
window.doctorHeadImage = new Image();
window.doctorHeadImage.src = './img/doctor-photo-head@2x.png';
```

## 技术细节

- **图像库**：Sharp（高性能 Node.js 图像处理）
- **裁剪策略**：中心正方形裁剪以保留脸部
- **遮罩方式**：SVG 圆形遮罩混合模式
- **输出格式**：PNG with transparency
- **色彩空间**：sRGB

## 常见问题

**Q: 能否支持 GIF 或视频帧？**  
A: 当前只支持静态图像。可修改 `process-assets.js` 添加 GIF 逐帧处理。

**Q: 处理时间很长？**  
A: Sharp 在首次使用时会编译 libvips。后续调用会快得多。

**Q: 如何自动化这个流程到构建中？**  
A: 在项目的主 `package.json` 中添加：
```json
"scripts": {
  "process-assets": "cd img && npm install && npm run process"
}
```

## 许可证

按照项目主许可证。
