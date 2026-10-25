沃尔翻译官 v0.2.1：补充 Mac 首次运行指南与海报、确认来源后的命令复制入口，以及首次打开引导和菜单中的常驻帮助入口。

**Mac 用户请先看完 [首次运行指南](https://github.com/blueaaa333/woer-translator/blob/main/docs/MAC_FIRST_RUN.md)**。不要把“无法验证开发者”和“文件已损坏 / 检测到恶意软件”混为一谈。确认下载与 SHA-256 后，优先使用系统“仍要打开”入口；命令仅为可选手动操作，成功后不需要重复执行。

![Mac 首次运行海报](https://raw.githubusercontent.com/blueaaa333/woer-translator/main/docs/mac-first-run-poster.png)

Release 附带可下载的 HTML 指南（文件名以 `-Mac.html` 结尾）与海报（`-Mac.png`）；DMG 内也包含这两份中文命名的说明。首次成功打开后的引导可从右上角“··· → Mac 首次运行指南”重新查看。

### 下载选择

- Windows 10 / 11（64 位）：`Windows-x64-Setup.exe`；无需安装可选择 `Portable.zip`，先完整解压再运行。
- Mac Apple 芯片：`macOS-arm64.dmg`；Intel Mac：`macOS-x64.dmg`。打开后把 App 拖入 Applications。也提供 `.pkg` 安装器。
- macOS 15 或更高版本为本次构建检查环境。较早版本尚未验证兼容性；Mac 版属首个预览版本，欢迎提供实际使用反馈。
- `SHA256SUMS.txt` 提供每个发行文件的校验值。`checks.json` 记录各平台构建后启动及词库检查结果。

### 使用说明

选中英文后显示小工具条，点击“查词”才读取选词并展开释义。也支持复制或手动输入查询；自动朗读默认关闭。

Windows 英美离线语音请在右上角“···”中主动选择下载，首次约 150 MB。安装包不附带 Piper 或模型。Mac 使用系统本地 `say`，分别选择 `en_GB` / `en_US` 口音；若系统缺少某一口音，会提示下载对应系统声音，绝不把同一个声音伪装成两种口音。

Mac 划词需在系统设置中授权辅助功能和输入监控；未授权时仍可手动或复制查询。请从菜单选择“启用 macOS 划词权限”。macOS 版没有在实体 Mac 上完成所有浏览器的划词体验验证，CI 检查不等同于完整人工验收。

### 签名与许可

Windows 安装器尚无商业代码签名；Mac App 仅作本地临时签名，没有 Apple Developer ID 签名和公证，系统可能拦截。请按系统官方说明和自己的信任判断处理，不需关闭系统整体安全保护。

原创代码 MIT；WordNet、COW、Wiktionary、Lucide、OpenCC、Python、Tcl/Tk 和 Mac 的 PyObjC 各适用其原许可。完整声明随程序资源提供，公开数据不包含个人 PDF 或 ECDICT。

### GitHub Packages

`@blueaaa333/woer-translator` 是 npm 安装包下载器，可自动选择平台并校验发行文件。普通用户直接下载上面的安装包即可，不需要 Node.js；npm 不会自动运行桌面程序。

### Code signing policy

正在申请 SignPath Foundation 的 Windows 开源签名支持，尚未获批，Windows 文件仍未签名。详见 [Code signing policy](https://github.com/blueaaa333/woer-translator/blob/main/docs/CODE_SIGNING_POLICY.md)。
