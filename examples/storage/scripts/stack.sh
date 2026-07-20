# Example helper script to call make commands in the stack directory.
# This script assumes there is a Makefile in the stack directory and that the make command is available in the system's PATH.

# Path to the stack directory
STACK_DIR="/Users/Shared/Projects/stack"

stack_cmd() {
    local target="$1"
    make -C "$STACK_DIR" "$target"
}