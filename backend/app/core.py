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
        self.session_id = session_id
        # Use iOS 18.7 / WeChat 8.0.67 fingerprint from HAR
        self.headers = {
            'Host': 'wechat.v2.traceint.com',
            'Connection': 'keep-alive',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': '*/*',
            'App-Version': '2.2.5',
            'Sec-Fetch-Site': 'same-site',
            'Priority': 'u=3, i',
            'Accept-Language': 'zh-CN,zh-Hans;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Sec-Fetch-Mode': 'cors',
            'Origin': 'https://web.traceint.com',
            'Referer': self.MINIPROGRAM_REFERER,
            'Sec-Fetch-Dest': 'empty',
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.67(0x18004239) NetType/WIFI Language/zh_CN',
            'Cookie': self.session_id
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _update_cookie(self, new_cookies: requests.cookies.RequestsCookieJar):
        """Update internal session ID from response cookies"""
        if not new_cookies:
            return
            
        current_dict = {}
        if self.session_id:
            for part in self.session_id.split(';'):
                if '=' in part:
                    k, v = part.strip().split('=', 1)
                    current_dict[k] = v
        
        new_dict = new_cookies.get_dict()
        current_dict.update(new_dict)
        
        # Reconstruct
        self.session_id = '; '.join([f"{k}={v}" for k, v in current_dict.items()])
        self.headers['Cookie'] = self.session_id
        self.session.headers['Cookie'] = self.session_id
        
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
            # Extract pure ID for the body
            sess_id_val = None
            for part in self.session_id.split(';'):
                if part.strip().startswith('wechatSESS_ID='):
                    sess_id_val = part.strip().split('=', 1)[1]
                    break
            
            if not sess_id_val:
                result["message"] = "Invalid Cookie: wechatSESS_ID not found"
                return result

            # Simulate delay
            time.sleep(random.uniform(0.5, 1.5))
            
            # Post to devices.html
            r = self.session.post(
                self.DEVICES_URL,
                data={'t': sess_id_val},
                timeout=10
            )
            r.raise_for_status()
            
            # Update cookie
            new_cookie = self._update_cookie(r.cookies)
            if new_cookie != self.session_id:
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
            # 1. Get Time
            r_time = self.session.get(self.GET_TIME_URL)
            r_time.raise_for_status()
            timestamp = r_time.text
            
            # 2. Encrypt Time
            password = self._encrypt(timestamp)
            
            # 3. Prepare Data
            sess_id_val = None
            for part in self.session_id.split(';'):
                if part.strip().startswith('wechatSESS_ID='):
                    sess_id_val = part.strip().split('=', 1)[1]
                    break
            
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
            r = self.session.post(self.SIGN_URL, data=payload)
            
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
                result["message"] = f"签到失败 ({code}): {msg}"
                
        except Exception as e:
            result["message"] = f"签到异常: {str(e)}"
            logger.error(f"Sign-in exception: {e}")
            
        return result
