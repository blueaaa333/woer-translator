# 英美真人录音与本地合成语音

## 优先真人录音（Windows / macOS）

v0.3.3 起，默认优先从 Wikimedia Commons 获取带明确 `En-uk` / `En-gb` 或 `En-us` 文件名的逐词真人录音。只接受逐文件可核验的 CC BY、CC BY-SA 或 CC0 许可；缺作者、许可链接、口音标记、文件校验值，或带有额外限制的录音均跳过。不是所有词都有两种口音的录音，多音词、专名和复合词也可能缺少合适读法；此时回退到本地合成，并显示“合成发音”，不把一个口音用于两个按钮。

首次播放时会发送当前查询词给 Commons API，按需下载单词录音，不下载整套音频库。缓存后再次播放同一词和口音无需联网。“··· → 优先真人发音（联网）”可关闭；自动朗读开启时，查词会触发相同的录音获取流程。网络错误有短暂退避，网络请求、解码、播放均在后台进行，界面不等待。

每条音频保留作者、原文件页、许可链接、原始文件 SHA-1、缓存 WAV 的 SHA-256 和改动说明。原始录音与转码 WAV 保存在用户缓存的 `speech-cache/recordings` 中；“··· → 发音来源与许可”或真人发音播放完成后的状态文字可打开本地署名页。只转换为 16 位 PCM WAV，保留正常语速、音高和完整内容；不做变速、变调或裁剪。转码音频按原许可提供，CC BY-SA 录音及其转换文件继续采用相同许可，不适用应用代码的 MIT 许可；分享音频时须携带对应署名、来源、许可和改动说明。源码与安装包不附带这些录音或个人缓存。

