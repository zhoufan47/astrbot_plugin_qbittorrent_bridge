import asyncio
import time
from typing import Optional, Any

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import qbittorrentapi
import re


def _extract_hash(magnet_link: str) -> Optional[str]:
    """从磁力链接中提取 Info Hash"""
    match = re.search(r'xt=urn:btih:([a-zA-Z0-9]+)', magnet_link)
    if match:
        return match.group(1).lower()
    return None


@register("qBittorrent Bridge", "棒棒糖", "Build a bridge to your Qbittorrent", "1.0.1")
class QBittorrentBridge(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.client = None
        self.web_ui_host = config.get("qbittorrent_web_ui_host", "")
        self.web_ui_port = config.get("qbittorrent_web_ui_port", "")
        self.web_ui_username = config.get("qbittorrent_web_ui_username", "")
        self.web_ui_password = config.get("qbittorrent_web_ui_password", "")
        self.duration = config.get("duration", 30)
        self.custom_trackers = config.get("tracker_list", [])
        self.meta_timeout = config.get("meta_timeout", 60)
        self.test_path = config.get("test_path", None)
        self.download_path = config.get("download_path", None)
        logger.info("插件 [qBittorrent Bridge] 已初始化。")

    async def initialize(self):
        try:
            self.client = qbittorrentapi.Client(host=self.web_ui_host,
                                                port=self.web_ui_port,
                                                username=self.web_ui_username,
                                                password=self.web_ui_password)
            version = await asyncio.to_thread(lambda: self.client.app.version)
            logger.info(f"✅ 成功连接到 qBittorrent (v{version})")
            api_version = await asyncio.to_thread(lambda: self.client.app.web_api_version)
            logger.info(f"   API 版本: {api_version}")
        except Exception as e:
            logger.error(f"❌ 连接 qBittorrent 失败: {e}")
            logger.error("   请检查：1. qBittorrent 是否已启动？ 2. Web UI 是否已开启？ 3. 端口/账号/密码是否正确？")

    @filter.command("qblogin")
    async def qb_login(self, event: AstrMessageEvent):
        yield event.plain_result("开始重新登陆qBittorrent API")
        self.client = qbittorrentapi.Client(host=self.web_ui_host,
                                            port=self.web_ui_port,
                                            username=self.web_ui_username,
                                            password=self.web_ui_password)
        version = await asyncio.to_thread(lambda: self.client.app.version)
        logger.info(f"✅ 成功连接到 qBittorrent (v{version})")
        api_version = await asyncio.to_thread(lambda: self.client.app.web_api_version)
        logger.info(f"   API 版本: {api_version}")
        yield event.plain_result(f"✅ 成功连接到 qBittorrent (v{version})")

    @filter.command("magtest")
    async def mag_test(self, event: AstrMessageEvent, magnet_link: str):
        info_hash = _extract_hash(magnet_link)
        if not info_hash:
            logger.error("❌ 无效的磁力链接，无法提取 Hash。")
            yield event.plain_result("❌ 无效的磁力链接，无法提取 Hash。")
            return

        # 得加个查询当前任务存不存在，不然慢点把已经下载完的任务给删了，就尴尬了
        t_list = await asyncio.to_thread(self.client.torrents_info, torrent_hashes=info_hash)
        if t_list:
            logger.info(f"任务信息已存在，直接返回任务状态")
            torrent = t_list[0]
            availability = torrent.get('availability', 0)
            final_report = (f"🏁 任务已存在，当前状态:{torrent.state}\n"
                            f"📊 健康度: {availability:.2f}\n"
                            f"🌱 做种人数: {torrent.num_seeds} (已连接) / {torrent.num_complete} (全网发现)\n"
                            f"👥 下载人数: {torrent.num_leechs} (已连接) / {torrent.num_incomplete} (全网发现)\n"
                            f"⬇️ 下载速度: {torrent.dlspeed / 1024:.2f} KB/s")
            yield event.plain_result(final_report)
            return


        logger.info(f"🔍 开始测试，目标 Hash: {info_hash}")
        yield event.plain_result(f"🔍 开始测试，目标 Hash: {info_hash}，注意！该任务将在测试完成后被删除！")

        # 2. 添加任务
        try:
            logger.info("➕ 正在发送任务到 qBittorrent...")
            await asyncio.to_thread(self.client.torrents_add, urls=magnet_link, tags=['magnet_tester_script'], save_path=self.test_path)
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"qBittorrent添加任务失败: {e}")
            yield event.plain_result(f"qBittorrent添加任务失败: {e})")
            return

        logger.info("-" * 10)

        if self.custom_trackers:
            try:
                logger.info(f"📡 注入 {len(self.custom_trackers)} 个自定义 Tracker...")
                await asyncio.to_thread(self.client.torrents_add_trackers, torrent_hash=info_hash, urls=self.custom_trackers)
                await asyncio.to_thread(self.client.torrents_reannounce, torrent_hashes=info_hash)
            except Exception as e:
                logger.warning(f"qBittorrent 注入Tracker异常: {e}")
                yield event.plain_result(f"qBittorrent 注入Tracker异常，使用默认Tracker继续下载: {e}")
        # 4. 等待元数据 (Metadata)
        logger.info("⏳ 正在解析元数据 (等待中)...")

        meta_success, torrents = await self.query_meta_result(info_hash)

        # 循环结束后的判断逻辑
        if meta_success:
            # 这里放置解析成功后的后续处理逻辑
            pass
        else:
            # 处理失败情况
            if not torrents:
                yield event.plain_result("未能获取到任务信息，任务可能添加失败")
            else:
                # 虽然获取到了任务，但在超时时间内元数据仍未就绪
                yield event.plain_result(f"元数据解析超时 ({self.meta_timeout}s)")

        if not meta_success:
            logger.error("❌ 元数据获取超时。该资源可能无人做种。")
            yield event.plain_result("❌ 元数据获取超时。该资源可能无人做种。")
            await self.clean_task(info_hash)
            return

        # 获取详细信息
        t_list = await asyncio.to_thread(self.client.torrents_info, torrent_hashes=info_hash)
        if t_list:
            torrent = t_list[0]
            first_report = (f"✅ 元数据获取成功！\n"
                            f"📦 资源名称: {torrent.name}\n"
                            f"💾 总大小: {torrent.total_size / 1024 / 1024:.2f} MB")
            logger.info("-" * 10)
            logger.info(first_report)
            yield event.plain_result(first_report)
        else:
            yield event.plain_result("未能获取到任务信息，任务可能添加失败")


        # 5. 持续下载测试
        logger.info(f"🚀 开始 {self.duration} 秒下载性能测试...")
        await asyncio.sleep(self.duration)
        logger.info("-" * 10)

        # 6. 最终报告
        t_list = await asyncio.to_thread(self.client.torrents_info, torrent_hashes=info_hash)
        if t_list:
            torrent = t_list[0]
            final_report = await self.get_final_report(torrent)
            yield event.plain_result(final_report)

        await self.clean_task(info_hash)

    async def get_final_report(self, torrent) -> str:
        availability = torrent.get('availability', 0)
        final_report = (f"🏁 [{self.duration} 秒测试报告]\n"
                        f"📊 健康度: {availability:.2f}\n"
                        f"🌱 做种人数: {torrent.num_seeds} (已连接) / {torrent.num_complete} (全网发现)\n"
                        f"👥 下载人数: {torrent.num_leechs} (已连接) / {torrent.num_incomplete} (全网发现)\n"
                        f"⬇️ 最终下载速度: {torrent.dlspeed / 1024:.2f} KB/s\n"
                        f"📥 {self.duration} 秒实际下载量: {torrent.downloaded / 1024 / 1024:.2f} MB\n")
        if availability < 1.0:
            final_report = final_report + "⚠️ 警告：健康度小于 1.0，说明全网可能没有完整资源。\n"
        else:
            final_report = final_report + "✅ 资源健康，理论上可完整下载。\n"
        return final_report

    async def clean_task(self, info_hash: str):
        try:
            logger.info("-" * 10)
            logger.info("🧹 清理中：删除测试任务及下载文件...")
            await asyncio.to_thread(self.client.torrents_delete, torrent_hashes=info_hash, delete_files=True)
            logger.info("✅ 测试结束，清理完成。")
        except Exception as e:
            #如果清理失败，只记录错误日志。一般情况不会发生。
            logger.error(f"❌ 清理任务失败,{e}。")


    async def query_meta_result(self, info_hash: str) -> tuple[bool, Any]:
        meta_success = False
        start_time = time.time()
        poll_interval = 2  # 设置轮询间隔，例如每 2 秒检查一次
        torrents = []  # 初始化变量，防止循环未执行导致变量未定义

        # 循环轮询逻辑
        while time.time() - start_time < self.meta_timeout:
            # 获取任务信息
            torrents = await asyncio.to_thread(self.client.torrents_info, torrent_hashes=info_hash)

            if torrents:
                torrent = torrents[0]
                # 检查是否解析完成 (状态不再是 metaDL 且 获取到了文件大小)
                if torrent.state != 'metaDL' and torrent.total_size > 0:
                    meta_success = True
                    logger.info(f"✅ 元数据解析成功: {torrent.name}")
                    break  # 成功获取，立即跳出循环，不再等待
            await asyncio.sleep(poll_interval)
        return meta_success, torrents

    @filter.command("magadd")
    async def mag_add(self, event: AstrMessageEvent, magnet_link: str):
        info_hash = _extract_hash(magnet_link)
        if not info_hash:
            logger.error("❌ 无效的磁力链接，无法提取 Hash。")
            yield event.plain_result("❌ 无效的磁力链接，无法提取 Hash。")
            return

        logger.info("➕ 正在发送任务到 qBittorrent...")
        try:
            await asyncio.to_thread(self.client.torrents_add, urls=magnet_link, tags=['magnet_tester_script'],
                                    save_path=self.download_path)
            yield event.plain_result(f"✅ 任务已发送至 qBittorrent，任务hash:{info_hash}。")
            if self.custom_trackers:
                logger.info(f"📡 注入 {len(self.custom_trackers)} 个自定义 Tracker...")
                await asyncio.to_thread(self.client.torrents_add_trackers, torrent_hash=info_hash, urls=self.custom_trackers)
                await asyncio.to_thread(self.client.torrents_reannounce, torrent_hashes=info_hash)
        except Exception as e:
            logger.warning(f"qBittorrent添加任务失败: {e}")
            yield event.plain_result(f"qBittorrent添加任务失败: {e})")
        return

    @filter.command("maginfo")
    async def mag_info(self, event: AstrMessageEvent, info_hash: str):
        torrent_list = await asyncio.to_thread(self.client.torrents_info, torrent_hashes=info_hash)
        if torrent_list:
            torrent = torrent_list[0]
            availability = torrent.get('availability', 0)
            final_report = (f"🏁 [当前任务状态]:{torrent.state}\n"
                            f"📊 健康度: {availability:.2f}\n"
                            f"🌱 做种人数 (Seeds): {torrent.num_seeds} (已连接) / {torrent.num_complete} (全网发现)\n"
                            f"👥 下载人数 (Leechers): {torrent.num_leechs} (已连接) / {torrent.num_incomplete} (全网发现)\n"
                            f"⬇️ 下载速度: {torrent.dlspeed / 1024:.2f} KB/s")
            yield event.plain_result(final_report)
        else:
            yield event.plain_result(f"没有找到任务:{info_hash}")


    async def terminate(self):
        if self.client:
            self.client = None
            logger.info("qBittorrent Bridge 插件已卸载，Api Client 客户端已关闭。")
