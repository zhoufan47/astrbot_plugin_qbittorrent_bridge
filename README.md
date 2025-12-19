# AstrBot Plugin: qBittorrent Bridge

<div align="center">

![AstrBot](https://img.shields.io/badge/AstrBot-Plugin-violet)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)

**连接 AstrBot 与 qBittorrent，实现群聊/私聊远程下载管理**

</div>

## 📖 简介 

`astrbot_plugin_qbittorrent_bridge` 是一个为 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 设计的插件。
它允许用户通过指令直接与 qBittorrent 下载器交互。

无论你是在群聊中分享磁力链接，还是私聊机器人，都可用来测试磁力链接的可用性，并随时添加下载任务和查看下载任务的情况。

## ✨ 命令列表

### 基础命令

- `/magtest [磁链]` - 测试磁链可用性和下载速度
- `/magadd [磁链]` - 新增下载任务
- `/maginfo [任务hash]` - 查看任务状态
- `/qblogin` - 刷新qBittorrent WEB API登录状态

## 🛠️ 配置说明

插件使用 AstrBot 的官方配置系统。

- **qBittorrent WEB UI IP** (`qbittorrent_web_ui_host`): qBittorrent WEB UI的IP地址，如127.0.0.1
- **qBittorrent WEB UI 端口** (`qbittorrent_web_ui_port`):  qBittorrent WEB UI的端口，如8080
- **qBittorrent WEB UI 用户名** (`qbittorrent_web_ui_username`):  qBittorrent WEB UI的用户名
- **qBittorrent WEB UI 密码** (`qbittorrent_web_ui_password`): qBittorrent WEB UI的密码
- **测试时间** (`duration`): 用于测试磁链下载的时间，更长的时间可以获得更为可靠的下载速度
- **元数据等待时间** (`meta_timeout`): 用于等待元数据抓取的时间，过短的时间可能导致大部分磁链无法正常获取元数据
- **自定义tracker** (`tracker_list`): 自定义Tracker列表，更多的tracker可以更快的获取磁链元数据和更高的下载速度和健康度
- **测试目录** (`test_path`): 用于下载测试文件的目录
- **下载目录** (`download_path`): 用于保存下载文件的目录

## 🛠️ 安装方法 | Installation

### 1. 安装插件
AstrBot 插件市场
