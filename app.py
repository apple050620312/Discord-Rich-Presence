import asyncio
import json
import logging
import os
import time
import sys

import websockets

# 設定日誌格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

GATEWAY_URL = "wss://gateway.discord.gg/?v=9&encoding=json"

class DiscordPresenceClient:
    def __init__(self, token: str, template: dict, is_bot: bool, account_index: int):
        self.token = token
        self.template = template
        self.is_bot = is_bot
        self.account_index = account_index
        self.logger = logging.getLogger(f"Account-{account_index + 1}")
        self.heartbeat_interval = 41.25  # 預設值，會被 Hello 事件覆寫
        self.ws = None
        self.heartbeat_task = None
        self.sequence = None
        self.script_start_time = int(time.time() * 1000)

    async def heartbeat(self):
        """背景任務：定時發送心跳包"""
        while True:
            try:
                if self.ws:
                    payload = {
                        "op": 1,
                        "d": self.sequence
                    }
                    await self.ws.send(json.dumps(payload))
                    self.logger.debug("Sent Heartbeat")
                # 乘以 0.9 加上一些 jitter 以確保在逾時前送達 (Discord 建議做法為 jitter，這裡是簡單提早發送)
                await asyncio.sleep(self.heartbeat_interval * 0.9 / 1000)
            except Exception as e:
                self.logger.error(f"Heartbeat error: {e}")
                break

    async def identify(self):
        """發送認證與狀態資訊"""
        auth_token = f"Bot {self.token}" if self.is_bot else self.token
        
        # 對應 Activity Type
        activity_type_map = {
            "Playing": 0,
            "Streaming": 1,
            "Listening": 2,
            "Watching": 3,
            "Competing": 5
        }
        
        act_type_str = self.template.get("activity_type", "Playing")
        act_type = activity_type_map.get(act_type_str, 0)
        
        # 建立基礎活動屬性
        activity = {
            "name": self.template.get("application_name", "Rich Presence"),
            "type": act_type
        }
        
        if self.template.get("application_id"):
            activity["application_id"] = str(self.template.get("application_id"))
            
        if self.template.get("detail_line_1"):
            activity["details"] = self.template.get("detail_line_1")
            
        if self.template.get("state_line_2"):
            activity["state"] = self.template.get("state_line_2")
            
        if self.template.get("stream_link") and act_type == 1:
            activity["url"] = self.template.get("stream_link")
            
        # Party Size
        p_size = self.template.get("party_size")
        p_max = self.template.get("maximum_party_size")
        if p_size is not None or p_max is not None:
            activity["party"] = {
                "size": [
                    int(p_size) if p_size is not None else 1,
                    int(p_max) if p_max is not None else 1
                ]
            }
            
        # Assets (Large Image & Small Image)
        assets = {}
        if self.template.get("large_image_url_key"):
            assets["large_image"] = self.template.get("large_image_url_key")
        if self.template.get("large_image_text"):
            assets["large_text"] = self.template.get("large_image_text")
        if self.template.get("large_image_clickable_url"):
            assets["large_url"] = self.template.get("large_image_clickable_url")
            
        if self.template.get("small_image_url_key"):
            assets["small_image"] = self.template.get("small_image_url_key")
        if self.template.get("small_image_text"):
            assets["small_text"] = self.template.get("small_image_text")
        if self.template.get("small_image_clickable_url"):
            assets["small_url"] = self.template.get("small_image_clickable_url")
            
        if assets:
            activity["assets"] = assets
            
        # Timestamps
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
            # Vencord 計算方式：從當天午夜開始算
            now = time.localtime()
            midnight_offset = (now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec) * 1000
            timestamps["start"] = int(time.time() * 1000) - midnight_offset
            
        if timestamps:
            activity["timestamps"] = timestamps
            
        # Vencord 特別支援的 URLs
        if self.template.get("detail_url"):
            activity["details_url"] = self.template.get("detail_url")
        if self.template.get("state_url"):
            activity["state_url"] = self.template.get("state_url")
            
        # Buttons 處理 (User Token 的格式必須是陣列字串與 metadata)
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
            "status": self.template.get("status", "online"),
            "since": int(time.time() * 1000),
            "activities": [activity],
            "afk": False
        }
        
        payload = {
            "op": 2,
            "d": {
                "token": auth_token,
                "properties": {
                    "os": "Windows",
                    "browser": "Chrome",
                    "device": ""
                },
                "presence": presence_payload
            }
        }
        
        await self.ws.send(json.dumps(payload))
        self.logger.info("Sent Identify payload with rich presence")

    async def connect(self):
        """連接並處理 WebSocket 訊息循環"""
        while True:
            try:
                self.logger.info("Connecting to Discord Gateway...")
                async with websockets.connect(GATEWAY_URL) as ws:
                    self.ws = ws
                    async for message in ws:
                        data = json.loads(message)
                        op = data.get("op")
                        self.sequence = data.get("s", self.sequence)
                        
                        if op == 10:  # Hello
                            self.heartbeat_interval = data["d"]["heartbeat_interval"]
                            self.logger.info(f"Received Hello. Heartbeat interval: {self.heartbeat_interval}ms")
                            
                            # 啟動心跳任務
                            if self.heartbeat_task:
                                self.heartbeat_task.cancel()
                            self.heartbeat_task = asyncio.create_task(self.heartbeat())
                            
                            # 發送 Identify
                            await self.identify()
                            
                        elif op == 11:  # Heartbeat ACK
                            self.logger.debug("Received Heartbeat ACK")
                            
                        elif op == 0:  # Dispatch (一般事件)
                            event_type = data.get("t")
                            if event_type == "READY":
                                user = data["d"]["user"]
                                self.logger.info(f"Successfully connected and ready as: {user.get('username')}#{user.get('discriminator')}")
                                
                        elif op == 7:  # Reconnect
                            self.logger.info("Gateway requested reconnect. Reconnecting...")
                            break
                        
                        elif op == 9:  # Invalid Session
                            self.logger.warning("Invalid session. Re-identifying...")
                            await asyncio.sleep(2)
                            break # 斷開連接並讓外層迴圈重新連線
                            
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
        tasks.append(client.connect())

    if not tasks:
        logging.error("沒有可執行的帳號任務。")
        return

    logging.info(f"正在啟動 {len(tasks)} 個帳號的 Presence 腳本...")
    # 同時執行所有帳號的連線任務
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("使用者中斷程式。")
