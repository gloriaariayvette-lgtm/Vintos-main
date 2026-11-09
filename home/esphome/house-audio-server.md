# The shower speaker's audio folder

The shower board (house-steam.yaml) plays his voice and his songs from a URL on the house network. Aegis cannot be
reached from the house network (its services live inside WSL), so house_boards.py copies each WAV over ssh to a folder
on the Mac Studio and the board fetches it from there. Files have random names and are cleared after an hour.

On the Studio, once (Gloria runs this; it serves only ~/house-audio, on port 8790):

    mkdir -p ~/house-audio
    cat > ~/Library/LaunchAgents/com.vintos.house-audio.plist <<PLIST
    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0"><dict>
      <key>Label</key><string>com.vintos.house-audio</string>
      <key>ProgramArguments</key><array>
        <string>/usr/bin/python3</string><string>-m</string><string>http.server</string><string>8790</string>
        <string>--directory</string><string>$HOME/house-audio</string></array>
      <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
    </dict></plist>
    PLIST
    launchctl load ~/Library/LaunchAgents/com.vintos.house-audio.plist

The URL the board is given is set in memory/house-boards.json under "audio" (default the Studio's house address,
port 8790). If the Studio's house address changes, change "base_url" there; nothing needs reflashing.
