from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import qbittorrentapi
import time
import sys
import re


def _extract_hash(magnet_link: str) -> str:
    """从磁力链接中提取 Info Hash"""
    match = re.search(r'xt=urn:btih:([a-zA-Z0-9]+)', magnet_link)
    if match:
        return match.group(1).lower()
    return None


@register("qBittorrent Bridge", "棒棒糖", "Build a bridge to your Qbittorrent", "1.0.0")
class qBittorrentBridge(Star):
    def __init__(self, context: Context,config: dict):
        super().__init__(context)
        self.client = None
        self.web_ui_host = config.get("qbittorrent_web_ui_host", "")
        self.web_ui_port = config.get("qbittorrent_web_ui_port", "")
        self.web_ui_username = config.get("qbittorrent_web_ui_username", "")
        self.web_ui_password = config.get("qbittorrent_web_ui_password", "")
        self.duration = config.get("duration",30)
        self.custom_trackers = config.get("tracker_list",[])
        logger.info("插件 [qBittorrent Bridge] 已初始化。")

    async def initialize(self):
        try:
            self.client = qbittorrentapi.Client(host=self.web_ui_host,
                                                port=self.web_ui_port,
                                                username=self.web_ui_username,
                                                password=self.web_ui_password)
            self.client.auth_log_in()
            logger.info(f"✅ 成功连接到 qBittorrent (v{self.client.app.version})")
            logger.info(f"   API 版本: {self.client.app.web_api_version}")
        except Exception as e:
            logger.error(f"❌ 连接 qBittorrent 失败: {e}")
            logger.error("   请检查：1. qBittorrent 是否已启动？ 2. Web UI 是否已开启？ 3. 端口/账号/密码是否正确？")

    @filter.command("magtest")
    async def mag_test(self, event: AstrMessageEvent,magnet_link: str):
        info_hash = _extract_hash(magnet_link)
        if not info_hash:
            logger.error("❌ 无效的磁力链接，无法提取 Hash。")
            yield event.plain_result("❌ 无效的磁力链接，无法提取 Hash。")
            return

        logger.info(f"🔍 开始测试，目标 Hash: {info_hash}")
        yield event.plain_result(f"🔍 开始测试，目标 Hash: {info_hash}")

        # 2. 添加任务
        logger.info("➕ 正在发送任务到 qBittorrent...")
        self.client.torrents_add(urls=magnet_link, tags=['magnet_tester_script'], save_path=None)

        time.sleep(1)

        if self.custom_trackers:
            logger.info(f"📡 注入 {len(self.custom_trackers)} 个自定义 Tracker...")
            self.client.torrents_add_trackers(torrent_hash=info_hash, urls=self.custom_trackers)
            self.client.torrents_reannounce(torrent_hashes=info_hash)
        # 4. 等待元数据 (Metadata)
        logger.info("⏳ 正在解析元数据 (等待中)...")
        meta_success = False
        start_wait = time.time()

        # 使用 sys.stdout 保持动态刷新效果，不写入日志文件避免刷屏
        while time.time() - start_wait < 45:
            torrents = self.client.torrents_info(torrent_hashes=info_hash)
            if not torrents:
                time.sleep(1)
                continue

            t = torrents[0]
            if t.state != 'metaDL' and t.total_size > 0:
                meta_success = True
                break

            # 动态显示进度（仅控制台可见）
            sys.stdout.write(
                f"\r   [Metadata] 耗时: {int(time.time() - start_wait)}s | 状态: {t.state} | Peers: {t.num_leechs} | Seeds: {t.num_seeds}")
            sys.stdout.flush()
            time.sleep(1)

        sys.stdout.write("\n")  # 换行

        if not meta_success:
            logger.error("❌ 元数据获取超时。该资源可能无人做种 (Dead Torrent)。")
            yield event.plain_result("❌ 元数据获取超时。该资源可能无人做种 (Dead Torrent)。")
            logger.info("🧹 清理任务中...")
            self.client.torrents_delete(torrent_hashes=info_hash, delete_files=True)
            return

        # 获取详细信息
        t = self.client.torrents_info(torrent_hashes=info_hash)[0]
        first_report = (f"✅ 元数据获取成功！\n"
                        f"📦 资源名称: {t.name}\n"
                        f"💾 总大小: {t.total_size / 1024 / 1024:.2f} MB")
        logger.info("-" * 10)
        logger.info(first_report)
        yield event.plain_result(first_report)

        # 获取文件列表
        try:
            files = self.client.torrents_files(torrent_hash=info_hash)
            logger.info(f"📄 文件列表 (前 5 个 / 共 {len(files)} 个):")
            for f in files[:5]:
                logger.info(f"   - {f.name} ({f.size / 1024 / 1024:.2f} MB)")
        except Exception as e:
            logger.warning(f"   (文件列表获取失败: {e})")
        logger.info("-" * 10)

        # 5. 持续下载测试
        logger.info(f"🚀 开始 {self.duration} 秒下载性能测试...")

        start_test = time.time()
        while time.time() - start_test < self.duration:
            t_list = self.client.torrents_info(torrent_hashes=info_hash)
            if not t_list: break
            t = t_list[0]

            elapsed = int(time.time() - start_test)

            # 动态进度条（保留 sys.stdout.write 以获得更好的控制台体验）
            sys.stdout.write(
                f"\r[{elapsed}/{ self.duration}s] "
                f"速度: {t.dlspeed / 1024:.1f} KB/s | "
                f"做种: {t.num_seeds} (全网:{t.num_complete}) | "
                f"下载: {t.num_leechs} | "
                f"进度: {t.progress * 100:.1f}%"
            )
            sys.stdout.flush()
            time.sleep(1)

        sys.stdout.write("\n")  # 换行
        logger.info("-" * 50)

        # 6. 最终报告
        t_list = self.client.torrents_info(torrent_hashes=info_hash)
        if t_list:
            t = t_list[0]
            availability = t.get('availability', 0)
            final_report = (f"🏁 [一分钟测试报告]\n"
                            f"📊 健康度: {availability:.2f}\n"
                            f"🌱 做种人数 (Seeds): {t.num_seeds} (已连接) / {t.num_complete} (全网发现)\n"
                            f"👥 下载人数 (Leechers): {t.num_leechs} (已连接) / {t.num_incomplete} (全网发现)\n"
                            f"⬇️ 最终下载速度: {t.dlspeed / 1024:.2f} KB/s\n"
                            f"📥 一分钟实际下载量: {t.downloaded / 1024 / 1024:.2f} MB")
            if availability < 1.0:
                final_report = final_report + " ⚠️ 警告：健康度小于 1.0，说明全网可能没有完整资源。\n"
            else:
                final_report = final_report + " ✅ 资源健康，理论上可完整下载。\n"
            yield event.plain_result(final_report)

        # 7. 清理
        logger.info("-" * 50)
        logger.info("🧹 清理中：删除测试任务及下载文件...")
        self.client.torrents_delete(torrent_hashes=info_hash, delete_files=True)
        logger.info("✅ 测试结束，清理完成。")

    @filter.command("magadd")
    async def mag_add(self, event: AstrMessageEvent,magnet_link: str):
        info_hash = _extract_hash(magnet_link)
        if not info_hash:
            logger.error("❌ 无效的磁力链接，无法提取 Hash。")
            yield event.plain_result("❌ 无效的磁力链接，无法提取 Hash。")
            return

        logger.info("➕ 正在发送任务到 qBittorrent...")
        self.client.torrents_add(urls=magnet_link, tags=['magnet_tester_script'], save_path=None)
        yield event.plain_result(f"✅ 任务已发送至 qBittorrent，任务hash:{info_hash}。")
        if self.custom_trackers:
            logger.info(f"📡 注入 {len(self.custom_trackers)} 个自定义 Tracker...")
            self.client.torrents_add_trackers(torrent_hash=info_hash, urls=self.custom_trackers)
            self.client.torrents_reannounce(torrent_hashes=info_hash)

    @filter.command("maginfo")
    async def mag_info(self, event: AstrMessageEvent,info_hash: str):
        t_list = self.client.torrents_info(torrent_hashes=info_hash)
        if t_list:
            t = t_list[0]
            availability = t.get('availability', 0)
            final_report = (f"🏁 [当前任务状态]:{t.state}\n"
                            f"📊 健康度: {availability:.2f}\n"
                            f"🌱 做种人数 (Seeds): {t.num_seeds} (已连接) / {t.num_complete} (全网发现)\n"
                            f"👥 下载人数 (Leechers): {t.num_leechs} (已连接) / {t.num_incomplete} (全网发现)\n"
                            f"⬇️ 下载速度: {t.dlspeed / 1024:.2f} KB/s")
            yield event.plain_result(final_report)
        else:
            yield event.plain_result(f"没有找到任务:{info_hash}")


    async def terminate(self):
        if self.client and not self.client:
            self.client = None
            logger.info("qBittorrent Bridge 插件已卸载，Api Client 客户端已关闭。")
