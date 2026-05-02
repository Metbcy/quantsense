#!/bin/bash
cd /tmp/proj/quantsense/frontend
exec env BACKEND_URL=http://127.0.0.1:8765 PORT=3210 node node_modules/next/dist/bin/next start 2>&1
