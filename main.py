#!/usr/bin/env python3

# typing
from typing import List, Tuple, Dict

# logging
from shared import log

# delaying refresh with sleep
import time

# teeworlds api part
import tw_api as tw
import copy

# vpn api classes
from vpn_apis import API_GetIPIntel_Net, API_IPHub, API_IP_Teoh_IO

# worker threads
import threading

# retrieving credentials from .env file
import os
from dotenv import load_dotenv

# discord bot part
import discord
from discord.utils import escape_markdown as escape


# validating VPN commands
from validate_email import validate_email
import ipaddress
import re

import sys


# how long to wait before refreshing the player lists
REFRESH_DELAY = 5.0

ENABLE_MASS_VPN_CHECK = False


"""
Basically, the updater updates the currently available servers, every REFRESH_DELAY seconds
And the discord bot handles the discord connection at the same time.

The VPN checker can be used to check player IPs against multiple free online APIs,
that provide such checks. In order not to hit the daily limits too fast, we save previously checked IPs

"""



def get_master_servers() -> List[Tuple[str, int]]:
    master_servers = []

    for i in range(1, tw.NUM_MASTERSERVERS+1):
        m = tw.Master_Server_Info(("master%d.teeworlds.com" % i, tw.MASTERSERVER_PORT))
        master_servers.append(m)
    return master_servers


def get_sever_addresses(master_servers : List[Tuple[str, int]]) -> List[Tuple[str, int]]:
    addresses = set()
    if not isinstance(master_servers, list):
        master_servers = [master_servers]
    
    for master in master_servers:
        master.start()
    
    time.sleep(0.01)

    for master in master_servers:
        master.join()
        
        for address in master.servers:
            addresses.add(address)
    
    return sorted(list(addresses))


def get_server_infos(addresses : List[Tuple[str, int]], retries=10) -> Dict[Tuple[str, int], Dict]:

    def get_infos(addresses : List) -> Dict:

        infos = {}
        if not isinstance(addresses, list):
            addresses = [addresses]
        
        servers = []

        for address in addresses:
            m = tw.Server_Info(address)
            m.start()
            servers.append(m)

        time.sleep(0.01)

        for server_info in servers:
            server_info.join()
            if server_info['error'] == None:
                infos[server_info['address']] = server_info.info

        return infos
    
    
    addresses_set = set(addresses)
    servers = dict()
    tries = retries
    while len(servers) != len(addresses) and tries > 0:
        # addresses that are expected to be found - addresses that are already found
        missing_addresses = list(addresses_set - set(servers.keys()))
        
        # add newly found address infos to out complete set of infos
        servers.update(get_infos(missing_addresses))

        # decrement tries
        tries -= 1

    # return all the server infos we could find.
    return servers


def get_players_info(server_infos : Dict[Tuple[str, int], Dict]) -> List[Dict]:
    players = []

    for address, server in server_infos.items():
        if len(server['players']) > 0:
            for player in server['players']:
                player['address'] = address
                players.append(player)
    
    return players


def get_modifications(server_infos : Dict[Tuple[str, int], Dict]) -> List[str]:
    mods = set()

    for _, server in server_infos.items():
        mods.add(server['gametype'])
        
    return sorted(list(mods))


def iterative_levenshtein(s : str, t : str) -> int:
    """ 
        iterative_levenshtein(s, t) -> ldist
        ldist is the Levenshtein distance between the strings 
        s and t.
        For all i and j, dist[i,j] will contain the Levenshtein 
        distance between the first i characters of s and the 
        first j characters of t
        https://www.python-course.eu/levenshtein_distance.php
    """
    rows = len(s)+1
    cols = len(t)+1
    dist = [[0 for x in range(cols)] for x in range(rows)]
    # source prefixes can be transformed into empty strings 
    # by deletions:
    for i in range(1, rows):
        dist[i][0] = i
    # target prefixes can be created from an empty source string
    # by inserting the characters
    for i in range(1, cols):
        dist[0][i] = i
    

    for col in range(1, cols):
        for row in range(1, rows):
            if s[row-1] == t[col-1]:
                cost = 0
            else:
                cost = 1
            dist[row][col] = min(dist[row-1][col] + 1,      # deletion
                                 dist[row][col-1] + 1,      # insertion
                                 dist[row-1][col-1] + cost) # substitution
    
    return dist[rows-1][cols-1] 

def find_player(partial_nickname : str, players : List[Dict]) -> Dict:
    players_copy = copy.copy(players)

    players_copy.sort(key=lambda player: iterative_levenshtein(partial_nickname.lower(), player['name'].lower()))

    for player in players_copy:
        name = player['name'].lower()
        if partial_nickname.lower() in name:
            return copy.deepcopy(player)

    return None

def find_online_servers(gametype : str, server_infos : Dict[Tuple[str, int], Dict]) -> List[Dict]:
    active_servers = []

    for _, server in server_infos.items():
        if len(server['players']) > 0 and gametype.lower() in server['gametype'].lower():
            active_servers.append(server)
    
    active_servers.sort(key=lambda server: -len(server['players']))

    return active_servers


