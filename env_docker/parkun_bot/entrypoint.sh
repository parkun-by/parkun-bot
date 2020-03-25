#!/bin/sh
# Docker entrypoint script.

# copy config from volume mounted in /tmp/config/
CONFIG=/tmp/parkun_config/config.py
if [ -f "$CONFIG" ]; then
    echo "$CONFIG exist"
    cp -a $CONFIG ./
fi

python ./main.py