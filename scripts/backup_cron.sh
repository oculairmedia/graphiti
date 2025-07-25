#!/bin/bash
#
# FalkorDB Backup Cron Configuration Setup
# Run this script to configure automated backups
#

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
BACKUP_SCRIPT="$SCRIPT_DIR/backup_falkordb.sh"
CRON_LOG="/var/log/falkordb-backup-cron.log"

# Make backup script executable
chmod +x "$BACKUP_SCRIPT"

# Create log directory
sudo mkdir -p /var/log
sudo mkdir -p /backups/falkordb

echo "🔧 Setting up FalkorDB automated backups..."

# Create crontab entries
CRONTAB_ENTRIES="
# FalkorDB Automated Backups
# Daily backup at 2:30 AM
30 2 * * * $BACKUP_SCRIPT daily >> $CRON_LOG 2>&1

# Weekly backup on Sunday at 3:00 AM
0 3 * * 0 $BACKUP_SCRIPT weekly >> $CRON_LOG 2>&1

# Monthly backup on 1st of month at 4:00 AM
0 4 1 * * $BACKUP_SCRIPT monthly >> $CRON_LOG 2>&1

# Snapshot backup every 4 hours
0 */4 * * * $BACKUP_SCRIPT snapshot >> $CRON_LOG 2>&1
"

# Install crontab
echo "Installing crontab entries..."
(crontab -l 2>/dev/null; echo "$CRONTAB_ENTRIES") | crontab -

echo "✅ Crontab installed successfully!"

# Display current crontab
echo ""
echo "📋 Current crontab:"
crontab -l | grep -A 10 "FalkorDB Automated Backups" || echo "No FalkorDB backup entries found"

echo ""
echo "📁 Backup locations:"
echo "   Daily:    /backups/falkordb/daily/"
echo "   Weekly:   /backups/falkordb/weekly/"
echo "   Monthly:  /backups/falkordb/monthly/"
echo "   Snapshots: /backups/falkordb/snapshots/"

echo ""
echo "📊 Manual backup commands:"
echo "   Daily:    $BACKUP_SCRIPT daily"
echo "   Weekly:   $BACKUP_SCRIPT weekly"
echo "   Monthly:  $BACKUP_SCRIPT monthly"
echo "   Snapshot: $BACKUP_SCRIPT snapshot"

echo ""
echo "📝 Log files:"
echo "   Backup log: /var/log/falkordb-backup.log"
echo "   Cron log:   $CRON_LOG"