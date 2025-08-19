#!/usr/bin/env bash
source <(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/misc/build.func)
# Copyright (c) 2021-2025 tteck
# Author: tteck | Adapted for FalkorDB
# License: MIT | https://github.com/community-scripts/ProxmoxVE/raw/main/LICENSE
# Source: https://www.falkordb.com/

APP="FalkorDB"
var_tags="${var_tags:-database;graph}"
var_cpu="${var_cpu:-2}"
var_ram="${var_ram:-2048}"
var_disk="${var_disk:-8}"
var_os="${var_os:-debian}"
var_version="${var_version:-12}"
var_unprivileged="${var_unprivileged:-1}"

header_info "$APP"
variables
color
catch_errors

function update_script() {
  header_info
  check_container_storage
  check_container_resources
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
  
  # Get latest version if not specified
  if [[ -z "$FALKORDB_VERSION" ]]; then
    FALKORDB_VERSION=$(curl -fsSL https://api.github.com/repos/FalkorDB/FalkorDB/releases/latest | grep -oP '"tag_name": "v\K[0-9]+\.[0-9]+\.[0-9]+')
  fi
  
  # Download and install FalkorDB
  cd /tmp
  DOWNLOAD_URL="https://github.com/FalkorDB/FalkorDB/releases/download/v${FALKORDB_VERSION}/falkordb-v${FALKORDB_VERSION}-linux-x64.tar.gz"
  $STD wget -O falkordb.tar.gz "$DOWNLOAD_URL"
  $STD tar -xzf falkordb.tar.gz
  
  # Install binaries
  $STD cp -r falkordb-v${FALKORDB_VERSION}-linux-x64/* /usr/local/
  $STD chmod +x /usr/local/bin/falkordb-server
  $STD chmod +x /usr/local/bin/falkordb-cli
  
  # Clean up
  $STD rm -rf /tmp/falkordb*
  
  msg_ok "FalkorDB v${FALKORDB_VERSION} Installed"
}

function setup_systemd() {
  msg_info "Setting up FalkorDB systemd service"
  
  # Create falkordb user
  $STD useradd --system --home /var/lib/falkordb --shell /bin/false falkordb
  
  # Create directories
  $STD mkdir -p /var/lib/falkordb
  $STD mkdir -p /var/log/falkordb
  $STD mkdir -p /etc/falkordb
  
  # Set permissions
  $STD chown -R falkordb:falkordb /var/lib/falkordb
  $STD chown -R falkordb:falkordb /var/log/falkordb
  $STD chown -R falkordb:falkordb /etc/falkordb
  
  # Create FalkorDB configuration
  cat <<EOF >/etc/falkordb/falkordb.conf
# FalkorDB Configuration
port 6379
bind 0.0.0.0
dir /var/lib/falkordb
logfile /var/log/falkordb/falkordb.log
loglevel notice

# Memory management
maxmemory-policy noeviction
save 900 1
save 300 10
save 60 10000

# Graph module specific settings
loadmodule /usr/local/lib/falkordb.so

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
ExecStart=/usr/local/bin/falkordb-server /etc/falkordb/falkordb.conf
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

  $STD systemctl daemon-reload
  $STD systemctl enable falkordb
  
  msg_ok "Systemd service configured"
}

function setup_firewall() {
  msg_info "Configuring firewall"
  $STD ufw allow 6379/tcp comment "FalkorDB"
  msg_ok "Firewall configured"
}

start
build_container
description

msg_info "Installing Dependencies"
$STD apt-get update
$STD apt-get -y install curl wget tar gzip ufw
msg_ok "Dependencies Installed"

install_falkordb
setup_systemd
setup_firewall

msg_info "Starting FalkorDB"
$STD systemctl start falkordb
msg_ok "FalkorDB Started"

motd_ssh
customize

msg_info "Cleaning up"
$STD apt-get -y autoremove
$STD apt-get -y autoclean
msg_ok "Cleaned"

msg_ok "Completed Successfully!\n"
echo -e "${CREATING}${GN}${APP} setup has been successfully initialized!${CL}"
echo -e "${INFO}${YW} Access it using the following connection details:${CL}"
echo -e "${TAB}${GATEWAY}${BGN}Host: ${IP}${CL}"
echo -e "${TAB}${GATEWAY}${BGN}Port: 6379${CL}"
echo -e "${TAB}${GATEWAY}${BGN}Protocol: Redis${CL}"
echo -e "${INFO}${YW} Connect using FalkorDB CLI:${CL}"
echo -e "${TAB}${GATEWAY}${BGN}falkordb-cli -h ${IP} -p 6379${CL}"
echo -e "${INFO}${YW} Configuration file: ${CL}"
echo -e "${TAB}${GATEWAY}${BGN}/etc/falkordb/falkordb.conf${CL}"
echo -e "${INFO}${YW} Service management:${CL}"
echo -e "${TAB}${GATEWAY}${BGN}systemctl status falkordb${CL}"
echo -e "${TAB}${GATEWAY}${BGN}systemctl restart falkordb${CL}"
echo -e "${TAB}${GATEWAY}${BGN}systemctl stop falkordb${CL}"