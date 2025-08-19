#!/usr/bin/env bash
source <(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/misc/build.func)
# Copyright (c) 2021-2025 tteck
# Author: tteck | Adapted for FalkorDB
# License: MIT | https://github.com/community-scripts/ProxmoxVE/raw/main/LICENSE
# Source: https://www.falkordb.com/

# This script creates a Proxmox LXC container and installs FalkorDB inside it
# Run this on your Proxmox host

APP="FalkorDB"
var_tags="database,graph"
var_cpu="2"
var_ram="2048"
var_disk="8"
var_os="debian"
var_version="12"
var_unprivileged="1"

# Use a dummy install script name that we'll override
var_install="debian"  # Use debian as a base, we'll override the actual installation

header_info "$APP"
variables
color
catch_errors

function update_script() {
  header_info
  check_container_storage
  check_container_resources
  
  msg_info "Updating ${APP}"
  # Update system packages
  apt-get update >/dev/null 2>&1
  apt-get -y upgrade >/dev/null 2>&1
  
  # Check for FalkorDB updates
  if command -v falkordb-server &> /dev/null; then
    CURRENT_VERSION=$(falkordb-server --version 2>&1 | grep -oP 'v\K[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown")
    LATEST_VERSION=$(curl -fsSL https://api.github.com/repos/FalkorDB/FalkorDB/releases/latest | grep -oP '"tag_name": "v\K[0-9]+\.[0-9]+\.[0-9]+')
    
    if [[ "$CURRENT_VERSION" != "$LATEST_VERSION" ]] && [[ "$LATEST_VERSION" != "" ]]; then
      msg_info "Updating FalkorDB from v$CURRENT_VERSION to v$LATEST_VERSION"
      # Download and install update
      cd /tmp
      wget -q "https://github.com/FalkorDB/FalkorDB/releases/download/v${LATEST_VERSION}/falkordb-v${LATEST_VERSION}-linux-x64.tar.gz"
      tar -xzf "falkordb-v${LATEST_VERSION}-linux-x64.tar.gz"
      systemctl stop falkordb
      cp -r "falkordb-v${LATEST_VERSION}-linux-x64/"* /usr/local/
      systemctl start falkordb
      rm -rf /tmp/falkordb*
      msg_ok "FalkorDB Updated to v$LATEST_VERSION"
    else
      msg_ok "FalkorDB is up to date (v$CURRENT_VERSION)"
    fi
  else
    msg_error "FalkorDB not found"
  fi
  
  msg_ok "Updated Successfully"
  exit
}

# This function is called by build.func after container creation
function description() {
  IP=$(pct exec "$CTID" ip -4 addr show dev eth0 | grep inet | awk '{print $2}' | cut -d/ -f1)
  
  # Install FalkorDB using our installation script
  msg_info "Installing FalkorDB in container $CTID"
  lxc-attach -n "$CTID" -- bash -c "export PROXMOX_INSTALL=1; $(curl -fsSL https://raw.githubusercontent.com/oculairmedia/graphiti/ingestion-queue-system/scripts/falkordb-install.sh)" || {
    msg_error "Failed to install FalkorDB"
    exit 1
  }
  
  msg_ok "FalkorDB installed successfully"
  
  echo -e "${APP} LXC Container Information:"
  echo -e "${BGN}Container ID: ${CL}${BL}$CTID${CL}"
  echo -e "${BGN}Hostname: ${CL}${BL}$HN${CL}"
  echo -e "${BGN}IP Address: ${CL}${BL}$IP${CL}"
  echo
  echo -e "${BGN}FalkorDB Connection Details:${CL}"
  echo -e "${TAB}${BGN}Host: ${CL}${BL}$IP${CL}"
  echo -e "${TAB}${BGN}Port: ${CL}${BL}6379${CL}"
  echo -e "${TAB}${BGN}Protocol: ${CL}${BL}Redis${CL}"
  echo
  echo -e "${BGN}Connect using FalkorDB CLI:${CL}"
  echo -e "${TAB}${BL}falkordb-cli -h $IP -p 6379${CL}"
  echo
  echo -e "${BGN}Service Management (inside container):${CL}"
  echo -e "${TAB}${BL}systemctl status falkordb${CL}"
  echo -e "${TAB}${BL}systemctl restart falkordb${CL}"
}

start
build_container
description

msg_ok "Completed Successfully!\n"