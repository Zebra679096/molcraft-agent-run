#!/bin/bash
cd /home/z/my-project/molcraft-agent
source .venv/bin/activate
rm -f docs/iteration_log.jsonl output/result.log
exec python3 -u main.py --iterations 1 --max-minutes 90 --max-steps 1000 --model deepseek-chat 2>&1
