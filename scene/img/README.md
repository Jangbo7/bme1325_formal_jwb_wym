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
head_photo-head@1x.png (64×64)   - 默认 NPC / 头像一倍图
photo-head@2x.png     (128×128) - 游戏标准（推荐）
photo-head@4x.png     (256×256) - 高清版
```

## 输出文件说明

### 头像系列的三个版本

| 文件 | 尺寸 | 用途 |
|------|------|------|
| `head_photo-head@1x.png` | 64×64 | 默认 NPC 头像、远景 |
| `*-head@2x.png` | 128×128 | **游戏主显示（推荐）** |
| `*-head@4x.png` | 256×256 | 高清缩放 |

### 处理特性
✅ **自动圆形化** - 符合游戏头部几何  
✅ **多分辨率** - 支持不同显示需求  
✅ **透明背景** - PNG 格式可无缝合成  
✅ **面部优化** - 自动检测并保留面部区域  

## 在前端中使用

当前 scene 会在 `scene/core/bootstrap.js` 中预加载 `head_photo-head@1x.png` 作为默认头像资源，并在固定 NPC、任务板和病历卡模块中复用。若你重新生成资源：

1. 保持产物文件名和前端预加载路径一致。
2. 如果你要改命名规则，顺手更新 `scene/core/bootstrap.js` 和对应的 NPC / UI 模块。
3. `@2x` 和 `@4x` 版本适合更清晰的缩放显示，`@1x` 版本更适合默认占位。

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