class DataUpdater(threading.Thread):
    def __init__(self, checked_ips_file='ips.txt'):
        self.running = False

        # vpn chencking
        self.ips_file = checked_ips_file
        self.ip_count = 0
        # init ips
        self.read_ips()

        threading.Thread.__init__(self, target=self.run)
    
    def run(self):
        self.running = True
        
        while self.running:
            self.step()
            self.update_ips()
            time.sleep(REFRESH_DELAY)

            
    def step(self):
        global mutex, server_infos, all_players
        
        addresses = get_sever_addresses(get_master_servers())
        servers = get_server_infos(addresses)
        if len(addresses) > 0 and len(servers) > 0:

            mutex.acquire()

            server_infos = servers
            all_players = get_players_info(server_infos)

            log("teeworlds", f"Servers: {len(server_infos)} Players: {len(all_players)}")
            mutex.release()
    
    def read_ips(self):
        if os.path.exists(self.ips_file):
            global mutex, ips

            tmp_dict = {}
            with open(self.ips_file) as f:
                for line in f:
                    tokens = line.split(" ")
                    key = tokens[0].strip()
                    try:
                        is_vpn = int(tokens[1])
                    except:
                        is_vpn = 0
                    tmp_dict[key] = bool(is_vpn)
            
            mutex.acquire()
            ips = tmp_dict
            self.ip_count = len(ips)
            mutex.release()
            log("vpn", f"Loaded {self.ip_count} IPs.")


    def update_ips(self):
        global mutex, ips
        lines = []

        mutex.acquire()
        something_changed = len(ips) > self.ip_count and len(ips) > 0
        if something_changed:
            for key, value in ips.items():
                lines.append(f"{key} {int(value)}\n")
            
            self.ip_count = len(ips)
        mutex.release()

        if something_changed:
            lines.sort()
            log("vpn", f"Writing {len(lines)} IPs")
            with open(self.ips_file, 'w') as f:    
                f.writelines(lines)
            log("vpn", f"Done writing IPs!")



