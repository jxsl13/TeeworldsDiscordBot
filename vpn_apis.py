# http requests for vpn checks
import aiohttp
from shared import log

# cooldown stuff
from datetime import datetime, timedelta

class CooldownHandler:

    def __init__(self):
        self.last_retry = 0
        self.cooldown_secs = 0
    
    def reset_cooldown(self):
        self.last_retry = 0
        self.cooldown_secs = 0
    
    def increase_cooldown(self):
        self.last_retry = int(datetime.now().timestamp())
        if self.cooldown_secs == 0:
            self.cooldown_secs += 1
        else:
            self.cooldown_secs *= 2
    
    def can_retry(self) -> bool:
        now_timestamp = int(datetime.now().timestamp())

        expires = datetime.fromtimestamp(self.last_retry) + timedelta(seconds=self.cooldown_secs)
        expires_timestamp = int(expires.timestamp())

        if now_timestamp >= expires_timestamp:
            return True
        else:
            return False
    def get_remaining_cooldown(self):
        now = datetime.now()
        expires = datetime.fromtimestamp(self.last_retry) + timedelta(seconds=self.cooldown_secs)

        if expires >= now:
            return (expires - now).total_seconds() // 1
        else:
            return 0





class API_GetIPIntel_Net(CooldownHandler):

    def __init__(self, email, vpn_threshold=0.9):
        super().__init__()
        self.session = None
        self.email = email
        self.threshold = vpn_threshold
        

    async def __connect(self):
        self.session = aiohttp.ClientSession()

    async def __close(self):
        await self.session.close() 


    async def __fetch(self, ip : str) -> str:
        params = {
            'ip' : ip,
            'contact' : self.email
        }

        async with self.session.get("http://check.getipintel.net/check.php", params=params) as response:
            if response.status == 200:
                self.reset_cooldown()
                return await response.text(encoding='utf-8')
            elif response.status == 400:
                error_code = await response.text(encoding='utf-8')
                try:
                    error_code = int(error_code)
                except:
                    pass
                    
                if error_code == -1:
                    log("ERROR", f"(API_GetIPIntel_Net)[{response.status}]: Invalid no input")
                elif error_code == -2:
                    log("ERROR", f"(API_GetIPIntel_Net)[{response.status}]: Invalid IP address")
                elif error_code == -3:
                    log("ERROR", f"(API_GetIPIntel_Net)[{response.status}]: Unroutable address / private address")
                elif error_code == -4:
                    log("ERROR", f"(API_GetIPIntel_Net)[{response.status}]: Unable to reach database, most likely the database is being updated. Keep an eye on twitter for more information.")
                elif error_code == -5:
                    log("ERROR", f"(API_GetIPIntel_Net)[{response.status}]: Your connecting IP has been banned from the system or you do not have permission to access a particular service. Did you exceed your query limits? Did you use an invalid email address? If you want more information, please use the contact links below.")
                elif error_code == -6:
                    log("ERROR", f"(API_GetIPIntel_Net)[{response.status}]: You did not provide any contact information with your query or the contact information is invalid.")
                else:
                    log("ERROR", f"(API_GetIPIntel_Net)[{response.status}]: {error_code}")

            elif response.status == 429:
                log("ERROR", f"(API_GetIPIntel_Net)[{response.status}]: If you exceed the number of allowed queries, you'll receive a HTTP 429 error.")
            else:
                text = await response.text(encoding='utf-8')
                log("ERROR", f"(API_GetIPIntel_Net)[{response.status}]: {text}")

        # error case, increase cooldown and set new retry
        self.increase_cooldown()
        return None   

    async def is_vpn(self, ip : str) -> (bool, bool):
        """
            returns (error, is_vpn)
        """
        if self.can_retry():

            await self.__connect()
            text = await self.__fetch(ip)
            await self.__close()

            if text == None:
                return(True, False)
            
            result = float(text)

            if 0.0 <= result <= 1.0 and result >= self.threshold:
                return (False, True)
            elif 0.0 <= result <= 1.0 and result < self.threshold:
                return (False, False)
        else:
            return (True, False)
            


class API_IPHub(CooldownHandler):

    def __init__(self, api_key):
        super().__init__()
        self.session = None
        self.api_key = api_key


    async def __connect(self):
        self.session = aiohttp.ClientSession()

    async def __close(self):
        await self.session.close() 


    async def __fetch(self, ip : str) -> str:
        headers = {
            'X-Key' : self.api_key
        }

        async with self.session.get(f"http://v2.api.iphub.info/ip/{ip}", headers=headers) as response:
            if response.status == 200:
                json =  await response.json()
                self.reset_cooldown()
                return json['block']
            else:
                text = await response.text(encoding='utf-8')
                log("ERROR", f"(API_IPHub)[{response.status}]: {text}")
        
        self.increase_cooldown()
        return None   

    async def is_vpn(self, ip : str) -> (bool, bool):
        """
            returns (error, is_vpn)
        """

        if self.can_retry():
            await self.__connect()
            text = await self.__fetch(ip)
            await self.__close()

            if text == None:
                return (True, False)

            result = int(text)

            if result in [0, 1, 2]:
                if result in [0, 2]:
                    return (False, False)
                else:
                    return (False, True)
            else:
                log("ERROR_Unexpected", f"(API_IPHub): {text}")
                return (True, False)
        else:
            return (True, False)


class API_IP_Teoh_IO(CooldownHandler):

    def __init__(self):
        super().__init__()
        self.session = None


    async def __connect(self):
        self.session = aiohttp.ClientSession()

    async def __close(self):
        await self.session.close() 


    async def __fetch(self, ip : str) -> bool:
        
        async with self.session.get(f"https://ip.teoh.io/api/vpn/{ip}") as response:
            if response.status == 200:
                try:
                    json = await response.json(content_type='text/plain')
                    is_hosting = int(json['is_hosting']) == 1
                    vpn_or_proxy = json['vpn_or_proxy'] == "yes"
                    self.reset_cooldown()
                    return is_hosting or vpn_or_proxy
                except Exception:
                    text = await response.text(encoding='utf-8')
                    log("ERROR",  f"(API_IP_Teoh_IO): {text}")

            else:
                text = await response.text(encoding='utf-8')
                log("ERROR", f"(API_IP_Teoh_IO)[{response.status}]: {text}")

        self.increase_cooldown()
        return None   

    async def is_vpn(self, ip : str) -> (bool, bool):
        """
            returns (error, is_vpn)
        """
        if self.can_retry():
            await self.__connect()
            result = await self.__fetch(ip)
            await self.__close()

            if result == None:
                return (True, False)
            else:
                return (False, result)
        else:
            return (True, False)

