# Codex 图片交付技术验证

> 日期：2026-08-14
> 对应蓝图：宿主 AI 创作阶段 0
> 环境：Codex Desktop、macOS arm64、内置生图能力
> 结论：macOS 生图/编辑与 Windows x64 接管验证均通过；可以进入核心协议开发

## 验证目标

验证三个阻断问题：

1. Codex 普通生图能否稳定提供 RedBeacon 可读取的本机文件。
2. Codex 能否读取本机参考图进行编辑，并再次提供独立本机文件。
3. 两类文件能否直接通过 RedBeacon 现有图片净化边界。

## 实验一：普通生图

使用 Codex 内置生图能力生成单个红色陶瓷灯塔摆件。

提示词：

```text
Use case: product-mockup
Asset type: RedBeacon technical verification fixture
Primary request: a single matte red ceramic lighthouse figurine standing upright
Scene/backdrop: clean warm-white studio background
Style/medium: simple polished product photography
Composition/framing: centered square composition with generous padding
Lighting/mood: soft neutral studio light
Constraints: no text, no logos, no watermark, one object only
```

工具返回值包含：

- `image_url`：`data:image/png;base64,...`，本次长度 1,811,590 字符。
- `output_hint`：明确给出 Codex 自有目录中的绝对 PNG 路径。
- 本机文件：1254×1254、RGB、1,358,674 字节。
- SHA-256：`993de555e7dfb595f818268d690e93519683311ed81ffda0491587acc1745abc`。

将该文件字节交给 `redbeacon.services.image_sanitize.save_sanitized_generated_image` 后：

- 输出仍为 1254×1254、RGB PNG。
- EXIF 条目为 0，Pillow `info` 为空。
- PNG 只包含 `IHDR`、`IDAT`、`IEND`，没有 ancillary chunk。
- 净化成功，未发生缩放、裁切或有损编码。

结论：宿主结果不需要经过网络 URL，也不需要把大型 base64 写进命令行或业务 JSON；本机文件交付可用。

## 实验二：参考图编辑

把实验一图片作为本机编辑目标，要求只把陶瓷颜色由红色改为深海军蓝。

提示词：

```text
Use case: precise-object-edit
Asset type: RedBeacon reference-image editing technical verification fixture
Input images: Image 1 is the edit target
Primary request: change only the lighthouse figurine's ceramic color from matte red to matte deep navy blue
Constraints: preserve the exact lighthouse shape, proportions, openings, camera angle, centered composition, warm-white studio background, lighting, shadows, texture, and image dimensions; change only the ceramic color; no text, no logos, no watermark
```

结果：

- Codex 接受本机绝对路径作为参考图输入。
- 返回新的独立 PNG 绝对路径和 data URL。
- 编辑结果仍为 1254×1254、RGB、1,135,430 字节。
- SHA-256：`e35b2f705f2702a3ce2bb87191d8990826a06cceaa90f542801d26c33633eb55`。
- 视觉检查确认主体形状、构图和背景保持，陶瓷颜色由红色变为深海军蓝。
- RedBeacon 净化器再次成功，输出没有 EXIF、ICC、文本、时间戳或未知附加块。

结论：Codex 的本机参考图编辑链路可用于后续带货图生图适配；具体商品图仍需在测试版用真实素材回归。

## 实验三：Windows x64 接管

把同一组普通生图和参考图编辑结果复制到项目的 Windows 11 ARM64 构建虚拟机，使用锁定的 Windows x64 CPython 环境运行同一验证脚本。

环境检查：

- Python 指针宽度：64 位。
- Windows 宿主报告：ARM64。
- `python.exe` PE machine：`0x8664`，确认是 x64 CPython，经系统仿真运行。
- 输入和净化输出目录包含空格。

结果：

- 两个输入 SHA-256 与 macOS 完全一致。
- 参考图与编辑图尺寸均为 1254×1254。
- 变化像素比例为 `0.999981`，确认不是原图原样返回。
- 净化输出 SHA-256 与 macOS 完全一致：`99757f8a670eda314951f8aac7e03dc861149f2b59cef5a3664aaac05e44f9f1`。
- Windows 输出同样只有 `IHDR`、`IDAT`、`IEND`，无 EXIF 或其它附加元数据。

结论：Codex 图片字节进入 RedBeacon 后的 Windows x64 接管、路径和净化行为已验证一致。

## 协议决策

基于真实返回形态，正式实现采用以下边界：

1. Codex/Skill 从生图结果中取得明确的本机输出路径。
2. Skill 把该路径写入 `redbeacon-host-result/v1` 文件，或先复制到 CLI 分配的任务收件箱。
3. CLI 不解析 `output_hint` 的自然语言，不读取聊天记录，也不接收大型内联 base64。
4. RedBeacon 根据 `generation_id`、当前通道和任务收件箱重新校验路径，读取字节后用现有净化器接管。
5. 只有净化和全部图片数量校验成功后，才允许写入审稿台。
6. 宿主工具缺失、没有本机路径、文件消失或净化失败，都视为图片能力不可用，进入已确认的平台授权/文字卡回退规则。

宿主身份和能力判断属于 Skill 运行时：CLI 不能从环境变量猜测“当前一定是 Codex”。第一版只有在宿主明确能完成文本创作，并且生图工具真实返回可读取本机文件时，才声明相应能力。

## 可重复验证工具

新增 `tools/verify_codex_image_handoff.py`：

- 接受 Codex 返回的本机图片路径。
- 拒绝符号链接、非普通文件、空文件、超限文件和非 JPG/PNG/WebP。
- 调用 RedBeacon 正式图片净化器并输出机器可读 JSON。
- 可选对照参考图，验证编辑结果尺寸是否一致、像素是否真实变化。

离线测试位于 `cli/tests/test_codex_image_handoff_spike.py`，覆盖：

- 中文和空格路径。
- EXIF/PNG 文本元数据清除。
- 参考图尺寸与像素变化检查。
- 未发生实际编辑时失败。
- 符号链接输入拒绝。

## 剩余门槛

- 用真实商品参考图验证带货多图任务，而不只验证单图颜色编辑。
- Codex Windows 宿主正式可用时，补一次“Windows 本机生图 → Windows 本机路径 → 接管”的完整宿主回归；当前已验证相同图片字节的 Windows x64 接管。
- 在 Skill 真源改造后，验证 Codex 批量逐篇调用时每个 `generation_id` 只接管自己的图片。

这些项目不阻止阶段 1～3 的核心协议开发，但在测试版交付和正式版发布前必须完成。
