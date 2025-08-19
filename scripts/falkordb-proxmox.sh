#!/usr/bin/env bash

# FalkorDB Proxmox LXC Container Creator
# This script creates an LXC container and installs FalkorDB
# Run this on your Proxmox host

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP="FalkorDB"
CTID=""
HOSTNAME="falkordb"
DISK_SIZE="8"
CPU_CORES="2"
RAM_MB="2048"
BRIDGE="vmbr0"
OS_TYPE="debian"
OS_VERSION="12"
STORAGE="local-lvm"

# Functions
msg_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

msg_ok() {
    echo -e "${GREEN}[OK]${NC} $1"
}

msg_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

header() {
    echo -e "${GREEN}
 ███████╗ █████╗ ██╗     ██╗  ██╗ ██████╗ ██████╗ ██████╗ ██████╗ 
 ██╔════╝██╔══██╗██║     ██║ ██╔╝██╔═══██╗██╔══██╗██╔══██╗██╔══██╗
 █████╗  ███████║██║     █████╔╝ ██║   ██║██████╔╝██║  ██║██████╔╝
 ██╔══╝  ██╔══██║██║     ██╔═██╗ ██║   ██║██╔══██╗██║  ██║██╔══██╗
 ██║     ██║  ██║███████╗██║  ██╗╚██████╔╝██║  ██║██████╔╝██████╔╝
 ╚═╝     ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚═════╝ 
${NC}
    ${YELLOW}FalkorDB Proxmox LXC Container Creator${NC}
    ${BLUE}Fast graph database with Redis protocol${NC}
"
}

# Check if running on Proxmox
check_proxmox() {
    if ! command -v pct &> /dev/null; then
        msg_error "This script must be run on a Proxmox host"
        exit 1
    fi
}

# Find next available container ID
find_ctid() {
    local id=100
    while pct status $id &>/dev/null; do
        ((id++))
    done
    CTID=$id
    msg_ok "Using Container ID: $CTID"
}

# Get user input
get_settings() {
    echo -e "${YELLOW}Container Settings:${NC}"
    echo -e "  Container ID: ${BLUE}$CTID${NC}"
    read -p "  Hostname [$HOSTNAME]: " input
    HOSTNAME=${input:-$HOSTNAME}
    read -p "  Disk Size (GB) [$DISK_SIZE]: " input
    DISK_SIZE=${input:-$DISK_SIZE}
    read -p "  CPU Cores [$CPU_CORES]: " input
    CPU_CORES=${input:-$CPU_CORES}
    read -p "  RAM (MB) [$RAM_MB]: " input
    RAM_MB=${input:-$RAM_MB}
    read -p "  Storage [$STORAGE]: " input
    STORAGE=${input:-$STORAGE}
    read -p "  Network Bridge [$BRIDGE]: " input
    BRIDGE=${input:-$BRIDGE}
    
    echo
    msg_info "Creating container with:"
    echo -e "  ID: ${BLUE}$CTID${NC}"
    echo -e "  Hostname: ${BLUE}$HOSTNAME${NC}"
    echo -e "  Disk: ${BLUE}${DISK_SIZE}GB${NC}"
    echo -e "  CPU: ${BLUE}${CPU_CORES} cores${NC}"
    echo -e "  RAM: ${BLUE}${RAM_MB}MB${NC}"
    echo -e "  Storage: ${BLUE}$STORAGE${NC}"
    echo -e "  Bridge: ${BLUE}$BRIDGE${NC}"
    echo
    
    read -p "Continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
}

# Download Debian template if needed
download_template() {
    local template="debian-${OS_VERSION}-standard_${OS_VERSION}"
    local template_file="/var/lib/vz/template/cache/${template}*.tar.*"
    
    if ! ls $template_file 1> /dev/null 2>&1; then
        msg_info "Downloading Debian $OS_VERSION template..."
        pveam update
        pveam download local debian-${OS_VERSION}-standard
        msg_ok "Template downloaded"
    else
        msg_ok "Template already exists"
    fi
}

# Create container
create_container() {
    msg_info "Creating LXC container..."
    
    # Find the template file
    local template=$(ls /var/lib/vz/template/cache/debian-${OS_VERSION}-standard*.tar.* 2>/dev/null | head -n1 | xargs basename)
    
    if [ -z "$template" ]; then
        msg_error "Debian template not found"
        exit 1
    fi
    
    # Create the container
    pct create $CTID /var/lib/vz/template/cache/$template \
        --hostname $HOSTNAME \
        --storage $STORAGE \
        --rootfs ${STORAGE}:${DISK_SIZE} \
        --cores $CPU_CORES \
        --memory $RAM_MB \
        --net0 name=eth0,bridge=$BRIDGE,ip=dhcp \
        --unprivileged 1 \
        --features nesting=1 \
        --onboot 1 \
        --start 0
    
    msg_ok "Container created"
}

