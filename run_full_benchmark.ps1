Remove-Item -Path "LOGS\raw\*.jsonl" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "LOGS\summaries\*.csv" -Force -ErrorAction SilentlyContinue

echo "Starting full benchmark run (100 iterations per scenario)..."
$env:PYTHONPATH="."
.\venv\Scripts\python.exe benchmark/runner.py --iterations 100 --modus all

echo "Benchmark complete! Check LOGS\summaries\ for results."
