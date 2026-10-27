# 第三方资源与许可

核查日期：2026-10-25。以下是所发布文件的许可范围，不代表对所有可能权利作零风险保证。项目与上游作者、词典出版商及相关机构没有官方合作或背书关系。

| 资源 | 本仓库中的内容 | 许可与履行方式 |
|---|---|---|
| 原创应用代码、脚本与自编复合词 | Python、C#、脚本、compound_entries.json | MIT；根目录 LICENSE、自编词条声明 |
| WordNet 3.0 | extended.db.gz 的英文词义、例句、词目及不规则词形 | WordNet 自带许可；保留 licenses/WordNet-LICENSE.txt，不以机构名宣传背书 |
| Chinese Open Wordnet | extended.db.gz 中按义项对应的中文词目 | 上游自带宽松许可；保留作者署名、声明及 licenses/COW-LICENSE.txt |
| Wiktionary，经 Wiktextract / Kaikki 提取 | community.db.gz；extended.db.gz 的结构化词形索引 | CC BY-SA 4.0；保留逐词原页 URL、贡献者署名、改动说明和同许可。extended.db.gz 中本项目新增的数据编排按 CC BY-SA 4.0，WordNet/COW 原内容保留原许可 |
| Lucide languages 图标 | assets/ 下 SVG、改色 PNG、ICO | ISC；保留 Lucide 完整许可及原图，声明改色、圆角背景、栅格化改动 |
| OpenCC Python 与字典数据 | 源码依赖；安装包内置 | Apache-2.0；保留许可证与来源 NOTICE，版本 0.1.7 |
| Wikimedia Commons 逐词真人录音 | 按需获取并缓存在用户目录，不随源码或安装包分发 | 逐文件 CC BY / CC BY-SA / CC0；保存作者、原文件页、许可链接、校验值、原始录音和转码说明，缓存内 ATTRIBUTION.html 汇总；音频沿用原许可 |
| miniaudio 1.71、CFFI 与 pycparser | Ogg/MP3/WAV 解码与运行桥接 | miniaudio 包自带 MIT；CFFI 的 MIT No Attribution 及附带组件声明、pycparser BSD；构建时收集精确版本及源包内完整许可至 licenses/runtime |
| certifi 与 Mozilla CA 根证书集合 | 更新检查与下载的 HTTPS 验证 | MPL-2.0；未修改上游文件，构建时将精确版本许可全文收集至 licenses/runtime；来源 https://github.com/certifi/python-certifi |
| Python / Tcl / Tk | 安装包运行组件 | PSF 及 Tcl/Tk 宽松许可；构建时收集精确版本全文至 licenses/runtime，Python 原许可含历史组件声明 |
| PyObjC | Mac 安装包系统接口桥接 | MIT；构建时保留 pyobjc-core 与各框架分发包的许可原文 |
| PyInstaller 启动器 | 冻结安装包 | GPL-2.0-or-later 加 bootloader exception；例外允许分发不同许可应用，原许可全文随包保留，不将构建工具整体当作本项目代码 |
| Piper 2023.11.14-2 / Piper Phonemize | 可选下载配置与独立进程适配代码，不分发运行二进制 | 上游 MIT 部分保留声明；其依赖包括 GPL-3.0 的 eSpeak NG，不能把整套运行包说成 MIT |
| Cori High / Kristin Medium 声音模型（兼容旧 Cori / LJSpeech） | 模型卡、固定版本与 SHA-256；不分发权重 | 上游仓库标注 MIT，模型卡将训练数据列为 public domain。使用者从上游直接下载并阅读相应条款 |
| 宣传图 | docs/promo.png | 本项目通过图像生成工具制作，含 ISC 许可的应用图标；不主张对通用图形或生成内容享有排他的商标权，图标许可继续适用 |

完整来源、链接、文件校验值见 SOURCES.md、data/manifest.json、data/checksums.json、scripts/speech-downloads.json。

## 数据改动

- 仅保留英语词条，把文本整理成索引 SQLite 数据库；未发布原始爬取程序之外的他人代码。
- Wiktionary 原创用例保留在原义项下，排除带引文类型、引用来源、作者、书名、年份或 URL 的示例；未附带媒体文件。
- 词形去重、过滤古旧及明显非标准标签；运行时转为简体中文并统一中文语法标签。
- WordNet 与 COW 通过同一 synset 对应，保留各自来源；Wiktionary 新增结构化索引与其文本按 CC BY-SA 4.0 分享。

## 明确排除

个人 PDF 及其提取词库、ECDICT 释义和由其导出的词形表、旧的未授权有道接口接入、他人广告或竞品商标、个人生词本、设置、剪贴板内容、语音缓存、日志、机器路径、令牌、Piper/eSpeak 预编译运行包和声音模型权重。桌面安装包只包含上表另行列明的运行组件。

这些排除并不意味着已认定相关材料侵权，而是其当前授权证据不足或与公开发行无关。


## 在线维基词典

通过 Wikimedia 官方 API 按需获取，词典文本及本软件的释义提取／繁简转换结果沿用 CC BY-SA 4.0。保留原词条、编辑历史与许可链接。与代码 MIT 许可分开标记。详见 [在线词典](docs/ONLINE_DICTIONARY.md)。不在源代码仓库分发用户在线缓存。