例如 `water` 的英音来自 Association Shtooka / Judith Franck（[原页](https://commons.wikimedia.org/wiki/File:En-uk-water.ogg)，CC BY 3.0 us），美音来自 Dvortygirl（[原页](https://commons.wikimedia.org/wiki/File:En-us-water.ogg)，CC BY-SA 3.0）。这是两个独立录音，不是对同一音频调整音高。

解码使用 miniaudio 1.71 Python 包，包内许可覆盖绑定、miniaudio 和 stb_vorbis；运行安装包保留 MIT 原文和 CFFI / pycparser 的对应许可。没有抓取商业词典私有音频接口，也没有把“网页可播放”视作转载授权。许可核验依据上游逐文件声明，不代表对所有上传者权利作绝对保证；发现问题可提交文件页和单词以便排除。

- [Commons 复用说明](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia)
- [MediaWiki imageinfo 元数据接口](https://www.mediawiki.org/wiki/API:Imageinfo)
- [miniaudio Python 项目](https://github.com/irmen/pyminiaudio)

## macOS 本地回退

Mac 版使用系统自带 `/usr/bin/say` 和 `/usr/bin/afplay`，按语言区域选择 `en_GB` 与 `en_US` 声音；优先选择目录中标记 Premium / Enhanced 的已安装声音，否则优先匹配常规的 Daniel / Samantha 等声音，不分发 Apple 语音资源。缺少某口音时，会提示在系统设置的辅助功能朗读声音中下载，不会用另一个口音冒充。系统设置中的具体名称会随 macOS 版本变化。声音与 AIFF/WAV 缓存均在本机处理。

## Windows 本地回退

新包英式使用 `en_GB-cori-high`，美式使用 `en_US-kristin-medium`；两个按钮调用不同模型，并保留各模型原始的音素前端配置。不能仅凭 language.code 把 espeak.voice 强改成另一名称，否则可能与模型训练时的音素系统不匹配。旧的 Cori Medium / LJSpeech Medium 文件继续作为兼容回退，不被覆盖。它们是本机合成语音，不能保证所有专名、多音词或上下文中的重音都准确。

源码和桌面安装包不附带 Piper 二进制、eSpeak NG、ONNX Runtime 或模型权重。用户在软件菜单选择“下载英美离线语音”或执行 `python scripts/setup_speech.py` 后，才直接从上游下载，并核对固定 SHA-256。模型采用固定 Hugging Face 提交，运行时固定 Piper 2023.11.14-2 发布文件，具体见 `scripts/speech-downloads.json`。安装包下载到本机用户数据目录，源码脚本默认下载到源码目录。

- [Piper 发布](https://github.com/rhasspy/piper/releases/tag/2023.11.14-2)
- [Piper 源码与 MIT 许可](https://github.com/rhasspy/piper/tree/2023.11.14-2)
- [Piper Phonemize](https://github.com/rhasspy/piper-phonemize/tree/2023.11.14-2)
- [eSpeak NG 与 GPL-3.0](https://github.com/rhasspy/espeak-ng)
- [英式模型卡](https://huggingface.co/rhasspy/piper-voices/blob/5041a7a49ae5b3a0f30e6837769eb03fdbb231bd/en/en_GB/cori/high/MODEL_CARD)
- [美式模型卡](https://huggingface.co/rhasspy/piper-voices/blob/5041a7a49ae5b3a0f30e6837769eb03fdbb231bd/en/en_US/kristin/medium/MODEL_CARD)

两份模型卡将训练语料列为 LibriVox，标注 public domain；声音仓库元数据标注 MIT。保留原模型卡，不声称声音或发音由本项目原创。

Piper 的开源许可不等于整套第三方依赖都采用 MIT。eSpeak NG 属于 GPL 组件；若未来分发含这些运行组件的安装包，需要针对实际二进制版本提供对应源码、必要构建信息及完整第三方声明。当前核查无法从历史构建的浮动依赖精确追溯全部二进制对应源码，因此本次不重新分发这些运行包。

上述模型仅在用户主动选择下载时联网；合成过程和闲置释放不联网。真人录音的联网行为见上文。应用默认不自动朗读；可在“···”开启，开关和口音会保存。

## Windows 声音检查（v0.3.4）

出现“已输出”却听不到时，请在“··· → 声音检查与输出设备”选择实际使用的扬声器或耳机，点击“播放测试音”。测试音由程序在本机生成，不依赖联网和语音模型。默认采用 WASAPI 等实际输出后端，拒绝静音数据和虚拟的无声后端；可主动切换旧版 Windows 兼容播放。系统默认模式解析当前默认输出设备，手动选过的设备断开时会要求重新选择。

如果仍听不到，点击“打开 Windows 音量混合器”，在测试音播放期间检查沃尔翻译官的独立音量、静音和路由。软件不自动解除静音、不提高系统音量，也不更改其他应用。设备成功接收音频不等于人已听到；“复制声音检查信息”提供所选设备、后端、音频峰值与时长、结果提示和应用版本，不包含查询词、音频文件或个人词库。关闭窗口不清除输出偏好。

## 发音响应优化（v0.3.5）

查词后可在后台静默打开输出设备，不会发声或增加查询词的联网发送。连续播放复用同一设备，闲置 30 秒关闭，退出应用时立即关闭；改选设备后切换连接。PCM 缓存最多 16 条且不超过 8 MB，文件大小或修改时间变化时重新解码。录音查询结果（包括不存在对应录音）缓存 24 小时；已下载录音仍沿用逐文件校验及署名。首次下载录音的网络等待、蓝牙和声卡的实际输出缓冲无法完全消除。检查信息中的 first_pcm_ms 是当前播放处理到首次提交 PCM 的时间，不含录音获取时间，也不等于声音抵达人耳的时间。

## 统一合成音色（v0.3.6）

从设置主动下载／升级约200 MB 的新包；新文件保存为各口音目录中的 dictionary-voice.onnx 和配置，保留原模型卡，不覆盖旧 voice.onnx。安装时跳过与固定上游压缩包完全相同的运行文件，避免重写正在使用的运行程序；模型与运行文件仍需通过 SHA-256。完成后自动关闭“优先真人发音（联网）”，使用刚下载的统一合成音色；可自行重新打开真人录音选项。朗读开关、默认口音、输出设备和生词本保持原选择。

原始模型前端保留不变。本次撤回了试验中强改 en-us 的做法；文件标记为 en_US 不等于必须改写其训练时的 phonemizer。短词补句末标点以提供完整 utterance，语速保持正常；这不是商业词典原声，也不能证明所有重音或多音词均正确。

没有接入或复制必应词典音频：微软服务协议的 Bing and MSN 条款没有授予把其中素材用于自有产品的通用权限。条款：https://www.microsoft.com/en-us/servicesagreement 。官方词典录音接入需要另行许可。
