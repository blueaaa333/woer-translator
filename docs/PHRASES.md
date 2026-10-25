# 短语整体翻译

本地词典优先查询完整短语，不会把几个单词的意思拼成短语释义。自编条目优先展示；选区不包含上下文时，不自动推断用户正在阅读的领域。

## 可选本地翻译服务

通用机器翻译尚未包含在基础安装包中。需要先在自己的电脑部署 [LibreTranslate](https://github.com/LibreTranslate/LibreTranslate)，再打开软件设置中的“使用本地翻译服务”。本客户端只连接 `http://127.0.0.1:5000/translate`，默认关闭。无需 GPT 账户或 API 费用；不会发送选中文字到公共翻译站点。服务运行后，查询未收录的多词短语会在后台获取中文机器翻译。

已安装 Docker 的用户可参考上游文档运行：

```sh
docker run --rm -p 127.0.0.1:5000:5000 libretranslate/libretranslate --load-only en,zh
```

首次运行会下载模型，需要网络、磁盘和内存；Docker 和模型下载不是本软件自动完成的。关闭容器后，机器翻译不可用，本地词典仍可使用。Docker Desktop 的使用条件另见其官方许可。

机器翻译不等于专业术语解释，可能误译。需要专业语境时，请同时查看分领域条目。当前划词安全限制仍为最多六个英文词、80 个字符，尚不支持整页或长句翻译。

## 来源与许可

LibreTranslate 上游采用 AGPL-3.0，本客户端通过独立 HTTP API 调用，未复制或分发其代码、模型。自行部署者应遵守服务及所选模型各自的许可；开放源代码不意味着所有资料都可不署名转载。

本软件的短语中文说明和双语示例为自行编写，不复制商业词典文本。Double Jeopardy 的营销解释参考 [Ehrenberg-Bass Institute](https://marketingscience.info/news-and-insights/effective-brand-growth-acquisition-or-retention)，法律解释仅为通用词义，不提供个案建议。

聊天中的 ChatGPT 订阅不能直接作为第三方软件的免费 GPT API。本版本没有连接聊天账户或嵌入 API 密钥。
