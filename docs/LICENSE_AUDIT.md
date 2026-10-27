# 整体发布授权核查（2026-10-27）

## 可确认的结论

本次核查覆盖公开仓库及 v0.3.10 三个平台发布资产，并据发现完善 v0.3.11。**不能签发“整个软件在全球完全不侵权”的保证，也不能将 MIT 或非营利当作所有第三方资源的授权。** 本报告是来源、许可与打包证据审查，不是法院认定或律师法律意见。

已清点来源、核验公开数据校验值、核对官方许可、检查实际分发内容，并补齐运行库的独立许可映射与构建检查。上游授权有明确证据的资源继续按各自条件使用；私人 PDF 及其派生词库仍不进入公开发行。

## 范围和证据

- 公开仓库源树：`c88f79cc0e3282c48356d92b9eb93936205388ae`，当时共 132 个文件，GitHub 递归列表完整。没有 PDF、模型、音频、个人设置、证书私钥等文件。
- 本地候选目录与该树比较，差异仅在尚未公开的 Windows 安装后更新启动草稿与自动生成的更新索引；这次审查以 GitHub 已发布版本为准，没有将本地草稿当成已发布代码。
- 三份公开安装器及校验清单已实际下载、核对大小和 SHA-256；下载过程中拿到的截断响应被拒绝，最终只接受完整匹配的文件。
- 两份 Mac DMG 均实际列出文件并提取 `Contents/Resources` 内声明。Windows 检查同次 CI 工件 `12703139534` 的 Portable ZIP；工件内 Setup.exe 与公开安装器 SHA-256 相同。Windows 安装器内部压缩块没有用第三方解包器再次展开，而是结合该 CI 产物和 Inno 的打包文件清单核对。
- 公开词库三个压缩文件及解压数据库全部匹配 `data/checksums.json`；兼容 words 库条目数为 0；community 库 157049 个记录均保留合法 Wiktionary 原词条 URL，37250 个例句来自已有过滤流程。结构检查不等于对这些贡献逐条作了原创权属调查。
- 软件包依赖版本依据包内 `build-info.json`，不是开发电脑上可能不同的版本。v0.3.10 三个平台均为 Python 3.12.10；Windows 和 Mac 的本地运行库声明分别检查。

## 本次发现与处理

| 项目 | 核查结果与处理 |
|---|---|
| Python 原生运行库 | 原收集器只复制根 LICENSE 和 Python 包许可，没有清楚、独立记录所有底层依赖。特别是 OpenSSL 组件与 Apache-2.0 的对应关系不够明确。包内其他组件已有 Apache 许可文本，因此不能仅凭“缺少独立 OpenSSL 文件”就断言旧版本构成侵权。本次增加实际 OpenSSL／zlib 版本的原始许可、CPython incorporated-software、Expat、libmpdec、libffi、bzip2、liblzma 声明及出处／哈希索引。 |
| 发布检查 | v0.3.11 冻结包冒烟检查会核验必要声明和采集哈希，拒绝私人库条目、PDF、模型、音频和未核查嵌入字体。缺少声明即构建失败。自动检查只证明设定的检查项通过。 |
| 安装提示的隐私文字 | 旧提示笼统说不上传查询记录，未准确表达新在线查词行为。改为明确当前查询词会按功能开关发送给 Wiktionary／Commons，不发送整页、剪贴板历史或私人词库。 |
| 名称和宣传 | 没有使用竞品 logo 或宣称商业词典／Wikimedia 官方背书。项目图标保留 Lucide ISC；宣传图记录生成来源。未开展足以证明全球名称可用的正式商标检索，也未作生成图独创性保证。 |

## 逐项资源处置

