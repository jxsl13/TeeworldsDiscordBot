# http requests for vpn checks
import aiohttp
from shared import log

class API_GetIPIntel_Net:

    def __init__(self, email, vpn_threshold=0.9):
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
                return await response.text(encoding='utf-8')
            else:
                log("ERROR", f"(API_GetIPIntel_Net)[{response.status}]: {response.text}")

        return None   

    async def is_vpn(self, ip : str) -> (bool, bool):
        """
            returns (error, is_vpn)
        """
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
            log("ERROR", f"(API_GetIPIntel_Net): {text}")
            return (True, False)


class API_IPHub:

    def __init__(self, api_key):
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
                return json['block']
            else:
                log("ERROR", f"(API_IPHub)[{response.status}]: {response.text}")

        return None   

    async def is_vpn(self, ip : str) -> (bool, bool):
        """
            returns (error, is_vpn)
        """
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
            log("ERROR", f"(API_IPHub): {text}")
            return (True, False)


class API_IP_Teoh_IO:

    def __init__(self):
        self.session = None


    async def __connect(self):
        self.session = aiohttp.ClientSession()

    async def __close(self):
        await self.session.close() 


    async def __fetch(self, ip : str) -> bool:
        
        async with self.session.get(f"https://ip.teoh.io/api/vpn/{ip}") as response:
            if response.status == 200:
                json =  await response.json(content_type='text/plain')
                is_hosting = int(json['is_hosting']) == 1
                vpn_or_proxy = json['vpn_or_proxy'] == "yes"
                return is_hosting or vpn_or_proxy
            else:
                log("ERROR", f"(API_IP_Teoh_IO)[{response.status}]: {response.text}")

        return None   

    async def is_vpn(self, ip : str) -> (bool, bool):
        """
            returns (error, is_vpn)
        """
        await self.__connect()
        result = await self.__fetch(ip)
        await self.__close()

        if result == None:
            return (True, False)
        else:
            return (False, result)
