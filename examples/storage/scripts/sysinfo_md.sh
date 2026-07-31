#!/usr/bin/env zsh

# Helper to escape pipe characters in values (optional but safe)
escape_md() {
  echo "$1" | sed 's/|/\\|/g'
}

cpu_model=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || sysctl -n hw.model 2>/dev/null || echo "Unknown")
cpu_cores=$(sysctl -n hw.ncpu 2>/dev/null || echo "Unknown")

# Uptime parsing
uptime_raw=$(uptime)
uptime_clean=$(echo "$uptime_raw" | sed -E 's/^[^,]*,//' | sed 's/^ *//')

# Memory (vm_stat)
vm_line=$(vm_stat -c 1 2 | tail -1)
pages=$(echo "$vm_line" | awk '{print $2}')
free_pages=$(echo "$vm_line" | awk '{print $3}')
active_pages=$(echo "$vm_line" | awk '{print $4}')
inactive_pages=$(echo "$vm_line" | awk '{print $5}')
wired_pages=$(echo "$vm_line" | awk '{print $7}')

# Convert pages (4KB) to bytes then to GB
to_gb() {
  local p=$1
  local bytes=$((p * 4096))
  local gb=$(echo "$bytes" | awk '{printf "%.2f", $1/1024/1024/1024}')
  echo "$gb"
}

mem_total_gb=$(to_gb "$pages")
mem_free_gb=$(to_gb "$free_pages")
mem_active_gb=$(to_gb "$active_pages")
mem_inactive_gb=$(to_gb "$inactive_pages")
mem_wired_gb=$(to_gb "$wired_pages")

# CPU usage (last sample from top)
cpu_line=$(top -l 2 | grep -E "^CPU" | tail -1)
cpu_user=$(echo "$cpu_line" | awk '{print $3}' | tr -d '%')
cpu_sys=$(echo "$cpu_line" | awk '{print $5}' | tr -d '%')
cpu_idle=$(echo "$cpu_line" | awk '{print $7}' | tr -d '%')
cpu_usage=$(echo "$cpu_user $cpu_sys" | awk '{printf "%.1f", $1 + $2}')

# GPU model
gpu_model=$(system_profiler SPDisplaysDataType 2>/dev/null | grep "Chipset Model" | head -1 | sed 's/.*Chipset Model: //')

# Disk (root)
disk_info=$(df -h / | tail -1)
disk_size=$(echo "$disk_info" | awk '{print $2}')
disk_used=$(echo "$disk_info" | awk '{print $3}')
disk_avail=$(echo "$disk_info" | awk '{print $4}')
disk_pct=$(echo "$disk_info" | awk '{print $5}' | tr -d '%')

disk_summary="${disk_used} / ${disk_size} (${disk_pct}%)"

_format_as_markdown_column() {
  local col_width="$1"
  local value="$2"
  local prefix=${3:-""}
  local suffix=${4:-""}
  printf "%s %-${col_width}s %s" "$prefix" "$(escape_md "$value")" "$suffix"
}


markdown_table() {
  local col1_width=17
  local col2_width=39
  echo "| Metric             | Value                                    |"
  echo "|--------------------|------------------------------------------|"
  echo "$(_format_as_markdown_column "$col1_width" "CPU Model" "|") $(_format_as_markdown_column "$col2_width" "$cpu_model" "|" " |")"
  echo "$(_format_as_markdown_column "$col1_width" "CPU Cores" "|") $(_format_as_markdown_column "$col2_width" "$cpu_cores" "|" " |")"
  echo "$(_format_as_markdown_column "$col1_width" "Uptime" "|") $(_format_as_markdown_column "$col2_width" "$uptime_clean" "|" " |")"
  echo "$(_format_as_markdown_column "$col1_width" "Memory Total" "|") $(_format_as_markdown_column "$col2_width" "${mem_total_gb} GB" "|" " |")"
  echo "$(_format_as_markdown_column "$col1_width" "Memory Free" "|") $(_format_as_markdown_column "$col2_width" "${mem_free_gb} GB" "|" " |")"
  echo "$(_format_as_markdown_column "$col1_width" "Memory Active" "|") $(_format_as_markdown_column "$col2_width" "${mem_active_gb} GB" "|" " |")"
  echo "$(_format_as_markdown_column "$col1_width" "Memory Inactive" "|") $(_format_as_markdown_column "$col2_width" "${mem_inactive_gb} GB" "|" " |")"
  echo "$(_format_as_markdown_column "$col1_width" "Memory Wired" "|") $(_format_as_markdown_column "$col2_width" "${mem_wired_gb} GB" "|" " |")"
  echo "$(_format_as_markdown_column "$col1_width" "CPU Usage" "|") $(_format_as_markdown_column "$col2_width" "${cpu_usage}%" "|" " |")"
  echo "$(_format_as_markdown_column "$col1_width" "GPU Model" "|") $(_format_as_markdown_column "$col2_width" "$(escape_md "$gpu_model")" "|" " |")"
  echo "$(_format_as_markdown_column "$col1_width" "Disk" "|") $(_format_as_markdown_column "$col2_width" "$(escape_md "$disk_summary")" "|" " |")"
}

# Build and return Markdown table string
markdown_output() {
  cat <<EOF
| Metric          | Value                              |
|-----------------|------------------------------------|
| CPU Model       | $(escape_md "$cpu_model") |
| CPU Cores       | $cpu_cores                         |
| Uptime          | $(escape_md "$uptime_clean") |
| Memory Total    | ${mem_total_gb} GB                 |
| Memory Free     | ${mem_free_gb} GB                  |
| Memory Active   | ${mem_active_gb} GB                |
| Memory Inactive | ${mem_inactive_gb} GB              |
| Memory Wired    | ${mem_wired_gb} GB                 |
| CPU Usage       | ${cpu_usage}%                      |
| GPU Model       | $(escape_md "$gpu_model") |
| Disk            | $(escape_md "$disk_summary") |
EOF
}

# markdown_output
