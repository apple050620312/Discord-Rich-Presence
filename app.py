import asyncio
import json
import logging
import os
import time
import random
import urllib.request
import websockets

# 設定日誌格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

GATEWAY_URL = "wss://gateway.discord.gg/?v=9&encoding=json"

class DiscordPresenceClient:
    def __init__(self, token, template, is_bot, index):
        self.token = token.strip('"\' \t\r\n')
        self.template = template
        self.is_bot = is_bot
        self.index = index
        self.logger = logging.getLogger(f"Account-{index+1}")
        
        self.ws = None
        self.heartbeat_interval = 41250
        self.heartbeat_task = None
        self.sequence = None
        self.script_start_time = int(time.time() * 1000)

    async def heartbeat(self):
        """背景任務：定時發送心跳包"""
        # Discord API 要求第一次心跳需加上隨機的 jitter 延遲，以避免伺服器被突發流量衝擊
        jitter = random.uniform(0, 1)
        await asyncio.sleep((self.heartbeat_interval / 1000) * jitter)
        
        while True:
            try:
                if self.ws:
                    payload = {
                        "op": 1,
                        "d": self.sequence
                    }
                    await self.ws.send(json.dumps(payload))
                    self.logger.debug("Sent Heartbeat")
                await asyncio.sleep(self.heartbeat_interval / 1000)
            except Exception as e:
                self.logger.error(f"Heartbeat error: {e}")
                break

    async def identify(self):
        """發送認證與狀態資訊"""
        auth_token = self.token
        if self.is_bot:
            auth_token = f"Bot {auth_token}"
            
        payload = {
            "op": 2,
            "d": {
                "token": auth_token,
                "capabilities": 16381,
                "properties": {
                    "os": "Windows",
                    "browser": "Chrome",
                    "device": "",
                    "system_locale": "en-US",
                    "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "browser_version": "120.0.0.0",
                    "os_version": "10",
                    "referrer": "",
                    "referring_domain": "",
                    "referrer_current": "",
                    "referring_domain_current": "",
                    "release_channel": "stable",
                    "client_build_number": 250000,
                    "client_event_source": None
                },
                "compress": False
            }
        }
        if self.is_bot:
            payload["d"]["intents"] = 0  # 0 indicates minimal intents, required for bot tokens
            
        await self.ws.send(json.dumps(payload))
        self.logger.info("Sent Identify payload")

    async def resolve_asset(self, app_id, key):
        if not app_id or not key or str(key).startswith("http"):
            return key
            
        def fetch():
            try:
                url = f"https://discord.com/api/v9/oauth2/applications/{app_id}/assets"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read().decode())
                    for asset in data:
                        if asset.get("name") == key:
                            return asset.get("id")
            except Exception as e:
                self.logger.warning(f"Failed to resolve asset key '{key}': {e}")
            return key
            
        return await asyncio.to_thread(fetch)

    async def send_presence(self):
        """發送 OP 3 Presence Update"""
        activity_type_map = {
            "Playing": 0,
            "Streaming": 1,
            "Listening": 2,
            "Watching": 3,
            "Competing": 5
        }
        
        act_type_str = self.template.get("activity_type", "Playing")
        act_type = activity_type_map.get(act_type_str, 0)
        
        activity = {
            "name": self.template.get("application_name", "Rich Presence"),
            "type": act_type,
            "flags": 1
        }
        
        app_id = self.template.get("application_id")
        if app_id:
            activity["application_id"] = str(app_id)
            
        if self.template.get("detail_line_1"):
            activity["details"] = self.template.get("detail_line_1")
            
        if self.template.get("state_line_2"):
            activity["state"] = self.template.get("state_line_2")
            
        if self.template.get("stream_link") and act_type == 1:
            activity["url"] = self.template.get("stream_link")
            
        p_size = self.template.get("party_size")
        p_max = self.template.get("maximum_party_size")
        if p_size is not None or p_max is not None:
            activity["party"] = {
                "size": [
                    int(p_size) if p_size is not None else 1,
                    int(p_max) if p_max is not None else 1
                ]
            }
            
        assets = {}
        large_key = self.template.get("large_image_url_key")
        if large_key:
            if not str(large_key).startswith("http") and app_id:
                large_key = await self.resolve_asset(app_id, large_key)
            assets["large_image"] = large_key
            
        if self.template.get("large_image_text"):
            assets["large_text"] = self.template.get("large_image_text")
        if self.template.get("large_image_clickable_url"):
            assets["large_url"] = self.template.get("large_image_clickable_url")
            
        small_key = self.template.get("small_image_url_key")
        if small_key:
            if not str(small_key).startswith("http") and app_id:
                small_key = await self.resolve_asset(app_id, small_key)
            assets["small_image"] = small_key
            
        if self.template.get("small_image_text"):
            assets["small_text"] = self.template.get("small_image_text")
        if self.template.get("small_image_clickable_url"):
            assets["small_url"] = self.template.get("small_image_clickable_url")
            
        if assets:
            activity["assets"] = assets
            
        timestamp_mode = self.template.get("timestamp_mode", "None")
        timestamps = {}
        if timestamp_mode == "Custom":
            if self.template.get("start_timestamp"):
                timestamps["start"] = int(self.template.get("start_timestamp"))
            if self.template.get("end_timestamp"):
                timestamps["end"] = int(self.template.get("end_timestamp"))
        elif timestamp_mode == "Since discord open":
            timestamps["start"] = self.script_start_time
        elif "Same as your current time" in timestamp_mode:
            now = time.localtime()
            midnight_offset = (now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec) * 1000
            timestamps["start"] = int(time.time() * 1000) - midnight_offset
            
        if timestamps:
            activity["timestamps"] = timestamps
            
        button_texts = []
        button_urls = []
        if self.template.get("button1_text"):
            button_texts.append(str(self.template.get("button1_text"))[:32])
            button_urls.append(str(self.template.get("button1_url", "")))
        if self.template.get("button2_text"):
            button_texts.append(str(self.template.get("button2_text"))[:32])
            button_urls.append(str(self.template.get("button2_url", "")))
            
        if button_texts:
            activity["buttons"] = button_texts
            activity["metadata"] = {
                "button_urls": button_urls
            }
            
        presence_payload = {
            "op": 3,
            "d": {
                "status": self.template.get("status", "online"),
                "since": 0,
                "activities": [activity],
                "afk": False
            }
        }
        
        await self.ws.send(json.dumps(presence_payload))
        self.logger.info("Sent OP 3 Presence Update")

    async def connect(self):
        """連接並處理 WebSocket 訊息循環"""
        while True:
            try:
                self.logger.info("Connecting to Discord Gateway...")
                # 加入 max_size=None 避免帳號伺服器過多導致 READY 封包超過 1MB 限制而被強制斷開
                connect_url = self.resume_gateway_url if hasattr(self, 'resume_gateway_url') and self.resume_gateway_url else GATEWAY_URL
                
                async with websockets.connect(connect_url, max_size=None) as ws:
                    self.ws = ws
                    async for message in ws:
                        data = json.loads(message)
                        op = data.get("op")
                        if data.get("s") is not None:
                            self.sequence = data.get("s")
                        
                        if op == 10:  # Hello
                            self.heartbeat_interval = data["d"]["heartbeat_interval"]
                            self.logger.info(f"Received Hello. Heartbeat interval: {self.heartbeat_interval}ms")
                            
                            if self.heartbeat_task:
                                self.heartbeat_task.cancel()
                            self.heartbeat_task = asyncio.create_task(self.heartbeat())
                            
                            if hasattr(self, 'session_id') and self.session_id:
                                # 嘗試恢復連線 (Resume) 避免重新下載巨大封包
                                self.logger.info(f"Attempting to resume session {self.session_id}...")
                                resume_payload = {
                                    "op": 6,
                                    "d": {
                                        "token": self.token,
                                        "session_id": self.session_id,
                                        "seq": self.sequence
                                    }
                                }
                                await self.ws.send(json.dumps(resume_payload))
                            else:
                                await self.identify()
                            
                        elif op == 11:  # Heartbeat ACK
                            self.logger.debug("Received Heartbeat ACK")
                            
                        elif op == 0:  # Dispatch
                            event_type = data.get("t")
                            if event_type == "READY":
                                user = data["d"]["user"]
                                self.session_id = data["d"]["session_id"]
                                self.resume_gateway_url = data["d"]["resume_gateway_url"]
                                self.logger.info(f"Successfully connected and ready as: {user.get('username')}#{user.get('discriminator')}")
                                await self.send_presence()
                            elif event_type == "RESUMED":
                                self.logger.info("Session successfully resumed! Avoided re-downloading initial payload.")
                                # 恢復連線後，保持原有的 Presence 狀態即可
                                
                        elif op == 7:  # Reconnect
                            self.logger.info("Gateway requested reconnect. Reconnecting...")
                            break
                        elif op == 9:  # Invalid Session
                            self.logger.warning("Invalid Session. Re-identifying...")
                            # 如果 Session 無效，清空 session_id 強制重新 Identify
                            self.session_id = None
                            self.resume_gateway_url = None
                            await asyncio.sleep(random.uniform(1, 5))
                            break
                            
            except websockets.exceptions.ConnectionClosed as e:
                self.logger.warning(f"Connection closed (code: {e.code}, reason: {e.reason}). Reconnecting in 5s...")
                if self.heartbeat_task:
                    self.heartbeat_task.cancel()
                await asyncio.sleep(5)
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}. Reconnecting in 5s...")
                if self.heartbeat_task:
                    self.heartbeat_task.cancel()
                await asyncio.sleep(5)