| 资源 | 许可／使用依据 | 本次履行与边界 |
|---|---|---|
| 自编代码、词条和例句 | 项目 MIT | 本项目编写并保留 LICENSE；未把第三方数据改标 MIT。未证明所有抽象交互方案均不存在第三方专利。 |
| WordNet 3.0 / COW | 上游许可允许按条件复制、修改、分发 | 保留全文版权、免责条款和来源；公开数据库重新构建，未从私人混合库抽取。 |
| 离线 Wiktionary | CC BY-SA 4.0 | 各词条保留来源 URL、贡献者署名、改动说明和同许可；已过滤带引用标记的例句。未人工审核上游每条贡献的实际权属。 |
| 在线 Wiktionary | 官方 API + CC BY-SA 4.0 | 保留原词条、编辑历史、版本及许可链接，标明提取与繁简转换；不把词典文本改为 MIT。原页特别署名或引用例外仍应遵守，开放站点不保证上游毫无侵权贡献。 |
| Lucide languages 改色图标 | ISC | 原图、完整 ISC 及相关 Feather 声明保留，标记改色和栅格化；不主张图标排他商标权。 |
| OpenCC | Apache-2.0 | 保留 LICENSE 与来源 NOTICE；没有嵌入用户系统字体。 |
| Python/Tcl/Tk/PyObjC/PyInstaller | 各自许可及 bootloader exception | 保留准确分发版本的许可；v0.3.11 增加原生库声明和阻断检查；Apple 系统接口的调用不等于再发行系统声音。 |
| miniaudio/CFFI/pycparser/certifi | 各自 MIT、BSD、MPL 等 | 收集分发包和匹配源包许可，保留 CFFI 附带组件声明。没有修改 certifi 的上游文件。 |
| Windows 安装器 | Inno Setup 许可 | 未改写 Inno 版权信息，不声称由本项目编写其安装器引擎；安装器许可与应用代码许可分开。 |
| Commons 真人录音 | 逐文件 CC BY、CC BY-SA 或 CC0 | 运行时校验许可、作者和来源，保留原件、转换说明与署名页。安装器不含这些录音；不能证明所有上传者都确实拥有全部权利。 |
| 可选 Piper / eSpeak 与音色 | 固定上游下载，程序和模型各自许可 | 不在仓库／安装器重新分发运行二进制和模型；保留 GPL 等声明，不把整个运行包称为 MIT。模型卡和固定来源保留。LibriVox 的公有领域声明有地域边界，不能据此保证全球声音人格权、录音或训练资料权利。 |
| 私人 PDF、ECDICT、考试词库 | 当前没有完整公开发行权利证据 | 不进入公开仓库或安装包；本机个人安装目录保留，未被本报告认定为可公开整包分发。 |

## 尚不能作出保证的事项

1. 每条上游释义／例句／音频贡献者的真实权利链及司法辖区差异。
2. 声音人格权益、训练材料在所有国家的权利状态。
3. 项目名称、图标的正式商标可用性，全球软件专利及生成图原创性。
4. 历史版本和已下载副本不会因本次更新自动改变；请升级取得补齐的声明。后续新增资源必须重新核查。

这些边界不会通过写一句“仅供学习、不盈利、侵删”而消失。对已发现的许可文件与来源记录问题，本项目已整改；对无法证明的权利事实，不作零风险承诺。

## 官方依据

