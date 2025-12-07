# Windows 11 真正可用的 HDR 校准软件
中文|[ENGLISH](https://github.com/forbxy/rwhc/blob/master/README.md)

![screenshot](https://github.com/forbxy/rwhc/blob/master/resources/ui_zh.png)

## 使用方法

1. **获取项目代码**  
   下载或 clone 本项目，进入项目根目录。

2. **安装 Python**  
   在 Windows 上安装 Python（任选其一）：
   - Microsoft Store
   - 官方网站：<https://www.python.org/downloads/windows/>

3. **安装依赖**  
   在项目根目录下执行：

   ```bash
   pip install -r requirements.txt
   ```

4. **运行程序**

   ```bash
   python app.py
   ```
   点击校准按钮开始校准

## 校色设备
目前设备驱动使用argyllcms，该驱动支持的常见设备有爱色丽全系和Datacolor  
具体可前往官网查询

## 使用说明补充

1. **使用爱色丽校色仪和罗技鼠标** 
   罗技鼠标驱动强制扫描所有设备会导致爱色丽校色仪被占用！！！ 
   先在设备管理器中将鼠标的驱动更换为 Windows 默认驱动，然后在“服务”中停止 `Logitech LampArray Service`。

2. **使用 Datacolor Spyder 校色仪**  
   点击安装驱动按钮跳转值argyll网站，下载后在usb文件夹中点击安装，然后在设备管理器中找到 Spyder 设备（位于“通用串行总线控制器”下）：
   - 右键设备选择“更新驱动”
   - 选择“浏览我的电脑以查找驱动程序”
   - 选择“让我从计算机的可用驱动程序列表中选取”
   - 从列表中选择 Argyll 驱动

3. **灰阶采样数**  
   10bit HDR 有 1024 级灰阶（R=G=B，范围 0–1023）。程序会在 1024 级灰阶中等距离采集指定数量的灰阶点，并对未测量的灰阶进行插值。  
   采集数量越多，PQ 曲线校准越精准(可能)，但耗时越长。

4. **色彩采样集**  
   程序会在所选色域内生成一个测试集，根据测试集预期 XYZ 与实测 XYZ 进行拟合得到矩阵。  
   - 如果你的屏幕在打开 HDR 后桌面色彩很鲜艳，选择 **sRGB**  
   - 如果颜色偏暗淡，选择 **sRGB + DisplayP3** 

5. **明亮模式**  
   对生成的 LUT 进行整体提升(1D LUT*1.1)，仅适合在强环境光下观看电影。

6. **预览校准结果**  
   当执行了校准后，矩阵和 LUT 会存储在内存中。勾选“预览校准结果”会生成临时 ICC 文件并加载到选中的屏幕，取消勾选则自动移除。  
   未执行校准时，加载的是理想 HDR ICC（BT.2020 色域，10000 nit，恒等矩阵和 无修正LUT）。

7. **校准**  
   生成矩阵和 LUT。

8. **测量色准**  
   测量屏幕的色准（若选中“预览校准结果”，会将当前矩阵和 LUT 临时加载到屏幕上再测量）。  
   没有深入验证这个功能的准确性

9. **保存**  
   将矩阵和 LUT 保存为 ICC 配置文件。

## 集成的外部工具

- **色彩生成器**  
  dogegen  
  <https://github.com/ledoge/dogegen>

- **校色设备驱动 / 测量工具**  
  ArgyllCMS `spotread`  
  <https://www.argyllcms.com/>  
  因为displaycal也是使用同的驱动，因此也可以参考displaycal文档

## 色度计校准说明

色度计需要不同类型屏幕对应的光皮校准文件，具体可参考：

- ArgyllCMS 文档：<https://www.argyllcms.com/doc/oeminst.html>  
- DisplayCAL 相关教程与文档

## 关于本项目的代码

作者并不是色彩科学相关职业，因此校色逻辑可能并非最佳  
如发现问题或有更好的想法，欢迎指出来

## 支持
如果你愿意支持作者买一个光度计  
USDT_ERC20:0xa7475effb3f2c5fcb618e8052fc4c45ccc9d9710  
BTC: bc1qa77v8als2f7qradmtmjjy5ad057q9yws6nanx6  

## 许可证

本项目采用 GNU Affero General Public License v3.0（AGPL-3.0）许可协议。  
详细条款请参见项目根目录中的 `LICENSE` 文件。