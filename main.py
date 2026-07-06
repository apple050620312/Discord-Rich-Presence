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

    async def heartbeat(self):
        """背景任務：定時發送心跳包"""
        while True:
            try:
                if self.ws and not self.ws.closed:
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
        
        presence_payload = {
            "status": self.template.get("status", "online"),
            "since": int(time.time() * 1000),
            "activities": self.template.get("activities", []),
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