- [WordNet](https://wordnet.princeton.edu/license-and-commercial-use)、[COW 原许可](https://github.com/omwn/omw-data/blob/main/wns/cow/LICENSE)
- [Wikimedia 条款](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use#7._Licensing_of_Content)、[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- [Lucide 原许可](https://github.com/lucide-icons/lucide/blob/main/LICENSE)
- [Python incorporated-software](https://docs.python.org/3.12/license.html#licenses-and-acknowledgements-for-incorporated-software)、[OpenSSL 3.0.16](https://github.com/openssl/openssl/blob/openssl-3.0.16/LICENSE.txt)
- [PyInstaller 例外](https://pyinstaller.org/en/stable/license.html)、[Inno Setup](https://jrsoftware.org/files/is/license.txt)
- [LibriVox 公有领域地域说明](https://librivox.org/pages/public-domain/)

## 实际核查的 v0.3.10 公开资产

| 文件 | SHA-256 |
|---|---|
| SHA256SUMS.txt | `585a747a61d2ebf137373da345aee41ab079a567ca55c7d86fe5b02b7d52a233` |
| WoerTranslator-0.3.10-macOS-arm64.dmg | `05b797773e796a849426d3497ab98c86e30e038ed84902c7e8edb0ea6c4eb7c0` |
| WoerTranslator-0.3.10-macOS-x64.dmg | `ed5527403d068928b09562ea56fb9e9a909e1e35435e40a0e14035ede5f7e937` |
| WoerTranslator-0.3.10-Windows-x64-Setup.exe | `f4f68c416641a8dfa63a8e5fea5c0c8375d61b97cb4c68a791613ba2390e0857` |

## 以前版本的核查记录（历史说明）

以下是旧版记录，不能代替本次范围和发现。

# 发布前来源与许可核查

核查日期：2026-10-24。对象是本目录发布的源码、开放数据快照及从该清单构建的 v0.2.0 桌面安装包，不是整个个人安装文件夹。

## 结论

**原安装目录不宜直接整包上传。** 公开版已采用明确文件清单重新整理：原创代码使用 MIT，开放词典按各自许可分发，保留署名、来源链接、改动说明及同许可要求。未发现本次选定发布文件中仍调用未授权有道端点、附带个人 PDF 或包含已知个人缓存的情况。

这是基于可查证许可和代码检查的发布风险核查，不是法律意见，也不能证明全球范围内绝无版权、商标、专利、人格权或上游授权瑕疵。宣传不使用“零侵权”“百分百准确”等保证。对具体投诉应核实来源并及时处理。

## 发现与处理

| 项目 | 发现 | 本次处理 |
|---|---|---|
| 自编应用与 UI | Python / C# 源码在本项目中编写；布局借鉴通用桌面浮窗交互 | 公开源码、采用 MIT；不附带竞品素材或声称官方关联 |
| ECDICT | 仓库声明 MIT；README 同时记载部分释义、词表与音标来自其他外部资料，当前没有逐项上游授权证据 | 从公开版全部排除其释义、派生词形表和考试标签；不据仓库许可作完整权属保证 |
| 用户提供的 PDF | 持有文件或可阅读不等于获得重新分发权；没有收到公开发行许可 | 不发布原 PDF、提取文本、exam_core.db 或相关脚本、截图 |
| WordNet / COW | 上游明确允许按条件使用、修改、分发 | 从原始开放数据重新构建，不从混合私有库抽取；保留全文许可、原作者署名和免责声明 |
| Wiktionary | 原创文本允许按 CC BY-SA 4.0 复用；引用他人的示例可能另有版权 | 保留逐词原页链接、贡献者署名、同许可及改动说明；重新构建时过滤已标记第三方引文，不打包图像、录音等媒体 |
| Piper 语音运行包 | 程序的 MIT 部分之外包含 eSpeak NG 等依赖；历史构建引用浮动 master，现存源码归档不能证明与所有二进制精确对应 | 这次不分发二进制、DLL、模型权重；只提供可选择的上游下载脚本、固定版本、SHA-256 和许可说明 |
| 英美语音模型 | 上游仓库声明 MIT；两份模型卡把训练语料列为 public domain | 保留原模型卡；模型下载固定提交，两份权重校验值已与官方 LFS SHA-256 对照。未作声音人格权或全球公有领域状态的额外保证 |
| Lucide 图标 | ISC 许可，允许按条件改编和分发 | 保留 SVG、完整许可及改动说明，不主张图标的排他商标权 |
| OpenCC | Apache-2.0 | 源码列为依赖，安装包内置；保留许可证、NOTICE |
| 个人权益和凭据 | 原开发目录有本机路径、PDF 输入、缓存和调试产物 | 使用文件白名单重建仓库；公开前检查暂存文件及压缩包，排除路径、日志、密钥和个人文件 |
| 程序二进制发行 | Python、Tcl/Tk、PyObjC、PyInstaller 启动器有各自许可要求 | 从公开源码和独立构建环境制作安装包，附带 Python 全文（含历史声明）、Tcl/Tk 与依赖包许可。PyInstaller 的启动器例外保留原文；不打包 Piper、eSpeak 或模型 |
| macOS 系统声音 | 通过系统接口调用，不是本项目可再许可的声音素材 | 不分发 Apple 声音，仅由用户在系统中选择或下载；安装包无 Developer ID 签名或 Apple 公证 |

## 主要依据

### v0.3.3 真人发音补充核查（2026-10-25）

源码与安装包不分发录音，运行时按需从 Commons 获取。只接受准确词目与英美口音文件名、作者、可复用 CC BY / CC BY-SA / CC0 许可链接及无额外限制的文件；校验原始文件 SHA-1，保留原文件、PCM 转换文件、作者、来源、原许可与改动说明。音频不改为 MIT，CC BY-SA 继续适用于相关音频。许可依据上游声明，不能排除上传者权利瑕疵；支持按具体文件排查与移除。

miniaudio 1.71 的分发包附带绑定、miniaudio、stb_vorbis 的 MIT 许可；构建另外收集精确版本源包和 CFFI、pycparser 的声明。不会调用商业词典的私有发音接口。详见 [语音来源](SPEECH.md)、[Commons 复用规则](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia) 和每条缓存的署名页。

- [ECDICT README 的数据历史与 MIT 声明](https://github.com/skywind3000/ECDICT)
- [WordNet 许可](https://wordnet.princeton.edu/license-and-commercial-use)
- [Chinese Open Wordnet 许可](https://github.com/omwn/omw-data/blob/main/wns/cow/LICENSE)
- [Wiktionary 版权说明](https://en.wiktionary.org/wiki/Wiktionary:Copyrights)
- [CC BY-SA 4.0 条件](https://creativecommons.org/licenses/by-sa/4.0/)
- [Piper Phonemize 构建配置](https://github.com/rhasspy/piper-phonemize/blob/2023.11.14-2/CMakeLists.txt)
- [Lucide 许可](https://github.com/lucide-icons/lucide/blob/main/LICENSE)
- 逐项模型卡、原始许可证、输入校验值及改动说明见 `licenses/`、`SOURCES.md`、`data/manifest.json`。

## 尚不能由本次核查代替的事项

本次没有开展正式商标注册检索、全球专利检索或对每一条上游词典贡献作权属调查。项目名“沃尔翻译官”是软件名称，不代表已取得注册商标。若后续要商业推广、出售含第三方运行组件的安装包或作其他特殊用途，需要按实际用途另行核查。
