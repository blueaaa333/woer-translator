# 可选离线英美语音

英式使用 `en_GB-cori-medium`，美式使用 `en_US-ljspeech-medium`；两个按钮调用不同模型。它们是本机合成语音，不能保证所有专名、多音词或上下文中的重音都准确。

本源码包不附带 Piper 二进制、eSpeak NG、ONNX Runtime 或模型权重。用户选择执行 `python scripts/setup_speech.py` 后，脚本才直接从上游下载，并核对固定 SHA-256。模型采用固定 Hugging Face 提交，运行时固定 Piper 2023.11.14-2 发布文件，具体见 `scripts/speech-downloads.json`。

- [Piper 发布](https://github.com/rhasspy/piper/releases/tag/2023.11.14-2)
- [Piper 源码与 MIT 许可](https://github.com/rhasspy/piper/tree/2023.11.14-2)
- [Piper Phonemize](https://github.com/rhasspy/piper-phonemize/tree/2023.11.14-2)
- [eSpeak NG 与 GPL-3.0](https://github.com/rhasspy/espeak-ng)
- [英式模型卡](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_GB/cori/medium/MODEL_CARD)
- [美式模型卡](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/ljspeech/medium/MODEL_CARD)

两份模型卡把训练语料分别列为 LibriVox / LJ Speech，标注 public domain；声音仓库元数据标注 MIT。保留原模型卡，不声称声音或发音由本项目原创。

Piper 的开源许可不等于整套第三方依赖都采用 MIT。eSpeak NG 属于 GPL 组件；若未来分发含这些运行组件的安装包，需要针对实际二进制版本提供对应源码、必要构建信息及完整第三方声明。当前核查无法从历史构建的浮动依赖精确追溯全部二进制对应源码，因此本次不重新分发这些运行包。

只在用户主动执行安装命令时下载。应用默认不自动朗读；可在“···”开启。缓存、首次加载和 90 秒闲置释放行为不会联网。
