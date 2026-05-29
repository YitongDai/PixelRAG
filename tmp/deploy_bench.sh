#!/bin/bash
# Deploy screenshot benchmark to a remote lab machine
# Usage: ./deploy_bench.sh <ssh-host>
set -e

HOST=$1
if [ -z "$HOST" ]; then echo "Usage: $0 <ssh-host>"; exit 1; fi

echo "=== Deploying to $HOST ==="

# Create workspace
ssh $HOST "mkdir -p ~/pixelrag-bench/render/src ~/pixelrag-bench/tmp"

# Copy our strategy + bench code
rsync -az --delete \
  render/src/pixelrag_render/ \
  $HOST:~/pixelrag-bench/render/src/pixelrag_render/

# Copy the ZIM path check and bench runner
ssh $HOST "cat > ~/pixelrag-bench/setup.sh" << 'SETUP'
#!/bin/bash
set -e
cd ~/pixelrag-bench

# Install Chrome if needed
if ! which google-chrome-stable >/dev/null 2>&1; then
    echo "Installing Chrome..."
    wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    sudo apt-get install -y /tmp/chrome.deb 2>/dev/null || sudo dpkg -i /tmp/chrome.deb 2>/dev/null
    sudo apt-get install -f -y 2>/dev/null
fi

# Install Python deps
pip install websockets numpy pillow 2>/dev/null || pip3 install websockets numpy pillow 2>/dev/null

# Install kiwix-tools if needed
if ! which kiwix-serve >/dev/null 2>&1; then
    echo "Installing kiwix-tools..."
    wget -q -O /tmp/kiwix.tar.gz https://download.kiwix.org/release/kiwix-tools/kiwix-tools_linux-x86_64-3.8.1.tar.gz
    tar xzf /tmp/kiwix.tar.gz -C /tmp/
    sudo cp /tmp/kiwix-tools*/kiwix-serve /usr/local/bin/ 2>/dev/null || cp /tmp/kiwix-tools*/kiwix-serve ~/pixelrag-bench/
fi

# Check for ZIM file
for p in /mnt/data/*/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim \
         /opt/dlami/nvme/wiki-screenshot/wikipedia_en_all_maxi_2025-08.zim \
         ~/wikipedia_en_all_maxi_2025-08.zim; do
    if [ -f "$p" ]; then
        echo "ZIM: $p"
        echo "$p" > ~/pixelrag-bench/zim_path.txt
        break
    fi
done

if [ ! -f ~/pixelrag-bench/zim_path.txt ]; then
    echo "ERROR: No ZIM file found. Please provide path."
    exit 1
fi

echo "Setup complete"
SETUP

ssh $HOST "bash ~/pixelrag-bench/setup.sh"

echo "=== $HOST ready ==="
