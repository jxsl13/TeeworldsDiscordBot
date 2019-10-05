
### Discord configuration
Create a new file `~/.env`

The file must contain your discord bot's access token.
```
# .env
DISCORD_TOKEN=<your token>
```

### Add the script to automatically start on reboot.
```
crontab -e
```

Add a new line:
```
@reboot TeeworldsDiscordBot/./main.py
```