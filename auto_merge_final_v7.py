import os
import sys
import glob
import re

# ================= 1. 环境配置 =================
# 您的 libvips 路径
VIPS_BIN_PATH = r'F:\pyvips\vips-dev-w64-all-8.17.3\bin'
OUTPUT_FILENAME = "Final_Result_Max.ome.tif"

print("🔧 初始化环境...")
if os.path.exists(VIPS_BIN_PATH):
    os.environ['PATH'] = VIPS_BIN_PATH + os.pathsep + os.environ['PATH']
    if hasattr(os, 'add_dll_directory'):
        try:
            os.add_dll_directory(VIPS_BIN_PATH)
        except: pass
else:
    print("❌ 路径错误，请检查 VIPS_BIN_PATH"); sys.exit(1)

try:
    import pyvips
except OSError:
    print("❌ 缺少 VC_Redist 运行库，请安装它！"); sys.exit(1)

# ================= 2. 辅助函数 =================
def get_channel_name(filename):
    base = os.path.splitext(os.path.basename(filename))[0]
    match = re.search(r'_([a-zA-Z0-9]+)_Extended$', base)
    return match.group(1) if match else base

def generate_ome_xml(width, height, channels_data, pixel_type="uint8"):
    xml = f'<?xml version="1.0" encoding="UTF-8"?><OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.openmicroscopy.org/Schemas/OME/2016-06 http://www.openmicroscopy.org/Schemas/OME/2016-06/ome.xsd">'
    xml += f'<Image ID="Image:0" Name="Merged_Max"><Pixels BigEndian="false" DimensionOrder="XYCZT" ID="Pixels:0" SizeC="{len(channels_data)}" SizeT="1" SizeX="{width}" SizeY="{height}" SizeZ="1" Type="{pixel_type}">'
    for i, (_, cname) in enumerate(channels_data):
        xml += f'<Channel ID="Channel:0:{i}" Name="{cname}" SamplesPerPixel="1"><LightPath/></Channel>'
    xml += '</Pixels></Image></OME>'
    return xml

# ================= 3. 主逻辑 =================
print("\n🔍 扫描文件...")
input_files = glob.glob("*_Extended.tif")
input_files = [f for f in input_files if "Result" not in f and "Fix" not in f]
input_files.sort()

if not input_files:
    print("❌ 未找到 *_Extended.tif 文件"); sys.exit(1)

channels_info = []
print(f"📄 准备合并 {len(input_files)} 个通道:")
for f in input_files:
    c_name = get_channel_name(f)
    channels_info.append((f, c_name))
    print(f"   [{c_name}] : {f}")

try:
    processed_imgs = []

    print("\n🚀 开始处理 (使用 Max Intensity 模式)...")

    for f in input_files:
        img = pyvips.Image.new_from_file(f, access="sequential")

        # --- 核心修改 V7 (最稳妥的写法) ---
        if img.bands > 1:
            # 1. 拆分成单通道列表: [Band0, Band1, Band2]
            split_bands = img.bandsplit()
            # 2. 用第1个通道发起比较，参数是[剩余通道]，index=-1表示取最大值
            img = split_bands[0].bandrank(split_bands[1:], index=-1)
        # --------------------------------

        # 移除强制 uchar 转换，保留原始数据格式（如 float 0-1）
        processed_imgs.append(img)

    # 尺寸检查
    base = processed_imgs[0]
    if any(i.width != base.width or i.height != base.height for i in processed_imgs):
        raise ValueError("❌ 图片尺寸不一致！")

    # 合并
    print("   正在合并通道...")
    merged = base.bandjoin(processed_imgs[1:])
    merged = merged.copy(interpretation="multiband")

    # Determine correct pixel type for XML
    vips_format_map = {
        'uchar': 'uint8',
        'char': 'int8',
        'ushort': 'uint16',
        'short': 'int16',
        'uint': 'uint32',
        'int': 'int32',
        'float': 'float',
        'double': 'double'
    }
    ome_pixel_type = vips_format_map.get(merged.format, "uint8")

    # 注入元数据
    xml_data = generate_ome_xml(merged.width, merged.height, channels_info, ome_pixel_type)
    merged.set_type(pyvips.GValue.gstr_type, "image-description", xml_data)

    # 保存
    print("   正在保存 (LZW压缩 + 金字塔)...")
    merged.write_to_file(
        OUTPUT_FILENAME,
        compression="lzw",
        tile=True, tile_width=512, tile_height=512,
        pyramid=True, bigtiff=True, subifd=True
    )

    print("\n" + "="*40)
    print(f"✅ 成功！输出文件: {OUTPUT_FILENAME}")
    print("="*40)

except Exception as e:
    print(f"\n❌ 出错: {e}")
    import traceback
    traceback.print_exc()
    input("按回车退出")
