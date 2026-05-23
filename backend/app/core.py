import requests
import json
import time
import random
import logging
import base64
from datetime import datetime
from typing import Optional, Dict, Any
from Crypto.Cipher import PKCS1_v1_5 as Cipher_pksc1_v1_5
from Crypto.PublicKey import RSA

from app.traceint_client import normalize_checkin_session_id

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WegolibCore:
    PUBLIC_KEY_STR = 'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0dmmkW4xPa+HhBTyaa0dgAb0fVZRS67jK4y15BQthjJ/ZuUZQmrbGqhG7rwnxfm7g+nFH9zEyRU5KLX3ty9jpNrPjyg7FBF9OvBDYHEt83b77W3mfBjpmoTJOt27E7RZ4InHqJQjqSEo4bw1PDz2OBmtlNIlXMu0VA8I0Bh39hBBnm0oouRV7FdqEzAp8nsF7a3VuBYpx9xek+cRVip0pMXI1AXM6bmyWWNzV0oikQW4ZIbutgDziTMeW28zl/hRbW9Ht34w0sWYyxumuLr1qweW3qnxycn3zn47weFYe6nJp71z+lgVtNTGtowNPPqBLXqusvwf+uNhSy1wKQFpUwIDAQAB'
    
    BASE_URL = "https://wechat.v2.traceint.com/index.php"
    DEVICES_URL = f"{BASE_URL}/wxApp/devices.html"
    SIGN_URL = f"{BASE_URL}/wxApp/sign.html"
    GET_TIME_URL = f"{BASE_URL}/wxApp/getTime.html"
    MINIPROGRAM_REFERER = "https://servicewechat.com/wx3b9352e6b254ed2b/25/page-frame.html"

    def __init__(self, session_id: str):
        self.session_id = normalize_checkin_session_id(session_id)
        self._base_headers = {
            'Host': 'wechat.v2.traceint.com',
            'Connection': 'keep-alive',
            'Accept': '*/*',
            'App-Version': '2.2.5',
            'Accept-Language': 'zh-CN,zh-Hans;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Origin': 'https://web.traceint.com',
            'Referer': self.MINIPROGRAM_REFERER,
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.67(0x18004239) NetType/WIFI Language/zh_CN',
        }
        self.session = requests.Session()
        self.session.headers.update(self._base_headers)

    def _extract_wechat_sess_id(self) -> Optional[str]:
        for part in self.session_id.split(';'):
            part = part.strip()
            if part.startswith('wechatSESS_ID='):
                return part.split('=', 1)[1]
        return None

    def _wxapp_headers(self, *, with_cookie: bool = False) -> dict[str, str]:
        headers = {
            **self._base_headers,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Sec-Fetch-Site': 'same-site',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
            'Priority': 'u=3, i',
        }
        if with_cookie and self.session_id:
            headers['Cookie'] = self.session_id
        return headers

    def _update_cookie(self, new_cookies: requests.cookies.RequestsCookieJar):
        """Update internal session ID from response cookies"""
        if not new_cookies:
            return
            
        current_dict: dict[str, str] = {}
        if self.session_id:
            for part in self.session_id.split(';'):
                if '=' in part:
                    k, v = part.strip().split('=', 1)
                    if k != 'Authorization':
                        current_dict[k] = v
        
        new_dict = new_cookies.get_dict()
        for key, value in new_dict.items():
            if key != 'Authorization':
                current_dict[key] = value
        
        ordered = ['wechatSESS_ID', 'SERVERID']
        self.session_id = '; '.join(
            f"{k}={current_dict[k]}" for k in ordered if k in current_dict
        )
        
        # Log if wechatSESS_ID changed
        if 'wechatSESS_ID' in new_dict:
            logger.info(f"wechatSESS_ID updated: {new_dict['wechatSESS_ID'][:10]}...")
            
        return self.session_id

    def keep_alive(self) -> dict:
        """
        Execute keep-alive logic using devices.html
        """
        result = {
            "success": False,
            "message": "",
            "new_session_id": None
        }
        
        try:
            sess_id_val = self._extract_wechat_sess_id()
            if not sess_id_val:
                result["message"] = "Invalid Cookie: wechatSESS_ID not found"
                return result

            # Simulate delay
            time.sleep(random.uniform(0.5, 1.5))
            
            # Post to devices.html（仅带 wechatSESS_ID Cookie，与 FuckLib 一致）
            r = requests.post(
                self.DEVICES_URL,
                data={'t': sess_id_val},
                headers=self._wxapp_headers(with_cookie=True),
                timeout=10,
            )
            r.raise_for_status()
            
            # Update cookie
            old_session_id = self.session_id
            new_cookie = self._update_cookie(r.cookies)
            if new_cookie and new_cookie != old_session_id:
                result["new_session_id"] = new_cookie

            data = r.json()
            if data.get('code') == 0:
                result["success"] = True
                result["message"] = "Session renewed successfully"
                logger.info("Keep-alive success")
            else:
                result["message"] = f"Server returned error: {data}"
                logger.warning(f"Keep-alive failed: {data}")

        except Exception as e:
            result["message"] = f"Request failed: {str(e)}"
            logger.error(f"Keep-alive exception: {e}")
            
        return result

    def _encrypt(self, password: str) -> str:
        key = '-----BEGIN PUBLIC KEY-----\n' + self.PUBLIC_KEY_STR + '\n-----END PUBLIC KEY-----'
        rsakey = RSA.importKey(key)
        cipher = Cipher_pksc1_v1_5.new(rsakey)
        cipher_text = base64.b64encode(cipher.encrypt(password.encode()))
        return cipher_text.decode()

    def sign_in(self, major: int, minor: int) -> dict:
        """
        Execute Bluetooth check-in
        """
        result = {
            "success": False,
            "message": ""
        }
        
        try:
            sign_headers = self._wxapp_headers(with_cookie=False)

            # 1. Get Time（签到接口不传 Cookie，凭据走 POST body 的 t 字段）
            r_time = requests.get(self.GET_TIME_URL, headers=sign_headers, timeout=10)
            r_time.raise_for_status()
            timestamp = r_time.text
            
            # 2. Encrypt Time
            password = self._encrypt(timestamp)
            
            # 3. Prepare Data
            sess_id_val = self._extract_wechat_sess_id()
            if not sess_id_val:
                result["message"] = "Invalid Cookie: wechatSESS_ID not found"
                return result

            device_info = [{
                "minor": int(minor),
                "rssi": -random.randint(60, 80),
                "major": int(major),
                "proximity": 2,
                "accuracy": random.uniform(1.0, 5.0),
                "uuid": "fda50693-a4e2-4fb1-afcf-c6eb07647825"
            }]
            
            payload = {
                't': sess_id_val,
                'devices': json.dumps(device_info),
                'pass': password
            }
            
            # 4. Post Sign
            r = requests.post(self.SIGN_URL, data=payload, headers=sign_headers, timeout=15)
            
            try:
                data = r.json()
            except:
                data = {"msg": r.text, "code": r.status_code}
                
            code = data.get('code')
            msg = data.get('msg') or data.get('message') or str(data)
            
            if str(code) in ['0', '200']:
                result["success"] = True
                final_msg = msg
                if final_msg == "扫码成功":
                    final_msg = "到馆验证成功"
                result["message"] = f"签到成功：{final_msg}"
            else:
                result["message"] = f"签到失败: {msg}"
                
        except Exception as e:
            result["message"] = f"签到异常: {str(e)}"
            logger.error(f"Sign-in exception: {e}")
            
        return result
