#!/usr/bin/env bash

# Standalone FalkorDB installer for Proxmox LXC
# Based on community-scripts template but self-contained
# Usage: Run this script on a fresh Debian/Ubuntu LXC container

# Colors and formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

function msg_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

function msg_ok() {
    echo -e "${GREEN}[OK]${NC} $1"
}

function msg_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

function header_info() {
    echo -e "${GREEN}
 ███████╗ █████╗ ██╗     ██╗  ██╗ ██████╗ ██████╗ ██████╗ ██████╗ 
 ██╔════╝██╔══██╗██║     ██║ ██╔╝██╔═══██╗██╔══██╗██╔══██╗██╔══██╗
 █████╗  ███████║██║     █████╔╝ ██║   ██║██████╔╝██║  ██║██████╔╝
 ██╔══╝  ██╔══██║██║     ██╔═██╗ ██║   ██║██╔══██╗██║  ██║██╔══██╗
 ██║     ██║  ██║███████╗██║  ██╗╚██████╔╝██║  ██║██████╔╝██████╔╝
 ╚═╝     ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚═════╝ 
${NC}
    ${YELLOW}FalkorDB Graph Database Installer${NC}
    ${BLUE}Fast graph database with Redis protocol${NC}
"
}
# Copyright (c) 2021-2025 tteck
# Author: tteck | Adapted for FalkorDB
# License: MIT | https://github.com/community-scripts/ProxmoxVE/raw/main/LICENSE
# Source: https://www.falkordb.com/

APP="FalkorDB"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   msg_error "This script must be run as root"
   exit 1
fi

# Only show header if running directly (not from LXC script)
if [[ -z "${PROXMOX_INSTALL}" ]]; then
    header_info
fi

