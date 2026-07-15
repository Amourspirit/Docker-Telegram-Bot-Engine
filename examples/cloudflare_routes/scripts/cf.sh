# !/usr/bin/env bash

CF_OBSIDIAN_DOMAIN_NAME="sync-data.example.com"
CF_DOCKER_DOMAIN_NAME="dock.example.com"
CF_UI_DOMAIN_NAME="ui.example.com"
CF_GRAFANA_DOMAIN_NAME="grafana.example.com"
CF_ARCANE_DOMAIN_NAME="arcane.example.com"

cf_remote_cmd() {
    local record_name="$1"
    local action="$2"
    local quiet_flag=""
    if [[ -z "$record_name" || -z "$action" ]]; then
        echo "Usage: _cf_remote_cmd <record_name> <action>"
        return 1
    fi
    if [[ "$action" == "status" ]]; 
    then
        quiet_flag="--quiet"
    fi
    bash "$HOME/scripts/cf-dns-cname-route-util/src/tunnel_route.sh" --cf-record-name="$record_name" $quiet_flag "$action"
}
