# 沃尔翻译官安装包下载器

普通用户请直接到 [Releases](https://github.com/blueaaa333/woer-translator/releases/latest) 下载桌面安装包，不需要 Node.js。

本 GitHub Packages npm 包提供命令行下载入口，不包含完整桌面程序。需要 Node.js 20 或更高版本。GitHub 的 npm 注册表可能要求登录，即使软件包是公开的。

```sh
npm install --global @blueaaa333/woer-translator --registry=https://npm.pkg.github.com
woer-translator download
woer-translator install
```

`download` 只下载当前操作系统和芯片架构的安装包，核对同一 Release 的 SHA-256 后保存，不运行文件。`install` 在校验通过后打开安装器，由系统界面完成安装。不会在 npm 安装时自动运行，不修改系统安全设置。

支持 Windows x64、macOS Apple 芯片和 Intel。macOS 首版采用本地临时签名，尚未取得 Apple Developer ID 签名或公证。桌面安装包中的第三方数据和运行库适用各自许可；本下载器代码采用 MIT。
