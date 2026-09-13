#!/bin/bash
set -e
cd /Users/adityavardhan/SLP/eval
echo "=== dev (train) split, full ==="
/Users/adityavardhan/SLP/venv/bin/python3 speechocean.py --split dev
echo "=== test split, full ==="
/Users/adityavardhan/SLP/venv/bin/python3 speechocean.py --split test
echo "=== DONE ==="
