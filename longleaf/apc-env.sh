# Environment for automate-pheno-comparisons runs on Longleaf
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR=/work/users/k/s/kschaper/.uv-cache
export UV_PYTHON_INSTALL_DIR=/work/users/k/s/kschaper/.uv-python
export APC=/work/users/k/s/kschaper/automate-pheno-comparisons
# keep oaklib/pystow ontology downloads (phenio.db is large) off the 50 GB home quota
export PYSTOW_HOME=$APC/pystow
export PATH="$APC/.venv/bin:$PATH"
