
### Discord configuration
Create a new file `~/.env`

The file must contain your discord bot's access token.
```
# .env
DISCORD_TOKEN=<your token>

IPHUB_TOKEN=<your https://iphub.info key>
EMAIL=<a proper existing email!>
```

### Add the script to automatically start on reboot.
```
crontab -e
```

Add a new line:
```
@reboot TeeworldsDiscordBot/./main.py
```

Extract all unique IPs from your log files:
```unix
cat *.txt | grep -E -o "([0-9]{1,3}[\.]){3}[0-9]{1,3}" | sort | uniq > UNIQUE_IPs.txt
```