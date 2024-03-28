#!/bin/sh

nohup python monitor.py >> monitor.log 2>&1 &
echo $! > monitor.pid
