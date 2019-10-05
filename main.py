#!/usr/bin/python3

from typing import List, Tuple, Dict

# teeworlds api part
import tw_api as tw
import copy
import time
from datetime import datetime
import threading

# discord bot part
import os
import discord
from discord.utils import escape_markdown as escape
from dotenv import load_dotenv

mutex = threading.Lock()
server_infos = dict()
all_players = []

REFRESH_DELAY = 10.0


"""
Basically, the updater updates the currently available servers, every 10 seconds
And the discord bot handles the discord connection at the same time.

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
    def __init__(self):
        self.running = False
        threading.Thread.__init__(self, target=self.run)
    
    def run(self):
        self.running = True
        
        while self.running:
            self.step()
            time.sleep(REFRESH_DELAY)

            
    def step(self):
        global mutex, server_infos, all_players
        
        addresses = get_sever_addresses(get_master_servers())
        servers = get_server_infos(addresses)
        if len(addresses) > 0 and len(servers) > 0:

            mutex.acquire()

            server_infos = servers
            all_players = get_players_info(server_infos)

            now = datetime.now()
            print("Update", now.strftime("%d.%m.%Y %H:%M:%S"), "Servers:", len(server_infos), "Players:", len(all_players))
            mutex.release()


class TeeworldsDiscord(discord.Client):

    async def on_message(self, message):
        global mutex, server_infos, all_players


        if message.author == self.user:
            return
        
        text = message.content

        if text.startswith("!help"):
            await message.channel.send("""Teeworlds Discord Bot by jxsl13. Have fun.
Commands:
**!p[layer]** <player> -  Check whether a player is currently online
**!o[nline]** <gametype> - Find all online servers with a specific gametype

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



if __name__ == "__main__":

    # DISCORD credentials
    load_dotenv()
    token = os.getenv('DISCORD_TOKEN')

    # tw api getting data drom master servers & servers
    # started in different thread
    updater = DataUpdater()
    updater.start()

    
    # started in main thread
    discord_bot = TeeworldsDiscord()
    discord_bot.run(token)