# Start container
start_container() {
    msg_info "Starting container..."
    pct start $CTID
    msg_ok "Container started"
    
    # Wait for network
    msg_info "Waiting for network..."
    local max_tries=30
    local tries=0
    while [ $tries -lt $max_tries ]; do
        if pct exec $CTID -- ping -c1 8.8.8.8 &>/dev/null; then
            msg_ok "Network is ready"
            break
        fi
        sleep 2
        ((tries++))
    done
    
    if [ $tries -eq $max_tries ]; then
        msg_error "Network timeout"
        exit 1
    fi
}

# Install FalkorDB
install_falkordb() {
    msg_info "Installing FalkorDB in container..."
    
    # Update container
    pct exec $CTID -- apt-get update
    pct exec $CTID -- apt-get -y upgrade
    
    # Install dependencies
    pct exec $CTID -- apt-get -y install curl wget redis-server
    
    # Stop and disable default Redis
    pct exec $CTID -- systemctl stop redis-server
    pct exec $CTID -- systemctl disable redis-server
    
    # Create FalkorDB directories
    pct exec $CTID -- mkdir -p /var/lib/falkordb
    pct exec $CTID -- mkdir -p /etc/falkordb
    
    # Create FalkorDB configuration
    pct exec $CTID -- bash -c 'cat > /etc/falkordb/falkordb.conf << EOF
port 6379
bind 0.0.0.0
dir /var/lib/falkordb
logfile /var/log/falkordb.log
loglevel notice
daemonize no

# Memory
maxmemory-policy noeviction
save 900 1
save 300 10
save 60 10000

# Load FalkorDB module (will be added after download)
# loadmodule /usr/lib/redis/modules/falkordb.so

# Network
tcp-keepalive 300
timeout 0
EOF'

    # Try to download FalkorDB module from Docker image
    msg_info "Extracting FalkorDB module..."
    pct exec $CTID -- bash -c '
        apt-get -y install docker.io
        docker pull falkordb/falkordb:latest
        docker create --name temp-falkor falkordb/falkordb:latest
        mkdir -p /usr/lib/redis/modules
        docker cp temp-falkor:/usr/lib/redis/modules/falkordb.so /usr/lib/redis/modules/ || \
        docker cp temp-falkor:/FalkorDB/bin/linux-x64-release/falkordb.so /usr/lib/redis/modules/
        docker rm temp-falkor
        docker rmi falkordb/falkordb:latest
        apt-get -y remove docker.io
        apt-get -y autoremove
    '
    
    # Update config to load module
    pct exec $CTID -- sed -i 's/# loadmodule/loadmodule/' /etc/falkordb/falkordb.conf
    
    # Create systemd service
    pct exec $CTID -- bash -c 'cat > /etc/systemd/system/falkordb.service << EOF
[Unit]
Description=FalkorDB Graph Database
After=network.target

[Service]
Type=notify
ExecStart=/usr/bin/redis-server /etc/falkordb/falkordb.conf
Restart=always
User=redis
Group=redis
WorkingDirectory=/var/lib/falkordb

[Install]
WantedBy=multi-user.target
EOF'
    
    # Set permissions
    pct exec $CTID -- chown -R redis:redis /var/lib/falkordb
    
    # Enable and start service
    pct exec $CTID -- systemctl daemon-reload
    pct exec $CTID -- systemctl enable falkordb
    pct exec $CTID -- systemctl start falkordb
    
    msg_ok "FalkorDB installed"
}

# Get container IP
get_ip() {
    IP=$(pct exec $CTID ip -4 addr show dev eth0 | grep inet | awk '{print $2}' | cut -d/ -f1)
}

# Main execution
main() {
    header
    check_proxmox
    find_ctid
    get_settings
    download_template
    create_container
    start_container
    install_falkordb
    get_ip
    
    echo
    msg_ok "FalkorDB LXC Container Created Successfully!"
    echo
    echo -e "${YELLOW}Container Information:${NC}"
    echo -e "  Container ID: ${BLUE}$CTID${NC}"
    echo -e "  Hostname: ${BLUE}$HOSTNAME${NC}"
    echo -e "  IP Address: ${BLUE}$IP${NC}"
    echo
    echo -e "${YELLOW}FalkorDB Connection:${NC}"
    echo -e "  Host: ${BLUE}$IP${NC}"
    echo -e "  Port: ${BLUE}6379${NC}"
    echo -e "  Protocol: ${BLUE}Redis${NC}"
    echo
    echo -e "${YELLOW}Test connection:${NC}"
    echo -e "  ${GREEN}redis-cli -h $IP ping${NC}"
    echo
    echo -e "${YELLOW}Access container:${NC}"
    echo -e "  ${GREEN}pct enter $CTID${NC}"
}

# Run
main "$@"