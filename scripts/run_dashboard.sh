#!/bin/bash
# scripts/run_dashboard.sh
# CBGB Trade Dashboard 실행 스크립트

set -e

cd "$(dirname "$0")/.."  # 프로젝트 루트로 이동

echo "📊 Starting CBGB Trade Dashboard..."
echo ""
echo "Dashboard will open at: http://localhost:8501"
echo "Press Ctrl+C to stop"
echo ""

PYTHONPATH=. streamlit run src/dashboard/app.py
