import discord
import asyncio
import json
import logging
import os
import time
import urllib.request

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s',
    handlers=[logging.StreamHandler()]
)


class CustomRPCClient(discord.Client):
    def __init__(self, account_config, template, index, script_start_time):
        # 停用 chunk_guilds_at_startup 避免大量公會導致啟動超時與 API 限制
        super().__init__(chunk_guilds_at_startup=False)
        
        self.account_config = account_config
        raw_token = account_config.get("token", "")
        self.auth_token = raw_token.strip('"\' \t\r\n')
        self.template = template
        self.is_bot = account_config.get("is_bot", False)
        self.index = index
        self.logger = logging.getLogger(f"Account-{index+1}")
        self.script_start_time = script_start_time

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

    async def on_ready(self):
        self.logger.info(f"Successfully connected and ready as: {self.user}")
        await self.update_status()
        
        if not hasattr(self, 'midnight_task'):
            self.midnight_task = self.loop.create_task(self.midnight_updater())

    async def midnight_updater(self):
        await self.wait_until_ready()
        while not self.is_closed():
            timestamp_mode = self.template.get("timestamp_mode", "None") if self.template else "None"
            if "Same as your current time" in timestamp_mode:
                now = time.localtime()
                seconds_until_midnight = 86400 - (now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec)
                await asyncio.sleep(seconds_until_midnight + 2) # 等到午夜過後兩秒鐘
                self.logger.info("Midnight crossed. Updating timestamps for 'Same as your current time' mode.")
                await self.update_status()
            else:
                break

    async def update_status(self):
        activities_list = []
        
        # 1. 處理自訂狀態 (Custom Status: emoji + text)
        custom_status_text = self.account_config.get("custom_status_text")
        custom_status_emoji = self.account_config.get("custom_status_emoji")
        
        if custom_status_text or custom_status_emoji:
            custom_status_dict = {
                "type": 4,
                "name": "Custom Status",
                "id": "custom"
            }
            if custom_status_text:
                custom_status_dict["state"] = str(custom_status_text)
            if custom_status_emoji:
                import re
                emoji_str = str(custom_status_emoji).strip()
                # 檢查是否為 Discord 自訂表情符號格式 <a:name:id> 或 <:name:id>
                match = re.match(r"<(a?):([a-zA-Z0-9_]+):([0-9]+)>", emoji_str)
                if match:
                    custom_status_dict["emoji"] = {
                        "name": match.group(2),
                        "id": match.group(3),
                        "animated": bool(match.group(1))
                    }
                else:
                    custom_status_dict["emoji"] = {"name": emoji_str}
            activities_list.append(custom_status_dict)

        # 2. 處理 Rich Presence (如果有設定範本的話)
        if self.template:
            activity_type_map = {
                "Playing": 0,
                "Streaming": 1,
                "Listening": 2,
                "Watching": 3,
                "Competing": 5
            }
            
            act_type_str = self.template.get("activity_type", "Playing")
            act_type = activity_type_map.get(act_type_str, 0)
            
            activity_dict = {
                "name": self.template.get("application_name", "Rich Presence"),
                "type": act_type,
                "flags": 1
            }
            
            app_id = self.template.get("application_id")
            if app_id:
                activity_dict["application_id"] = str(app_id)
                
            if self.template.get("detail_line_1"):
                activity_dict["details"] = self.template.get("detail_line_1")
                
            if self.template.get("state_line_2"):
                activity_dict["state"] = self.template.get("state_line_2")
                
            if self.template.get("stream_link") and act_type == 1:
                activity_dict["url"] = self.template.get("stream_link")
                
            p_size = self.template.get("party_size")
            p_max = self.template.get("maximum_party_size")
            if p_size is not None or p_max is not None:
                activity_dict["party"] = {
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
                activity_dict["assets"] = assets
                
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
                activity_dict["timestamps"] = timestamps
                
            button_texts = []
            button_urls = []
            if self.template.get("button1_text"):
                button_texts.append(str(self.template.get("button1_text"))[:32])
                button_urls.append(str(self.template.get("button1_url", "")))
            if self.template.get("button2_text"):
                button_texts.append(str(self.template.get("button2_text"))[:32])
                button_urls.append(str(self.template.get("button2_url", "")))
                
            if button_texts:
                activity_dict["buttons"] = button_texts
                activity_dict["metadata"] = {
                    "button_urls": button_urls
                }
                
            activities_list.append(activity_dict)
            
        status_str = "online"
        if self.template:
            status_str = self.template.get("status", "online")

        # 繞過 discord.py-self 的 change_presence 單一 activity 限制，直接發送 OP 3
        presence_payload = {
            "op": 3,
            "d": {
                "status": status_str,
                "since": 0,
                "activities": activities_list,
                "afk": False
            }
        }
        
        await self.ws.send_as_json(presence_payload)
        self.logger.info("Sent OP 3 Presence Update via ws.send_as_json (Custom Status + RPC)")

async def start_account(client, index):
    if index > 0:
        await asyncio.sleep(index * 6)  # 階梯式啟動避免限流
    try:
        # discord.py-self 移除了 bot 參數，改為透過 "Bot " 前綴自動判斷
        token_to_use = f"Bot {client.auth_token}" if client.is_bot and not client.auth_token.startswith("Bot ") else client.auth_token
        await client.start(token_to_use)
    except Exception as e:
        client.logger.error(f"Failed to start client: {e}")

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

    script_start_time = int(time.time() * 1000)
    tasks = []
    
    for i, acc in enumerate(accounts):
        token = acc.get("token")
        template_name = acc.get("template")

        if not token:
            logging.warning(f"帳號 {i+1} 缺少 token，跳過。")
            continue

        template = templates.get(template_name)
        if not template and template_name:
            logging.warning(f"帳號 {i+1} 指定的範本 '{template_name}' 不存在。")

        client = CustomRPCClient(acc, template, i, script_start_time)
        tasks.append(asyncio.create_task(start_account(client, i)))

    if not tasks:
        logging.error("沒有可執行的帳號任務。")
        return

    logging.info(f"正在啟動 {len(tasks)} 個帳號的 Presence 腳本 (使用 discord.py-self)...")
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("使用者中斷程式。")