async def start_account(client, index):
    if index > 0:
        await asyncio.sleep(index * 6)  # 避免多個帳號同時 Identify 被 Discord 限流
    await client.connect()

async def main():
    config_path = "config.json"
    if not os.path.exists(config_path):
        logging.error("找不到 config.json。請複製 config.example.json 並命名為 config.json 後填入您的設定。")
        return

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        logging.error(f"讀取 config.json 失敗: {e}")
        return

    templates = config.get("templates", {})
    accounts = config.get("accounts", [])

    if not accounts:
        logging.error("在設定檔中找不到任何帳號。")
        return

    tasks = []
    for i, acc in enumerate(accounts):
        token = acc.get("token")
        template_name = acc.get("template")
        is_bot = acc.get("is_bot", False)

        if not token:
            logging.warning(f"帳號 {i+1} 缺少 token，跳過。")
            continue

        template = templates.get(template_name)
        if not template:
            logging.warning(f"帳號 {i+1} 指定的範本 '{template_name}' 不存在，跳過。")
            continue

        client = DiscordPresenceClient(token, template, is_bot, i)
        tasks.append(asyncio.create_task(start_account(client, i)))

    if not tasks:
        logging.error("沒有可執行的帳號任務。")
        return

    logging.info(f"正在啟動 {len(tasks)} 個帳號的 Presence 腳本...")
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("使用者中斷程式。")
