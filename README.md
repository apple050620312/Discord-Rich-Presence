# Discord Rich Presence (Multi-Account & Script Only)

這是一個輕量級的 Python 腳本，能讓您在 **不需要開啟 Discord 桌面版應用程式** 的情況下，為多個 Discord 帳號同時掛上自訂的 Rich Presence (豐富狀態)，並支援 24 小時在背景運行。

本專案的設定檔 (`config.json`) 完全相容於 Vencord CustomRPC 插件的設定邏輯，您可以無縫地將您習慣的設定轉移過來！

## 功能特色
- 🚀 **純腳本執行**：直接與 Discord Gateway 連線，無須在背景執行 Discord 用戶端。
- 👥 **多帳號支援**：可同時為多個帳號設定不同的狀態。
- 🎨 **多範本配置**：預先寫好各種狀態（例如：玩遊戲、寫程式、看動漫），並在設定檔中為不同帳號指定不同範本。
- 🔄 **自動重連**：內建斷線重連與心跳包 (Heartbeat) 機制，確保狀態 24 小時穩定顯示。
- 💯 **完美還原 Vencord CustomRPC**：支援大小圖片、雙按鈕、各種 Timestamp 模式等進階設定。

---

## 🛠️ 安裝與啟動教學

### 1. 安裝環境
請確保您的電腦已經安裝 [Python 3.8 或以上版本](https://www.python.org/downloads/)。
打開終端機 (Terminal / 命列提示字元)，進入專案資料夾並安裝依賴套件：

```bash
pip install -r requirements.txt
```

### 2. 準備設定檔
1. 將專案中的 `config.example.json` 複製一份，並將新檔案重新命名為 `config.json`。
2. 用文字編輯器 (如 VSCode, 記事本) 打開 `config.json`。

### 3. 取得您的 Discord Token
> ⚠️ **警告**：您的 Token 等同於您的帳號密碼！請**絕對不要**傳給任何人，也不要截圖外流。直接使用 User Token 屬於 Self-botting，雖然此腳本只做狀態更新，但請自行評估使用風險。

1. 打開瀏覽器並登入 [Discord 網頁版](https://discord.com/app)。
2. 按下 `F12` 開啟開發者工具。
3. 切換到 **Network (網路)** 標籤頁。
4. 按 `F5` 重新整理頁面。
5. 在過濾器 (Filter) 搜尋 `science` 或是隨便點擊列表中的 `messages` 請求。
6. 在右側的 **Headers (標頭)** -> **Request Headers (請求標頭)** 中找到 `Authorization`，後面的字串就是您的 Token。
7. 將取得的 Token 填入 `config.json` 中的 `accounts` -> `token` 欄位裡。

### 4. 設定您的 Rich Presence 範本
在 `config.json` 的 `templates` 區塊中，您可以自由新增或修改狀態。
以下是可用欄位清單（完美對應 Vencord CustomRPC）：

| JSON 欄位名稱 | 對應 UI 名稱 | 說明 |
| :--- | :--- | :--- |
| `activity_type` | Activity Type | `Playing`, `Streaming`, `Listening`, `Watching`, `Competing` |
| `application_id` | Application ID | 您從 Discord Developer Portal 取得的應用程式 ID |
| `application_name` | Application Name | 狀態最上方顯示的粗體應用程式名稱 |
| `detail_line_1` | Detail (line 1) | 狀態的第一行文字 |
| `state_line_2` | State (line 2) | 狀態的第二行文字 |
| `stream_link` | Stream Link | 直播網址 (僅在 `activity_type` 為 Streaming 時有效) |
| `party_size` | Party Size | 隊伍目前人數 (例如：1) |
| `maximum_party_size`| Maximum Party Size | 隊伍最大人數 (例如：4) |
| `large_image_url_key`| Large Image URL/Key | 大圖片的直接網址 (例如 Imgur 連結) 或是 Discord Asset Key |
| `large_image_text` | Large Image Text | 滑鼠移到大圖片上顯示的文字 |
| `large_image_clickable_url`| Large Image clickable URL| 點擊大圖片導向的網址 |
| `small_image_url_key`| Small Image URL/Key | 小圖片的直接網址 或是 Asset Key |
| `small_image_text` | Small Image Text | 滑鼠移到小圖片上顯示的文字 |
| `small_image_clickable_url`| Small Image clickable URL| 點擊小圖片導向的網址 |
| `button1_text` / `button2_text` | Button Text | 按鈕的顯示文字 |
| `button1_url` / `button2_url` | Button URL | 點擊按鈕要前往的網址 |
| `timestamp_mode` | Timestamp Mode | 時間戳模式 (見下方詳細說明) |
| `start_timestamp` | Start Timestamp | 自訂時間戳 (單位：毫秒)，僅在 Custom 模式下有效 |
| `end_timestamp` | End Timestamp | 自訂結束時間戳 (單位：毫秒)，僅在 Custom 模式下有效 |

#### Timestamp Mode (時間戳模式) 支援的字串：
- `"None"`：不顯示時間。
- `"Since discord open"`：顯示為本腳本啟動的當下時間（從 00:00 開始計時）。
- `"Same as your current time"`：Vencord 的 TIME 模式，會計算從當天午夜 00:00 到現在的時間。
- `"Custom"`：使用您填入的 `start_timestamp` 與 `end_timestamp`。

### 5. 執行腳本
設定完成後，在終端機輸入：
```bash
python main.py
```
如果看到 `Successfully connected and ready as: 您的名稱#1234`，就代表成功了！此時您可以關閉 Discord 桌面版，狀態依舊會 24 小時保持連線。若要停止，只需在終端機按下 `Ctrl + C` 即可。
