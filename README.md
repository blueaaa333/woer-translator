# 沃尔翻译官

让阅读，少一点打断。

![沃尔翻译官宣传图，界面示意](docs/promo.png)

轻量的 Windows 桌面英汉查词工具。选中英文后，先出现小工具条；点击“查词”再展开释义。适合在网页、支持文字选择的 PDF 和常见文字软件里阅读英文。

- 浅蓝与白色的小窗，中文释义优先，补充词典和来源放在下方。
- 英式、美式两个独立的离线合成语音按钮；支持词典提供的音标。
- 按义项阅读例句，词形使用中文名称、中文解释和语法说明。
- 工具条停留在本次选词处；取消选区后收起。偏好菜单停靠在“···”附近。
- 统一简体中文；自动朗读默认关闭，可在设置里开启。

## 开始使用

这是源码发行版，当前不提供经发行审核的免安装 EXE。需要 Windows 10/11、Python 3.11–3.13（含 Tkinter）及系统自带 .NET Framework C# 编译器。已在 Windows / Python 3.13 环境检查；扫描型 PDF 没有文字选区，不能直接划词。

在项目目录的 PowerShell 中运行：

```powershell
.\run.ps1
```

第一次会建立虚拟环境、安装 OpenCC、校验并解压词库、编译取词助手。要启用英美离线发音，请先阅读 [语音依赖说明](docs/SPEECH.md)，再运行：

```powershell
.\run.ps1 -WithSpeech
```

这一步从上游下载运行组件和两套模型，合计约 150 MB，需要网络；之后查词、合成语音均在本机完成。源码仓库不附带这些第三方二进制和模型。没有安装语音依赖时，查词仍可用，发音按钮会提示未能播放。

保持软件运行，在支持的应用中拖选或双击英文，点击工具条中的“查词”“英”“美”或“复制”。也可主动复制单词显示工具条，或按 `Ctrl+Alt+D`。`×` / `Esc` 收起窗口，“··· → 退出应用”结束程序。

## 公开词库的范围

公开版使用 WordNet 3.0、Chinese Open Wordnet、Wiktionary 开放文本及少量自编复合词。词库来自多个来源，记录数与去重词数不同，具体构建统计见 [data/manifest.json](data/manifest.json)。

**公开版未打包 ECDICT、个人 PDF 提取词库或个人缓存**，因此覆盖范围和个人使用版本不完全相同。不同词的释义、音标和例句完整程度取决于来源；离线语音是合成发音，不是真人逐词录音。

## 许可证与隐私

原创应用代码按 [MIT](LICENSE) 开源。词库、图标和第三方依赖保留各自许可，**整个仓库不能一概当作 MIT 数据包**。请阅读 [第三方声明](THIRD_PARTY_NOTICES.md)、[来源与重建方式](SOURCES.md) 和 [发布前核查](docs/LICENSE_AUDIT.md)。

应用没有第三方私有查词接口，没有查询词上传或分析服务。点击“来源”会在浏览器打开公开来源页面。下载依赖时会连接相应上游。

应用会在本机保存设置、生词本、合成语音缓存和错误日志。划词响应计时日志包含来源进程、窗口及事件信息，不记录查询词或网页 URL；这些本机数据不进入仓库。详见 [隐私说明](docs/PRIVACY.md)。

## 开发与检查

```powershell
python -m pip install -r requirements.txt
python scripts/prepare_data.py
python -m unittest discover -s tests -p "test_*.py"
.\build_bridge.ps1
```

应用入口为 `app.py`；窗口与取词助手需要 Windows，词典数据检查可以单独运行。原始第三方数据的完整重建方法见 `SOURCES.md`。欢迎通过 Issue 提交错误词条、来源链接及最小复现步骤，请勿提交密码、私有文件或整份本机日志。

---

Woer Translator is a compact Windows desktop dictionary with selection-triggered actions, Simplified Chinese definitions, usage examples, morphology explanations, and optional independent UK/US offline speech models. Original application code is MIT; third-party data and dependencies retain their own licenses.
