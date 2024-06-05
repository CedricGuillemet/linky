#!/usr/bin/sh
systemctl --user stop linky
sudo stty -F /dev/ttyS0 sane
systemctl --user start linky
