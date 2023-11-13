#!/bin/bash
python3 agent.py -host 0.0.0.0 -p 3000 /lib/nagios/plugin/check_ram.py
