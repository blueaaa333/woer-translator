# 发布前来源与许可核查

核查日期：2026-10-24。对象是本目录拟发布的源码和开放数据快照，不是整个个人安装文件夹。

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
| OpenCC | Apache-2.0 | 源码发布仅列为独立依赖，保留许可证、NOTICE；由用户从 PyPI 安装 |
| 个人权益和凭据 | 原开发目录有本机路径、PDF 输入、缓存和调试产物 | 使用文件白名单重建仓库；公开前检查暂存文件及压缩包，排除路径、日志、密钥和个人文件 |
| 程序二进制发行 | Python、Tk、PyInstaller、VC 运行库及语音依赖均有各自许可要求 | 本次只发布源码和可独立审查的数据，不将个人安装目录当成已审查安装包 |

## 主要依据

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