class TeeworldsDiscord(discord.Client):

    def __init__(self):
        super().__init__()
        self.email = os.getenv("EMAIL")
        self.apis = [API_GetIPIntel_Net(email, 0.95), API_IPHub(iphub_token), API_IP_Teoh_IO()]



    async def on_message(self, message):
        global mutex, server_infos, all_players, ips, email, iphub_token, invalid_vpn_networks


        if message.author == self.user:
            return
        
        text = message.content

        if text.startswith("!help"):
            await message.channel.send("""Teeworlds Discord Bot by jxsl13. Have fun.
Commands:
**!p[layer]** <player> -  Check whether a player is currently online
**!o[nline]** <gametype> - Find all online servers with a specific gametype
**!o[nline]p[layers]** <gametype> - Show a list of servers and players playing a specific gametype.
**!vpn** <IP> - check if a given IP is actually a player connected via VPN(this feature doesn't work on servers, PM the bot.).
**!ip_filter** <text> - given a random text, the bot will return all unique IPs of that text.

            """)
        elif text.startswith("!player ") or text.startswith("!p "):
            tokens = text.split(" ", maxsplit=1)

            if len(tokens) != 2:
                return
            mutex.acquire()
            player = find_player(tokens[1], all_players)
            mutex.release()
            
            if player:
                await message.channel.send(f"'{escape(player['name'])}' is currently playing on '{escape(server_infos[player['address']]['name'])}'")
            else:
                await message.channel.send(f"No such player found: '{tokens[1]}'")


        elif text.startswith("!online ") or text.startswith("!o "):
            tokens = text.split(" ", maxsplit=1)

            if len(tokens) != 2:
                return
            
            mutex.acquire()
            servers = find_online_servers(tokens[1], server_infos)
            mutex.release()

            answer = ""

            if len(servers) > 0:
                line = ""

                for server in servers:
                    line = f"\n**{escape(server['name'])}** ({server['num_players']} Players)"
                    if len(answer) + len(line) > 2000:
                        await message.channel.send(answer)
                        answer = line
                    else:
                        answer += line

            else:
                answer = f"No online servers with gametype '{tokens[1]}' found!"

            if len(answer) > 0:
                await message.channel.send(answer)
        
        elif text.startswith("!onlineplayers ") or text.startswith("!op "):
            tokens = text.split(" ", maxsplit=1)

            if len(tokens) != 2:
                return
            
            mutex.acquire()
            servers = find_online_servers(tokens[1], server_infos)
            mutex.release()

            answer = ""

            if len(servers) > 0:

                for server in servers:
                    answer = f"\n**{escape(server['name'])}** ({server['num_players']} Players)"
                    answer += "\n```"
                    for player in server['players']:
                        name = player['name']
                        clan = player['clan']
                        player_type = "(bot)" if player['player'] >= 2 else ""
                        answer += "\n{:<{name_width}}      {:>{clan_width}} {player_type}".format(
                            name, 
                            clan, 
                            name_width=16,  
                            clan_width=12, 
                            player_type=player_type)

                    answer += "```\n"  
                    await message.channel.send(answer)
                    answer = ""

            else:
                answer = f"No online servers with gametype '{tokens[1]}' found!"

            if len(answer) > 0:
                await message.channel.send(answer)
        elif text.startswith("!vpn "):
            
            if message.channel.type is not discord.ChannelType.private:
                await message.channel.send("This feature is only available via PM. Please send a private message.")
                return

            tokens = text.split(" ")
            if len(tokens) < 2:
                return

            valid_ips = [x for x in tokens if is_valid_ip(x)]

            if len(valid_ips) == 0:
                await message.channel.send("Invalid IP address(es) provided.")
                return
            
            if not ENABLE_MASS_VPN_CHECK:
                if len(valid_ips) >= 16:
                    valid_ips = valid_ips[:16]
                                    

            for ip in valid_ips:
                is_vpn = False

                # check if ip is in reserved networks
                __ip = ipaddress.ip_address(ip)
                for network in invalid_vpn_networks:
                    if __ip in network:
                        await message.channel.send(f"The IP '{ip}' is part of a reserved IP range which should not be accessible to humans.")
                        return


                is_ip_known = True
                mutex.acquire()
                try:
                    is_vpn = ips[ip]
                except KeyError:
                    is_ip_known = False
                mutex.release()

                if not is_ip_known:
                    log("vpn", f"Unknown IP: {ip}")
                    # ip is unknown
                    
                    got_resonse = False
                    
                    # if one api says yes, we save the ip as vpn
                    for idx, api in enumerate(self.apis):
                        log("vpn", f"Checking API {idx +1}/{len(self.apis)}")
                        err, is_vpn = await api.is_vpn(ip)
                        if err:
                            cooldown = api.get_remaining_cooldown()
                            log("vpn", f"Skipping API {idx +1}/{len(self.apis)}")
                            if cooldown > 0:
                                log("cooldown", f"{cooldown} seconds left.")
                            continue
                        else:
                            got_resonse = True

                        if is_vpn:
                            log("vpn", "Is a VPN!")
                            mutex.acquire()
                            ips[ip] = True
                            mutex.release()
                            break
                    

                    if not got_resonse:
                        await message.channel.send(f"Could not retrieve any data for IP '{ip}', please try this command another time.")
                        continue
                    elif not is_vpn:
                        # got response and none of th eapis said that the ip is a VPN
                        mutex.acquire()
                        log("vpn", "Is not a VPN")
                        ips[ip] = False
                        mutex.release()
                    
                else:
                    # known ip, do nothing, just send the message
                    log("vpn", f"Known IP: {ip}")
                
                # inform the player about whether the ip is a vpn or not
                string = "not"
                if is_vpn:
                    ip = f'**{ip}**'
                    string = ""
                
                await message.channel.send(f"The IP '{ip}' is {string} a VPN")
        elif text.startswith("!ip_filter "):
            
            if message.channel.type is not discord.ChannelType.private:
                await message.channel.send("This feature is only available via PM. Please send a private message.")
                return

            tokens = text.split(" ", maxsplit=1)

            if len(tokens) < 2:
                return
            
            ipv4_pattern = r"(?:(?:1\d\d|2[0-5][0-5]|2[0-4]\d|0?[1-9]\d|0?0?\d)\.){3}(?:1\d\d|2[0-5][0-5]|2[0-4]\d|0?[1-9]\d|0?0?\d)"
            res = re.findall(ipv4_pattern, tokens[1])
            unique_ips = sorted(list(set(res)))
            
            answer = "!vpn"
            for ip in unique_ips:
                answer = f"{answer} {ip}"
            
            await message.channel.send(answer)


def is_valid_ip(ip : str) -> bool:    
    try:
        ipaddress.ip_address(ip)
        return True
    except:
        return False

def fill_invaild_networks(networks: List[str]):
    res = []
    for n in networks:
        res.append(ipaddress.ip_network(n))
    return res




if __name__ == "__main__":

    # credentials
    load_dotenv()
    discord_token = os.getenv('DISCORD_TOKEN')
    email = os.getenv('EMAIL')
    iphub_token = os.getenv('IPHUB_TOKEN')

    is_valid = validate_email(email)
    if not is_valid:
        log("FATAL", "Passed email is not valid, please use a non made up email address")
        sys.exit(1)

    # initialize global variables
    mutex = threading.Lock()
    server_infos = dict()
    all_players = []
    ips = dict()

    # https://en.wikipedia.org/wiki/Reserved_IP_addresses
    invalid_vpn_networks = fill_invaild_networks([
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.88.99.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "255.255.255.255/32",
        "::/0",
        "::/128",
        "::1/128",
        "::ffff:0:0/96",
        "::ffff:0:0:0/96",
        "64:ff9b::/96",
        "100::/64",
        "2001::/32",
        "2001:20::/28",
        "2001:db8::/32",
        "2002::/16",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
    ])

    # tw api getting data drom master servers & servers
    # started in different thread
    # and vpn data saver
    updater = DataUpdater()
    updater.start()

    
    # started in main thread
    discord_bot = TeeworldsDiscord()
    discord_bot.run(discord_token)

    

