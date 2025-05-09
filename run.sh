#!/bin/bash

# Run script for Gemini Code Assist PR Poetry Collection
# This script runs the main collection program and then cleans up the poems

echo "=== Gemini Code Assist PR Poetry Collection ==="
echo "Starting collection process..."

# Run the main collection script
python get_new_flowers.py "$@"
MAIN_RESULT=$?

if [ $MAIN_RESULT -ne 0 ]; then
    echo "Error: Collection process failed with exit code $MAIN_RESULT"
    exit $MAIN_RESULT
fi

echo "Collection process completed successfully."
echo "Running cleanup process..."

# Run the cleanup script
python cleanup_poems.py
CLEANUP_RESULT=$?

if [ $CLEANUP_RESULT -ne 0 ]; then
    echo "Error: Cleanup process failed with exit code $CLEANUP_RESULT"
    exit $CLEANUP_RESULT
fi

echo "Cleanup process completed successfully."
echo "=== All processes completed ==="