function update_script() {
  header_info
  if [[ ! -f /usr/local/bin/falkordb-server ]]; then
    msg_error "No ${APP} Installation Found!"
    exit
  fi
  msg_info "Updating ${APP}"
  $STD apt-get update
  $STD apt-get -y upgrade
  
  # Check for FalkorDB updates
  CURRENT_VERSION=$(falkordb-server --version 2>&1 | grep -oP 'v\K[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown")
  LATEST_VERSION=$(curl -fsSL https://api.github.com/repos/FalkorDB/FalkorDB/releases/latest | grep -oP '"tag_name": "v\K[0-9]+\.[0-9]+\.[0-9]+')
  
  if [[ "$CURRENT_VERSION" != "$LATEST_VERSION" ]] && [[ "$LATEST_VERSION" != "" ]]; then
    msg_info "Updating FalkorDB from v$CURRENT_VERSION to v$LATEST_VERSION"
    install_falkordb
    $STD systemctl restart falkordb
    msg_ok "FalkorDB Updated to v$LATEST_VERSION"
  else
    msg_ok "FalkorDB is up to date (v$CURRENT_VERSION)"
  fi
  msg_ok "Updated Successfully"
  exit
}

function install_falkordb() {
  msg_info "Installing FalkorDB"
  
  # Install required packages for downloading
  apt-get update >/dev/null 2>&1
  apt-get -y install curl wget tar gzip >/dev/null 2>&1
  
  # Get latest version if not specified
  if [[ -z "$FALKORDB_VERSION" ]]; then
    msg_info "Getting latest FalkorDB version"
    FALKORDB_VERSION=$(curl -fsSL https://api.github.com/repos/FalkorDB/FalkorDB/releases/latest 2>/dev/null | grep -oP '"tag_name": "v\K[0-9]+\.[0-9]+\.[0-9]+' || echo "4.12.3")
    msg_info "Using FalkorDB version ${FALKORDB_VERSION}"
  fi
  
  # FalkorDB is distributed as a Docker image, we need to install Redis and the module
  msg_info "Installing Redis base"
  apt-get -y install redis-server >/dev/null 2>&1
  systemctl stop redis-server >/dev/null 2>&1
  systemctl disable redis-server >/dev/null 2>&1
  
  # Download FalkorDB module
  cd /tmp
  msg_info "Downloading FalkorDB module"
  DOWNLOAD_URL="https://github.com/FalkorDB/FalkorDB/releases/download/v${FALKORDB_VERSION}/falkordb.Linux-ubuntu22.04-x86_64.v${FALKORDB_VERSION}.zip"
  
  # Try different download URLs based on version
  if ! wget -q -O falkordb.zip "$DOWNLOAD_URL" 2>/dev/null; then
    # Try alternative naming
    DOWNLOAD_URL="https://github.com/FalkorDB/FalkorDB/releases/download/v${FALKORDB_VERSION}/falkordb.Linux-x86_64.v${FALKORDB_VERSION}.tar.gz"
    if ! wget -q -O falkordb.tar.gz "$DOWNLOAD_URL" 2>/dev/null; then
      msg_error "Could not download FalkorDB v${FALKORDB_VERSION}"
      msg_info "Installing from Docker image instead"
      
      # Install Docker to extract the module
      apt-get -y install docker.io >/dev/null 2>&1
      docker pull falkordb/falkordb:v${FALKORDB_VERSION} >/dev/null 2>&1
      
      # Extract the module from Docker image
      docker create --name temp-falkor falkordb/falkordb:v${FALKORDB_VERSION} >/dev/null 2>&1
      docker cp temp-falkor:/usr/lib/redis/modules/falkordb.so /usr/lib/redis/modules/ >/dev/null 2>&1
      docker rm temp-falkor >/dev/null 2>&1
      
      # Clean up Docker
      apt-get -y remove docker.io >/dev/null 2>&1
      apt-get -y autoremove >/dev/null 2>&1
    else
      tar -xzf falkordb.tar.gz >/dev/null 2>&1
      mkdir -p /usr/lib/redis/modules
      find . -name "*.so" -exec cp {} /usr/lib/redis/modules/falkordb.so \; 2>/dev/null
    fi
  else
    apt-get -y install unzip >/dev/null 2>&1
    unzip -q falkordb.zip >/dev/null 2>&1
    mkdir -p /usr/lib/redis/modules
    find . -name "*.so" -exec cp {} /usr/lib/redis/modules/falkordb.so \; 2>/dev/null
  fi
  
  # Clean up
  cd /
  rm -rf /tmp/falkordb* /tmp/temp*
  
  msg_ok "FalkorDB Module Installed"
}

function setup_systemd() {
  msg_info "Setting up FalkorDB systemd service"
  
  # Create falkordb user
  useradd --system --home /var/lib/falkordb --shell /bin/false falkordb >/dev/null 2>&1 || true
  
  # Create directories
  mkdir -p /var/lib/falkordb
  mkdir -p /var/log/falkordb
  mkdir -p /etc/falkordb
  
  # Set permissions
  chown -R falkordb:falkordb /var/lib/falkordb
  chown -R falkordb:falkordb /var/log/falkordb
  chown -R falkordb:falkordb /etc/falkordb
  
  # Create FalkorDB configuration
  cat <<EOF >/etc/falkordb/falkordb.conf
# FalkorDB Configuration
port 6379
bind 0.0.0.0
dir /var/lib/falkordb
logfile /var/log/falkordb/falkordb.log
loglevel notice
daemonize no

# Memory management
maxmemory-policy noeviction
save 900 1
save 300 10
save 60 10000

# Graph module specific settings
loadmodule /usr/lib/redis/modules/falkordb.so

# Security (uncomment and set password)
# requirepass your_secure_password_here

# Network
tcp-keepalive 300
timeout 0
EOF

  # Create systemd service
  cat <<EOF >/etc/systemd/system/falkordb.service
[Unit]
Description=FalkorDB Graph Database
After=network.target

[Service]
Type=notify
User=falkordb
Group=falkordb
ExecStart=/usr/bin/redis-server /etc/falkordb/falkordb.conf
ExecStop=/bin/kill -s QUIT \$MAINPID
TimeoutStopSec=0
Restart=always
WorkingDirectory=/var/lib/falkordb

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/falkordb /var/log/falkordb

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable falkordb >/dev/null 2>&1
  
  msg_ok "Systemd service configured"
}

function setup_firewall() {
  msg_info "Configuring firewall"
  ufw allow 6379/tcp comment "FalkorDB" >/dev/null 2>&1
  msg_ok "Firewall configured"
}

# Main installation
main() {
    install_falkordb
    setup_systemd
    setup_firewall

    msg_info "Starting FalkorDB"
    systemctl start falkordb
    if systemctl is-active --quiet falkordb; then
        msg_ok "FalkorDB Started"
    else
        msg_error "Failed to start FalkorDB - check logs with: journalctl -u falkordb"
    fi

    msg_info "Cleaning up"
    apt-get -y autoremove >/dev/null 2>&1
    apt-get -y autoclean >/dev/null 2>&1
    msg_ok "Cleaned"
}

# Run installation if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main
    
    # Get container IP
    IP=$(hostname -I | awk '{print $1}')
    
    msg_ok "Completed Successfully!"
    echo ""
    echo -e "${GREEN}${APP} setup has been successfully initialized!${NC}"
    echo -e "${YELLOW}Access it using the following connection details:${NC}"
    echo -e "  ${BLUE}Host:${NC} ${IP}"
    echo -e "  ${BLUE}Port:${NC} 6379"
    echo -e "  ${BLUE}Protocol:${NC} Redis"
    echo ""
    echo -e "${YELLOW}Connect using FalkorDB CLI:${NC}"
    echo -e "  ${GREEN}falkordb-cli -h ${IP} -p 6379${NC}"
    echo ""
    echo -e "${YELLOW}Configuration file:${NC}"
    echo -e "  ${GREEN}/etc/falkordb/falkordb.conf${NC}"
    echo ""
    echo -e "${YELLOW}Service management:${NC}"
    echo -e "  ${GREEN}systemctl status falkordb${NC}"
    echo -e "  ${GREEN}systemctl restart falkordb${NC}"
    echo -e "  ${GREEN}systemctl stop falkordb${NC}"
fi