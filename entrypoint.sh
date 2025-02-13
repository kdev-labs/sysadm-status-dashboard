#!/bin/bash

set -e 

echo "Using DATABASE_FILE=${DATABASE_FILE}"

if [ ! -f "${DATABASE_FILE}" ]; then
    echo "Database file not found. Creating a new one..."
    sqlite3 ${DATABASE_FILE} < schema.sql
fi

if [ ! -f "${DATABASE_FILE}" ]; then
    echo "Error: Database file not found and could not be created."
    exit 1
fi


exec "$@"