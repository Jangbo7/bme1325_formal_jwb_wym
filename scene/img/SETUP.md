# 依赖安装指南

## 前置条件

已安装 Python 3.7+ 和 Pillow 库（用于图像处理）。

## 检查依赖

```powershell
# 检查 Python
python --version

# 检查 Pillow
python -c "from PIL import Image; print('✓ Pillow 已安装')"
```

## 如果缺少 Pillow

### 方案 A：pip 安装（推荐）
```powershell
pip install --upgrade pillow
```

### 方案 B：conda 安装（如果用 Conda）
```powershell
conda install pillow
```

## 验证安装

运行以下命令应该看到 "✓ Pillow 已就绪"：
```powershell
python -c "from PIL import Image; print('✓ Pillow 已就绪')"
```

完成后就可以运行 `python process-assets.py` 了！
