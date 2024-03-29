#!/bin/sh

nohup python missing_block_checker.py "$@" >> missing_block_checker.log 2>&1 &
echo $! > missing_block_checker.pid
