# 沃尔翻译官

让阅读，少一点打断。

![沃尔翻译官宣传图，界面示意](docs/promo.png)

轻量的桌面英汉查词工具，提供 Windows 与 macOS 版本。选中英文后，先出现小工具条；点击“查词”再展开释义。适合在网页、支持文字选择的 PDF 和常见文字软件里阅读英文。

- 浅蓝与白色的小窗，中文释义优先，补充词典和来源放在下方。
- 英式、美式独立发音按钮：优先播放已核验许可的真人录音，缓存后可离线播放；缺少时使用本地合成。
- 按义项阅读例句，词形使用中文名称、中文解释和语法说明。
- 工具条只在系统确认文字选区后显示，停留在本次选词处；取消选区后收起。偏好菜单停靠在“···”附近。
- 统一简体中文；自动朗读默认关闭，开启后会记住开关和英美口音。

## 授权核查与版本

请使用 v0.3.11 或更新版本。此次解包检查补齐了 OpenSSL 等原生运行库的许可声明，并加入发布阻断检查。代码 MIT 不覆盖第三方词库、音频或运行库；详见 [逐项核查报告](docs/LICENSE_AUDIT.md)。这是一份可追溯的许可检查，不是全球范围的零侵权保证。

## 开始使用

[下载桌面安装包](https://github.com/blueaaa333/woer-translator/releases/latest)：Windows x64 安装器、Mac Apple 芯片版或 Intel 版 DMG。安装包内置解释器和公开词库，不需另装 Python。具体限制见 [发行说明](docs/RELEASE_NOTES.md)。

**Mac 用户先看 [首次运行指南与海报](docs/MAC_FIRST_RUN.md)**：先核对 SHA-256，再按提示类型处理。DMG 内附有可离线阅读的 HTML 指南；App 第一次成功打开也会显示引导，并可从“···”菜单重新查看。终端命令是确认可信后的可选操作，不能修复真正损坏的文件，也不需要重复运行。

Windows 10/11；Mac 在 macOS 15 构建检查。Mac 是首个预览版本，尚未完成实体 Mac 上所有浏览器的人工验收。Windows 安装器未作商业签名，Mac 未作 Developer ID 签名及 Apple 公证。Mac 划词需在“系统设置 → 隐私与安全”允许辅助功能及输入监控；在“···”菜单中主动发起授权。未授权可手动或复制查询。扫描型 PDF 没有文字选区，不能直接划词。v0.3.12 起采用严格选区确认；某些应用或 PDF 不提供可靠选区状态时不会自动弹条，可手动输入或使用查询快捷键。

首次真人发音需联网，菜单可关闭并切换本地合成；作者、来源和许可可在“··· → 发音来源与许可”查看。Windows 新音色包采用 Cori High（英式）与 Kristin Medium（美式）；主动下载完成后自动启用统一合成音色，可在菜单重新开启真人录音优先。Windows 安装包可从“··· → 下载／升级英美离线语音”按需安装声音；Mac 使用系统本地英美语音，缺少某口音时会提示从系统设置下载。[Packages](https://github.com/blueaaa333/woer-translator/packages) 提供 npm 下载与校验工具，普通用户直接下载安装包即可。

自 v0.3.0 起，软件默认每天检查正式版本更新，发现新版后提醒；也可从“··· → 检查更新”手动发起或关闭自动检查。点击“下载更新”后在后台下载并校验，再点击“重启并更新”安装，保留设置、生词本和已下载的语音。**v0.2.2 及更早版本需先手动安装一次 v0.3.0，旧程序无法凭空获得更新功能。** Mac App 须先安装到 Applications，且安装位置可写；系统安全确认和权限仍由用户本人处理。

如需从源码启动，要求 Python 3.11–3.13（含 Tkinter）；Windows 还需要系统自带的 .NET Framework C# 编译器。

在项目目录的 PowerShell 中运行：

```powershell
.\run.ps1
```

第一次会建立虚拟环境、安装 OpenCC、校验并解压词库、编译取词助手。要启用英美离线发音，请先阅读 [语音依赖说明](docs/SPEECH.md)，再运行：

```powershell
.\run.ps1 -WithSpeech
```

这一步仅用于 Windows，从上游下载运行组件和两套模型，合计约 200 MB，需要网络；之后查词、合成语音均在本机完成。源码与安装包不附带这些第三方二进制和模型。Mac 源码运行：安装 requirements.txt、执行 scripts/prepare_data.py 后运行 python app.py。

保持软件运行，在支持的应用中拖选或双击英文，点击工具条中的“查词”“英”“美”或“复制”。也可主动复制单词显示工具条，或按 Windows 的 `Ctrl+Alt+D` / Mac 的 `⌘⌥D`。`×` / `Esc` 收起窗口，“··· → 退出应用”结束程序。

## 公开词库的范围

公开版使用 WordNet 3.0、Chinese Open Wordnet、Wiktionary 开放文本及少量自编复合词。词库来自多个来源，记录数与去重词数不同，具体构建统计见 [data/manifest.json](data/manifest.json)。

**公开版未打包 ECDICT、个人 PDF 提取词库或个人缓存**，因此覆盖范围和个人使用版本不完全相同。不同词的释义、音标和例句完整程度取决于来源；离线语音是合成发音，不是真人逐词录音。

## 许可证与隐私

### Code signing policy

正在申请 SignPath Foundation 的 Windows 开源签名支持，目前尚未获批，现有 Windows 安装包仍未签名。维护角色、构建来源和拟采用的人工签名审批方式见 [Code signing policy](docs/CODE_SIGNING_POLICY.md)。

原创应用代码按 [MIT](LICENSE) 开源。词库、图标和第三方依赖保留各自许可，**整个仓库不能一概当作 MIT 数据包**。请阅读 [第三方声明](THIRD_PARTY_NOTICES.md)、[来源与重建方式](SOURCES.md) 和 [发布前核查](docs/LICENSE_AUDIT.md)。

应用没有第三方私有查词接口，没有分析服务。优先真人发音开启时，会向 Commons 发送当前查询词以获取录音，可在菜单关闭。点击“来源”会在浏览器打开公开来源页面。下载依赖时会连接相应上游。

应用会在本机保存设置、生词本、合成语音缓存和错误日志。划词响应计时日志包含来源进程、窗口及事件信息，不记录查询词或网页 URL；这些本机数据不进入仓库。详见 [隐私说明](docs/PRIVACY.md)。

## 开发与检查

```powershell
python -m pip install -r requirements.txt
python scripts/prepare_data.py
python -m unittest discover -s tests -p "test_*.py"
.\build_bridge.ps1
```

应用入口为 `app.py`，Mac 集成位于 `mac_platform.py`。安装包须在目标操作系统运行 `python scripts/build_release.py` 构建，Windows 需安装 Inno Setup 6；GitHub Actions 分别使用 Windows、Mac arm64、Mac x64 环境并检查冻结后的程序，再上传 Release。原始第三方数据的完整重建方法见 `SOURCES.md`。欢迎通过 Issue 提交错误词条、来源链接及最小复现步骤，请勿提交密码、私有文件或整份本机日志。

---

Woer Translator is a compact desktop dictionary for Windows and macOS, with selection-triggered actions, Simplified Chinese definitions, usage examples, morphology explanations, and distinct UK/US speech. Original application code is MIT; third-party data and dependencies retain their own licenses. The initial macOS build is a preview without Developer ID signing or notarization.

### Edge PDF 兼容选项

若 Edge PDF 选词不弹出，可在“···”启用“Edge PDF 自动复制取词”。该功能默认关闭，启用后划词会执行一次 Ctrl+C，所选文字将写入剪贴板。仅确认产生新的有效源文字后显示工具条；不预先清空剪贴板。仅开启此项时只用于 Edge PDF；WPS、其他浏览器等 Windows 应用可启用“更多应用自动复制取词”。该选项也会把选词写入剪贴板，并会记住开关状态。
